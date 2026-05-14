"""v7 diagnosis agents with explicit task scope, evidence, claims, and status."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from common.schemas.diagnosis import DiagnosisPlan, TaskResult
from common.schemas.shared import Claim, ContextPack, RiskFinding
from common.tools.diagnosis_tools import (
    check_owner_landlord_match,
    check_proxy_contract,
    classify_clause_risk,
    classify_ownership_risk,
    compare_standard_contract,
    search_insurance_rag,
    search_legal_basis_rag,
    search_market_rag,
    search_registry_rag,
    search_required_check_rag,
    search_special_clause_rag,
)
from common.tools.llm import LLMUnavailable, extract_json_object, llm_generate
from common.tools.v7_contracts import graph_context_to_dicts

TASK_AGENT_MAP: dict[str, str] = {
    "special_clause": "special_clause_agent",
    "ownership_risk": "ownership_risk_agent",
    "market_risk": "market_risk_agent",
    "insurance_risk": "insurance_risk_agent",
    "required_check": "required_check_agent",
    "legal_basis": "legal_basis_agent",
}


def run_contract_supervisor_agent(fields: dict[str, Any], validation_missing: list[str]) -> DiagnosisPlan:
    """Create a v7 task queue from extracted PDF fields."""
    special_terms = fields.get("special_terms") or []
    pending_tasks: list[str] = []
    reasons: list[str] = []

    if special_terms:
        pending_tasks.append("special_clause")
        reasons.append("special terms exist")
    pending_tasks.append("ownership_risk")
    reasons.append("registry/owner authority cannot be proven by contract PDF alone")

    if fields.get("address") or fields.get("deposit_amount"):
        pending_tasks.append("market_risk")
        reasons.append("address/deposit fields allow market risk check")
    else:
        reasons.append("market risk still tracked as missing-input task")
        pending_tasks.append("market_risk")

    pending_tasks.extend(["insurance_risk", "required_check", "legal_basis"])
    if validation_missing:
        reasons.append(f"missing fields: {', '.join(validation_missing)}")

    pending_tasks = list(dict.fromkeys(pending_tasks))
    return DiagnosisPlan(
        run_special_clause="special_clause" in pending_tasks,
        run_ownership_risk="ownership_risk" in pending_tasks,
        run_market_risk="market_risk" in pending_tasks,
        run_insurance_risk="insurance_risk" in pending_tasks,
        run_required_check="required_check" in pending_tasks,
        run_legal_basis="legal_basis" in pending_tasks,
        reasons=reasons,
        skipped_agents=[],
        pending_tasks=pending_tasks,
        llm_required=False,
        llm_used=False,
        status="PLANNED",
    )


def run_special_clause_agent(fields: dict[str, Any]) -> TaskResult:
    special_terms = [str(term) for term in fields.get("special_terms") or [] if str(term).strip()]
    query = "\n".join(special_terms) or "전세계약 특약 위험 불공정 특약 표준계약서"
    pack = search_special_clause_rag(query, top_k=5)
    comparisons = compare_standard_contract(special_terms)
    risk_items = classify_clause_risk(special_terms, comparisons) if special_terms else []
    recommendations = [item.required_action for item in risk_items if item.required_action]
    legal_points = _legal_points_from_pack(pack, fallback=["특약은 표준계약서와 비교해 임차인에게 불리한지 확인해야 합니다."])
    return _task_result(
        task="special_clause",
        agent="special_clause_agent",
        pack=pack,
        risk_items=risk_items,
        recommendations=recommendations,
        legal_points=legal_points,
        status="COMPLETE" if special_terms else "PARTIAL",
        metadata={"standard_contract_comparisons": comparisons},
    )


def run_ownership_risk_agent(fields: dict[str, Any], registry_fields: dict[str, Any] | None = None) -> TaskResult:
    query = _registry_query(fields)
    pack = search_registry_rag(query, top_k=5)
    owner_checks = check_owner_landlord_match(fields, registry_fields)
    proxy_checks = check_proxy_contract(fields)
    risk_items = classify_ownership_risk(fields, owner_checks, proxy_checks)
    missing_checks = [check for check in owner_checks + proxy_checks if check.get("status") in {"MISSING", "REVIEW", "FAIL"}]
    recommendations = [item.required_action for item in risk_items if item.required_action]
    legal_points = _legal_points_from_pack(pack, fallback=["등기부등본, 소유자, 대리권 자료를 계약 전 확인해야 합니다."])
    return _task_result(
        task="ownership_risk",
        agent="ownership_risk_agent",
        pack=pack,
        risk_items=risk_items,
        recommendations=recommendations,
        legal_points=legal_points,
        missing_checks=missing_checks,
        status="COMPLETE" if pack.contexts else "PARTIAL",
        metadata={"owner_checks": owner_checks, "proxy_checks": proxy_checks},
    )


def run_market_risk_agent(fields: dict[str, Any]) -> TaskResult:
    query = f"전세가율 깡통전세 시세 위험 주소={fields.get('address')} 보증금={fields.get('deposit_amount')}"
    pack = search_market_rag(query, top_k=5)
    risk_items: list[RiskFinding] = []
    if not fields.get("address") or not fields.get("deposit_amount"):
        risk_items.append(_finding("MARKET_INPUT_MISSING", "전세가율 판단 입력 부족", "MEDIUM", 10, "주소 또는 보증금 정보가 부족해 전세가율을 확정하기 어렵습니다.", "주소, 면적, 보증금, 주변 매매가 자료를 확인하세요.", "market_risk_agent"))
    legal_points = _legal_points_from_pack(pack, fallback=["전세가율과 주변 매매가를 함께 확인해야 깡통전세 위험을 줄일 수 있습니다."])
    return _task_result("market_risk", "market_risk_agent", pack, risk_items, [item.required_action for item in risk_items if item.required_action], legal_points, status="PARTIAL")


def run_insurance_risk_agent(fields: dict[str, Any]) -> TaskResult:
    query = f"전세보증보험 HUG HF SGI 가입요건 거절사유 주소={fields.get('address')} 보증금={fields.get('deposit_amount')}"
    pack = search_insurance_rag(query, top_k=5)
    risk_items = [
        _finding("INSURANCE_ELIGIBILITY_UNVERIFIED", "보증보험 가입 가능성 미확인", "MEDIUM", 10, "계약서만으로 HUG/HF/SGI 보증보험 가입 가능 여부를 확정할 수 없습니다.", "보증기관 가입요건과 선순위권리, 주택유형, 보증금 한도를 확인하세요.", "insurance_risk_agent")
    ]
    legal_points = _legal_points_from_pack(pack, fallback=["보증보험은 기관별 가입요건과 선순위권리 조건을 함께 확인해야 합니다."])
    return _task_result("insurance_risk", "insurance_risk_agent", pack, risk_items, [item.required_action for item in risk_items if item.required_action], legal_points, status="PARTIAL")


def run_required_check_agent(fields: dict[str, Any]) -> TaskResult:
    query = "전세계약 필수 확인 서류 등기부등본 건축물대장 납세증명서 신분증 위임장 전입신고 확정일자"
    pack = search_required_check_rag(query, top_k=5)
    missing_checks = [
        {"status": "REVIEW", "check": "REGISTRY", "message": "등기부등본 최신본 확인 필요"},
        {"status": "REVIEW", "check": "TAX_ARREARS", "message": "임대인 납세증명서 또는 체납 여부 확인 필요"},
        {"status": "REVIEW", "check": "MOVE_IN_FIXED_DATE", "message": "전입신고와 확정일자 취득 계획 확인 필요"},
    ]
    risk_items = [
        _finding("REQUIRED_CHECKS_UNVERIFIED", "필수 확인자료 미확인", "MEDIUM", 10, "계약서만으로 필수 확인자료 제출 여부를 확정할 수 없습니다.", "등기부등본, 건축물대장, 납세증명서, 신분증/위임장 확인 절차를 완료하세요.", "required_check_agent")
    ]
    legal_points = _legal_points_from_pack(pack, fallback=["계약 전 필수 확인자료는 체크리스트로 관리해야 합니다."])
    return _task_result("required_check", "required_check_agent", pack, risk_items, [item.required_action for item in risk_items if item.required_action], legal_points, missing_checks=missing_checks, status="PARTIAL")


def run_legal_basis_agent(fields: dict[str, Any], task_results: dict[str, TaskResult] | None = None) -> TaskResult:
    prior = task_results or {}
    query = " ".join([result.task + " " + " ".join(result.legal_points) for result in prior.values()]) or "전세계약 위험 법령 판례 공공기관 가이드"
    pack = search_legal_basis_rag(query, top_k=7)
    legal_points = _legal_points_from_pack(pack, fallback=["위험 판단은 관련 법령, 판례, 공공기관 가이드를 함께 근거로 삼아야 합니다."])
    claims = _claims_from_pack("legal_basis", legal_points, pack)
    return _task_result("legal_basis", "legal_basis_agent", pack, [], [], legal_points, claims=claims, status="COMPLETE" if pack.contexts else "PARTIAL")


def _task_result(
    task: str,
    agent: str,
    pack: ContextPack,
    risk_items: list[RiskFinding],
    recommendations: list[str],
    legal_points: list[str],
    *,
    claims: list[Claim] | None = None,
    missing_checks: list[dict[str, Any]] | None = None,
    status: str = "COMPLETE",
    metadata: dict[str, Any] | None = None,
) -> TaskResult:
    evidence_refs = _evidence_refs(pack)
    resolved_claims = claims or _claims_from_pack(task, legal_points, pack)
    if not evidence_refs and status == "COMPLETE":
        status = "PARTIAL"
    return TaskResult(
        task=task,
        agent=agent,
        status=status,  # type: ignore[arg-type]
        claims=resolved_claims,
        legal_points=legal_points,
        risk_items=risk_items,
        recommendations=list(dict.fromkeys(item for item in recommendations if item)),
        evidence_refs=evidence_refs,
        graph_context=pack.graph_context,
        missing_checks=missing_checks or [],
        metadata={
            "context_quality": pack.quality.reason,
            "context_score": pack.quality.score,
            "result_status": status,
            **(metadata or {}),
        },
    )


def _claims_from_pack(task: str, legal_points: list[str], pack: ContextPack) -> list[Claim]:
    evidence_ids = [context.source_id for context in pack.contexts[:5]]
    graph_ids = [f"{item.node}|{item.relation}|{item.target}" for item in pack.graph_context[:5]]
    claims: list[Claim] = []
    for index, point in enumerate(legal_points[:3], 1):
        claims.append(
            Claim(
                claim_id=f"{task}_claim_{index}",
                task=task,
                text=point,
                evidence_ids=evidence_ids,
                graph_context_ids=graph_ids,
                confidence="MEDIUM" if evidence_ids or graph_ids else "LOW",
            )
        )
    return claims


def _legal_points_from_pack(pack: ContextPack, *, fallback: list[str]) -> list[str]:
    points = [context.text[:180].strip() for context in pack.contexts[:3] if context.text.strip()]
    return points or fallback


def _evidence_refs(pack: ContextPack) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": context.source_id,
            "source_id": context.source_id,
            "title": context.title,
            "table": context.metadata.get("table", ""),
            "doc_type": context.doc_type,
            "source_type": context.metadata.get("source_type", ""),
            "score": context.score,
            "snippet": context.text[:700],
            "chunk_text": context.text[:1200],
            "metadata": context.metadata,
        }
        for context in pack.contexts
    ]


def _finding(code: str, title: str, severity: str, score_delta: int, description: str, action: str, source: str) -> RiskFinding:
    return RiskFinding(
        code=code,
        title=title,
        severity=severity,  # type: ignore[arg-type]
        score_delta=score_delta,
        description=description,
        required_action=action,
        source=source,
    )


def _registry_query(fields: dict[str, Any]) -> str:
    parts = [
        "전세계약 임대인 소유자 일치 대리인 위임장 등기부등본 신탁등기 근저당 권리관계 확인",
        f"주소={fields.get('address')}",
        f"임대인={fields.get('landlord')}",
        f"특약={fields.get('special_terms')}",
    ]
    return "\n".join(part for part in parts if part)
