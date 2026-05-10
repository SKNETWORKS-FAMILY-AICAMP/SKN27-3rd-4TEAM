"""LangGraph node functions for the jeonse diagnosis workflow."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from common.schemas.diagnosis import DiagnosisState
from common.schemas.shared import AgentTrace, ContextPack, RiskFinding
from common.tools.adaptive_rag import adaptive_rag
from common.tools.document import extract_contract_fields, parse_contract_file
from common.tools.market import analyze_market


def contract_intake_agent(state: DiagnosisState) -> DiagnosisState:
    file_path = state.get("contract_file")
    missing = list(state.get("missing_inputs", []))
    errors = list(state.get("errors", []))

    if file_path:
        suffix = Path(file_path).suffix.lower()
        if suffix not in {".pdf", ".txt", ".md", ".png", ".jpg", ".jpeg"}:
            errors.append(f"지원하지 않는 계약서 형식입니다: {suffix}")
    else:
        missing.append("contract_file: 테스트용 mock 계약서로 진행")

    return _merge(state, analysis_ready=not errors, missing_inputs=missing, errors=errors, trace=_trace("Contract Intake Agent", "validate_contract_input", {"contract_file": file_path}, {"analysis_ready": not errors}))


def contract_parser_agent(state: DiagnosisState) -> DiagnosisState:
    text, pages, confidence = parse_contract_file(state.get("contract_file"))
    return _merge(state, contract_text=text, page_texts=pages, ocr_confidence=confidence, trace=_trace("Contract Parser Agent", "parse_pdf_or_text", {"contract_file": state.get("contract_file")}, {"text_length": len(text), "pages": len(pages)}))


def contract_field_extractor_agent(state: DiagnosisState) -> DiagnosisState:
    fields = extract_contract_fields(state.get("contract_text", ""))
    return _merge(state, contract_fields=fields, trace=_trace("Contract Field Extractor Agent", "extract_structured_fields", {}, {"fields": fields}))


def special_clause_analyzer_agent(state: DiagnosisState) -> DiagnosisState:
    fields = state.get("contract_fields", {})
    terms = fields.get("special_terms") or []
    query = "\n".join(str(term) for term in terms) or state.get("contract_text", "")[:1500]
    context_pack = adaptive_rag("special_clause_analysis", query, filters={"doc_type": ["checklist", "guide", "law", "case"]}, top_k=5)

    findings: list[RiskFinding] = []
    revisions: list[str] = []
    missing_defensive: list[RiskFinding] = []

    joined = "\n".join(str(term) for term in terms)
    risky_patterns = [
        ("CLAUSE_REPAIR_ALL", "수리비 전액 임차인 부담", "수리비를 임차인이 전액 부담하는 문구는 통상적인 사용 손모까지 임차인에게 전가할 수 있어 위험합니다.", ["수리비", "전액", "임차인"]),
        ("CLAUSE_LATE_RETURN", "보증금 반환 지연 가능 특약", "보증금 반환 시점을 과도하게 늦추는 문구는 반환 위험을 키울 수 있습니다.", ["보증금", "반환", "이후"]),
        ("CLAUSE_NO_OWNER_RESP", "임대인 책임 제한 특약", "권리 변동이나 하자에 대한 임대인 책임을 배제하는 문구는 위험합니다.", ["책임지지", "권리", "변동"]),
    ]
    for code, title, description, tokens in risky_patterns:
        if all(token in joined for token in tokens):
            findings.append(RiskFinding(code=code, title=title, severity="HIGH", score_delta=15, description=description, evidence=terms, required_action="특약 삭제 또는 책임 범위를 명확히 제한하는 수정 문구를 요청하세요.", source="special_clause_analyzer"))
            revisions.append(f"{title}: 임차인의 통상 사용으로 인한 손모는 제외하고, 임대인의 수선 의무와 보증금 반환 기한을 명확히 쓰는 방향으로 수정 권장")

    if "잔금" not in joined or "권리변동" not in joined:
        missing_defensive.append(RiskFinding(code="MISSING_NO_NEW_LIEN", title="잔금 전후 권리변동 금지 특약 부족", severity="MEDIUM", score_delta=10, description="잔금일 전후 임대인이 근저당권 등 새로운 권리를 설정하지 않는다는 방어 특약이 보이지 않습니다.", required_action="잔금일 다음날까지 근저당권 등 제한물권을 설정하지 않는다는 특약을 추가 검토하세요.", source="special_clause_analyzer"))

    packs = dict(state.get("context_packs", {}))
    packs["special_clause_analysis"] = context_pack
    return _merge(state, context_packs=packs, clause_findings=findings, missing_defensive_clauses=missing_defensive, recommended_revisions=revisions, trace=_trace("Special Clause Analyzer Agent", "analyze_special_terms_with_rag", {"term_count": len(terms)}, {"finding_count": len(findings), "missing_defensive_count": len(missing_defensive)}))


def market_analyzer_agent(state: DiagnosisState) -> DiagnosisState:
    analysis, findings = analyze_market(state.get("contract_fields", {}))
    return _merge(state, market_analysis=analysis, market_findings=findings, trace=_trace("Market Analyzer Agent", "compare_jeonse_and_sale_data", asdict(analysis), {"finding_count": len(findings)}))


def required_check_analyzer_agent(state: DiagnosisState) -> DiagnosisState:
    fields = state.get("contract_fields", {})
    query = f"전세계약서만 입력된 상태에서 추가 확인이 필요한 위험 항목. 주소={fields.get('address')} 유형={fields.get('housing_type')}"
    context_pack = adaptive_rag("required_check_analysis", query, filters={"doc_type": ["checklist", "guide", "law"]}, top_k=5)

    findings = [
        RiskFinding("REQUIRED_REGISTRY", "등기부 권리관계 확인 필요", "HIGH", 20, "계약서만으로는 근저당권, 압류, 가압류, 신탁 등 권리관계를 확인할 수 없습니다.", required_action="계약 직전 등기부등본 갑구/을구를 확인하세요.", source="required_check_analyzer"),
        RiskFinding("REQUIRED_OWNER_MATCH", "임대인과 소유자 일치 확인 필요", "HIGH", 15, "계약서상 임대인이 실제 등기부 소유자인지 계약서만으로 확정할 수 없습니다.", required_action="등기부 소유자와 신분증/위임장을 대조하세요.", source="required_check_analyzer"),
        RiskFinding("REQUIRED_TAX", "체납 세금 확인 필요", "MEDIUM", 10, "국세/지방세 체납은 보증금 회수 위험과 연결될 수 있으나 계약서만으로 알 수 없습니다.", required_action="납세증명서 또는 관련 확인 절차를 요청하세요.", source="required_check_analyzer"),
    ]
    if fields.get("housing_type") in {"단독다가구", "단독", "다가구"}:
        findings.append(RiskFinding("REQUIRED_SENIOR_TENANTS", "다가구 선순위 보증금 확인 필요", "HIGH", 20, "단독/다가구는 다른 세입자의 선순위 보증금 규모가 중요하지만 계약서만으로 확인하기 어렵습니다.", required_action="전입세대확인서, 확정일자 부여 현황, 임대인 고지 내용을 확인하세요.", source="required_check_analyzer"))

    packs = dict(state.get("context_packs", {}))
    packs["required_check_analysis"] = context_pack
    return _merge(state, context_packs=packs, required_check_findings=findings, trace=_trace("Required Check Analyzer Agent", "list_contract_only_unknown_risks", {}, {"finding_count": len(findings)}))


def risk_judge_agent(state: DiagnosisState) -> DiagnosisState:
    findings: list[RiskFinding] = []
    findings.extend(state.get("clause_findings", []))
    findings.extend(state.get("missing_defensive_clauses", []))
    findings.extend(state.get("market_findings", []))
    findings.extend(state.get("required_check_findings", []))

    score = min(100, sum(max(0, finding.score_delta) for finding in findings))
    if score >= 75:
        level = "CRITICAL"
    elif score >= 50:
        level = "HIGH"
    elif score >= 25:
        level = "MEDIUM"
    else:
        level = "LOW"

    return _merge(state, risk_findings=findings, risk_score=score, risk_level=level, trace=_trace("Risk Judge Agent", "aggregate_rule_based_score", {"finding_count": len(findings)}, {"risk_score": score, "risk_level": level}))


def report_writer_agent(state: DiagnosisState) -> DiagnosisState:
    context_pack = adaptive_rag("report_generation", "전세계약 위험 진단 결과 리포트 작성", filters={"doc_type": ["guide", "checklist"]}, top_k=3)
    packs = dict(state.get("context_packs", {}))
    packs["report_generation"] = context_pack

    report_trace = _trace("Report Writer Agent", "compose_user_report", {}, {"sections": ["title", "disclaimer", "risk_score", "risk_level", "contract_fields", "market_analysis", "findings", "recommended_revisions", "next_checks", "rag_references", "agent_trace"]})
    full_trace = list(state.get("agent_trace", [])) + [report_trace]

    report = {
        "title": "전세계약 위험 진단 리포트",
        "disclaimer": "본 결과는 법률 자문이 아니라 계약 전 위험 확인을 돕는 보조 정보입니다.",
        "risk_score": state.get("risk_score", 0),
        "risk_level": state.get("risk_level", "UNKNOWN"),
        "contract_fields": state.get("contract_fields", {}),
        "market_analysis": asdict(state.get("market_analysis")) if state.get("market_analysis") else None,
        "findings": [asdict(finding) for finding in state.get("risk_findings", [])],
        "recommended_revisions": state.get("recommended_revisions", []),
        "next_checks": [finding.required_action for finding in state.get("risk_findings", []) if finding.required_action],
        "rag_references": _summarize_context_packs(packs),
        "agent_trace": [asdict(trace) for trace in full_trace],
    }
    return _merge(state, context_packs=packs, report=report, trace=report_trace)


def _summarize_context_packs(packs: dict[str, ContextPack]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for task_type, pack in packs.items():
        for context in pack.contexts:
            refs.append({"task_type": task_type, "title": context.title, "doc_type": context.doc_type, "source_id": context.source_id, "score": context.score})
    return refs


def _merge(state: DiagnosisState, *, trace: AgentTrace | None = None, **updates: Any) -> DiagnosisState:
    next_state: DiagnosisState = dict(state)
    next_state.update(updates)
    if trace:
        traces = list(next_state.get("agent_trace", []))
        traces.append(trace)
        next_state["agent_trace"] = traces
    return next_state


def _trace(agent: str, action: str, inputs: dict[str, Any], outputs: dict[str, Any]) -> AgentTrace:
    return AgentTrace(agent=agent, action=action, inputs=inputs, outputs=outputs)



