"""MVP diagnosis agents with explicit tool boundaries."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from common.schemas.diagnosis import DiagnosisPlan, TaskResult
from common.schemas.shared import RiskFinding
from common.tools.llm import LLMUnavailable, extract_json_object, ollama_generate
from common.tools.diagnosis_tools import (
    check_owner_landlord_match,
    check_proxy_contract,
    classify_clause_risk,
    classify_ownership_risk,
    compare_standard_contract,
    search_registry_rag,
    search_special_clause_rag,
)


def run_contract_supervisor_agent(fields: dict[str, Any], validation_missing: list[str]) -> DiagnosisPlan:
    """Create a diagnosis plan from extracted PDF fields with LLM judgement."""
    special_terms = fields.get("special_terms") or []
    reasons: list[str] = []
    skipped: list[str] = []

    run_special = bool(special_terms)
    if run_special:
        reasons.append("special_terms extracted; run special_clause_agent")
    else:
        skipped.append("special_clause_agent:no_special_terms")

    reasons.append("PDF contract alone cannot prove registry owner/authority; run ownership_risk_agent")

    if fields.get("deposit_amount") and fields.get("address"):
        reasons.append("market fields present but MVP keeps market_risk_agent disabled")
    else:
        skipped.append("market_risk_agent:missing_market_inputs_or_disabled")

    if validation_missing:
        reasons.append(f"required fields missing: {', '.join(validation_missing)}")

    reference_plan = DiagnosisPlan(
        run_special_clause=False,
        run_ownership_risk=False,
        run_market_risk=False,
        run_insurance_risk=False,
        run_required_check=False,
        run_legal_basis=False,
        reasons=[
            "LLM supervisor unavailable; diagnosis cannot proceed as final judgement",
            *reasons,
        ],
        skipped_agents=skipped,
        llm_required=True,
        llm_used=False,
        status="LLM_REQUIRED_UNAVAILABLE",
    )
    llm_data = _llm_json_or_none(
        agent_name="contract_supervisor_agent",
        system="너는 전세계약 PDF 진단 supervisor agent다. 반드시 JSON만 반환한다.",
        prompt=f"""
추출된 계약서 필드를 보고 어떤 진단 agent를 실행할지 결정해.
MVP에서는 special_clause_agent와 ownership_risk_agent만 실제 실행 가능하다.
계약서 PDF만으로 등기부/소유자/대리권은 확정할 수 없으므로 ownership_risk_agent는 기본 실행한다.

반환 JSON:
{{
  "run_special_clause": true,
  "run_ownership_risk": true,
  "run_market_risk": false,
  "run_insurance_risk": false,
  "run_required_check": false,
  "run_legal_basis": false,
  "reasons": ["이유"],
  "skipped_agents": ["agent:reason"]
}}

fields:
{json.dumps(fields, ensure_ascii=False, default=str)}

validation_missing:
{json.dumps(validation_missing, ensure_ascii=False)}
""".strip(),
    )
    if not llm_data:
        return reference_plan
    return DiagnosisPlan(
        run_special_clause=bool(llm_data.get("run_special_clause", run_special)),
        run_ownership_risk=bool(llm_data.get("run_ownership_risk", True)),
        run_market_risk=bool(llm_data.get("run_market_risk", False)),
        run_insurance_risk=bool(llm_data.get("run_insurance_risk", False)),
        run_required_check=bool(llm_data.get("run_required_check", False)),
        run_legal_basis=bool(llm_data.get("run_legal_basis", False)),
        reasons=[str(item) for item in llm_data.get("reasons", reasons)],
        skipped_agents=[str(item) for item in llm_data.get("skipped_agents", skipped)],
        llm_required=True,
        llm_used=True,
        status="PLANNED",
    )


def run_special_clause_agent(fields: dict[str, Any]) -> TaskResult:
    """Analyze special clauses. Allowed tools:

    - search_special_clause_rag_tool
    - compare_standard_contract_tool
    - classify_clause_risk_tool
    """
    special_terms = [str(term) for term in fields.get("special_terms") or [] if str(term).strip()]
    query = "\n".join(special_terms)
    context_pack = search_special_clause_rag(query, top_k=5)
    comparisons = compare_standard_contract(special_terms)
    rule_risk_items = classify_clause_risk(special_terms, comparisons)
    llm_result = _run_special_clause_llm(special_terms, context_pack, comparisons, rule_risk_items)
    risk_items = llm_result.get("risk_items") if llm_result.get("llm_used") else []
    recommendations = list(llm_result.get("recommendations", [])) if llm_result.get("llm_used") else []
    return TaskResult(
        task="SPECIAL_CLAUSE",
        risk_items=risk_items,
        recommendations=list(dict.fromkeys(recommendations)),
        evidence_refs=_evidence_refs(context_pack),
        metadata={
            "allowed_tools": [
                "search_special_clause_rag_tool",
                "compare_standard_contract_tool",
                "classify_clause_risk_tool",
            ],
            "context_quality": context_pack.quality.reason,
            "context_score": context_pack.quality.score,
            "comparison_count": len(comparisons),
            "llm_attached": True,
            "llm_used": bool(llm_result.get("llm_used")),
            "llm_note": llm_result.get("llm_note"),
            "result_status": "COMPLETE" if llm_result.get("llm_used") else "LLM_REQUIRED_UNAVAILABLE",
            "fallback_reference_only": {
                "standard_contract_comparisons": comparisons,
                "rule_findings": [asdict(item) for item in rule_risk_items],
            },
        },
    )


def run_ownership_risk_agent(fields: dict[str, Any], registry_fields: dict[str, Any] | None = None) -> TaskResult:
    """Analyze ownership/authority risk. Allowed tools:

    - search_registry_rag_tool
    - check_owner_landlord_match_tool
    - check_proxy_contract_tool
    - classify_ownership_risk_tool
    """
    query = _registry_query(fields)
    context_pack = search_registry_rag(query, top_k=5)
    owner_checks = check_owner_landlord_match(fields, registry_fields)
    proxy_checks = check_proxy_contract(fields)
    rule_risk_items = classify_ownership_risk(fields, owner_checks, proxy_checks)
    llm_result = _run_ownership_llm(fields, context_pack, owner_checks, proxy_checks, rule_risk_items)
    risk_items = llm_result.get("risk_items") if llm_result.get("llm_used") else []
    reference_missing_checks = [
        check for check in owner_checks + proxy_checks
        if check.get("status") in {"MISSING", "REVIEW", "FAIL"}
    ]
    missing_checks = list(llm_result.get("missing_checks", [])) if llm_result.get("llm_used") else []
    recommendations = [finding.required_action for finding in risk_items if finding.required_action]
    recommendations.extend(llm_result.get("recommendations", []) if llm_result.get("llm_used") else [])
    return TaskResult(
        task="OWNERSHIP_RISK",
        risk_items=risk_items,
        recommendations=list(dict.fromkeys(recommendations)),
        evidence_refs=_evidence_refs(context_pack),
        missing_checks=missing_checks,
        metadata={
            "allowed_tools": [
                "search_registry_rag_tool",
                "check_owner_landlord_match_tool",
                "check_proxy_contract_tool",
                "classify_ownership_risk_tool",
            ],
            "context_quality": context_pack.quality.reason,
            "context_score": context_pack.quality.score,
            "llm_attached": True,
            "llm_used": bool(llm_result.get("llm_used")),
            "llm_note": llm_result.get("llm_note"),
            "result_status": "COMPLETE" if llm_result.get("llm_used") else "LLM_REQUIRED_UNAVAILABLE",
            "fallback_reference_only": {
                "owner_checks": owner_checks,
                "proxy_checks": proxy_checks,
                "missing_checks": reference_missing_checks,
                "rule_findings": [asdict(item) for item in rule_risk_items],
            },
        },
    )


def _run_special_clause_llm(
    special_terms: list[str],
    context_pack,
    comparisons: list[dict[str, Any]],
    rule_risk_items: list[RiskFinding],
) -> dict[str, Any]:
    data = _llm_json_or_none(
        agent_name="special_clause_agent",
        system="너는 전세계약 특약 위험 분석 agent다. 허용된 tool 결과만 근거로 JSON만 반환한다.",
        prompt=f"""
너는 special_clause_agent다.
이미 허용된 tool들이 실행되었다:
- search_special_clause_rag_tool
- compare_standard_contract_tool
- classify_clause_risk_tool

Tool 결과와 RAG 근거를 바탕으로 최종 task_result용 JSON을 작성해.
없는 사실을 만들지 말고, 위험하지 않은 항목은 제외해.

반환 JSON:
{{
  "risk_items": [
    {{
      "code": "CLAUSE_...",
      "title": "짧은 제목",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "score_delta": 15,
      "description": "왜 위험한지",
      "evidence": ["특약 원문 또는 근거"],
      "required_action": "수정/확인 조치"
    }}
  ],
  "recommendations": ["수정 권장 방향"]
}}

special_terms:
{json.dumps(special_terms, ensure_ascii=False)}

rag_contexts:
{json.dumps(_context_summary(context_pack), ensure_ascii=False)}

standard_contract_comparisons:
{json.dumps(comparisons, ensure_ascii=False)}

rule_findings:
{json.dumps([asdict(item) for item in rule_risk_items], ensure_ascii=False)}
""".strip(),
    )
    if not data:
        return {"llm_used": False, "llm_note": "LLM unavailable; fallback kept as reference only"}
    return {
        "llm_used": True,
        "llm_note": "LLM synthesized special clause task result",
        "risk_items": _findings_from_llm(data.get("risk_items", []), "special_clause_agent:llm"),
        "recommendations": [str(item) for item in data.get("recommendations", []) if str(item).strip()],
    }


def _run_ownership_llm(
    fields: dict[str, Any],
    context_pack,
    owner_checks: list[dict[str, Any]],
    proxy_checks: list[dict[str, Any]],
    rule_risk_items: list[RiskFinding],
) -> dict[str, Any]:
    data = _llm_json_or_none(
        agent_name="ownership_risk_agent",
        system="너는 전세계약 소유권/계약권한 위험 분석 agent다. 허용된 tool 결과만 근거로 JSON만 반환한다.",
        prompt=f"""
너는 ownership_risk_agent다.
이미 허용된 tool들이 실행되었다:
- search_registry_rag_tool
- check_owner_landlord_match_tool
- check_proxy_contract_tool
- classify_ownership_risk_tool

PDF 계약서만으로 확정할 수 없는 권리관계는 단정하지 말고 missing_check로 남겨.

반환 JSON:
{{
  "risk_items": [
    {{
      "code": "OWNER_...",
      "title": "짧은 제목",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "score_delta": 10,
      "description": "왜 위험한지",
      "evidence": ["계약서 필드 또는 RAG 근거"],
      "required_action": "확인 조치"
    }}
  ],
  "missing_checks": [
    {{"status": "MISSING|REVIEW|FAIL", "check": "CHECK_CODE", "message": "필요 확인자료"}}
  ],
  "recommendations": ["확인 권장 방향"]
}}

fields:
{json.dumps(fields, ensure_ascii=False, default=str)}

rag_contexts:
{json.dumps(_context_summary(context_pack), ensure_ascii=False)}

owner_checks:
{json.dumps(owner_checks, ensure_ascii=False)}

proxy_checks:
{json.dumps(proxy_checks, ensure_ascii=False)}

rule_findings:
{json.dumps([asdict(item) for item in rule_risk_items], ensure_ascii=False)}
""".strip(),
    )
    if not data:
        return {"llm_used": False, "llm_note": "LLM unavailable; fallback kept as reference only"}
    return {
        "llm_used": True,
        "llm_note": "LLM synthesized ownership task result",
        "risk_items": _findings_from_llm(data.get("risk_items", []), "ownership_risk_agent:llm"),
        "missing_checks": [item for item in data.get("missing_checks", []) if isinstance(item, dict)],
        "recommendations": [str(item) for item in data.get("recommendations", []) if str(item).strip()],
    }


def _llm_json_or_none(*, agent_name: str, system: str, prompt: str) -> dict[str, Any] | None:
    try:
        raw = ollama_generate(prompt, system=system, temperature=0.0)
        data = extract_json_object(raw)
        return data if isinstance(data, dict) else None
    except (LLMUnavailable, json.JSONDecodeError, ValueError, TypeError):
        return None


def _findings_from_llm(items: Any, source: str) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    if not isinstance(items, list):
        return findings
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not title or not description:
            continue
        severity = str(item.get("severity") or "MEDIUM").upper()
        if severity not in {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            severity = "MEDIUM"
        findings.append(
            RiskFinding(
                code=str(item.get("code") or _slug_code(title)),
                title=title,
                severity=severity,  # type: ignore[arg-type]
                score_delta=max(0, min(_safe_int(item.get("score_delta"), 10), 25)),
                description=description,
                evidence=[str(value) for value in item.get("evidence", [])] if isinstance(item.get("evidence"), list) else [],
                required_action=str(item.get("required_action") or "") or None,
                source=source,
            )
        )
    return findings


def _context_summary(context_pack) -> list[dict[str, Any]]:
    return [
        {
            "source_id": context.source_id,
            "title": context.title,
            "doc_type": context.doc_type,
            "score": context.score,
            "text": context.text[:800],
        }
        for context in context_pack.contexts
    ]


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _slug_code(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value.upper())
    return f"LLM_{cleaned[:48].strip('_') or 'RISK'}"


def _registry_query(fields: dict[str, Any]) -> str:
    parts = [
        "전세계약 임대인 소유자 일치 대리인 위임장 등기부등본 신탁등기 근저당 권리관계 확인",
        f"주소={fields.get('address')}",
        f"임대인={fields.get('landlord')}",
        f"특약={fields.get('special_terms')}",
    ]
    return "\n".join(part for part in parts if part)


def _evidence_refs(context_pack) -> list[dict[str, Any]]:
    return [
        {
            "source_id": context.source_id,
            "title": context.title,
            "doc_type": context.doc_type,
            "score": context.score,
            "chunk_text": context.text[:500],
        }
        for context in context_pack.contexts
    ]
