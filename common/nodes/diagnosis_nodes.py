"""v7 LangGraph nodes for PDF-first contract diagnosis."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from common.agents.diagnosis_agents import (
    TASK_AGENT_MAP,
    run_contract_supervisor_agent,
    run_insurance_risk_agent,
    run_legal_basis_agent,
    run_market_risk_agent,
    run_ownership_risk_agent,
    run_required_check_agent,
    run_special_clause_agent,
)
from common.agents.review_supervisor_agent import review_agent_output
from common.schemas.diagnosis import DiagnosisState, TaskResult
from common.schemas.shared import AgentTrace, Claim, GraphContextItem, ReviewResult, ReviewStatus, RiskFinding
from common.tools.diagnosis_tools import search_legal_basis_rag
from common.tools.pdf_contract import (
    detect_contract_sections,
    extract_contract_fields,
    extract_pdf_text,
    ocr_pdf,
    validate_contract_fields,
    validate_pdf,
)
from common.tools.v7_contracts import merge_evidence_refs, merge_graph_context, normalize_evidence_refs


def contract_intake_node(state: DiagnosisState) -> DiagnosisState:
    validation = validate_pdf(state.get("contract_file"))
    errors = list(state.get("errors", [])) + validation.errors
    missing = list(state.get("missing_inputs", []))
    missing.extend(validation.warnings)
    return _merge(
        state,
        pdf_validation=validation,
        analysis_ready=validation.valid,
        errors=errors,
        missing_inputs=missing,
        trace=_trace("contract_intake", "validate_pdf_tool", {"contract_file": state.get("contract_file")}, asdict(validation)),
    )


def contract_parser_node(state: DiagnosisState) -> DiagnosisState:
    text, pages, confidence = extract_pdf_text(state.get("contract_file"))
    extraction_method = "extract_pdf_text_tool"
    if state.get("pdf_validation") and state["pdf_validation"].extension == ".pdf" and len(text.strip()) < 80:
        text, pages, confidence = ocr_pdf(state.get("contract_file"))
        extraction_method = "ocr_pdf_tool"
    sections = detect_contract_sections(text)
    return _merge(
        state,
        contract_text=text,
        page_texts=pages,
        ocr_confidence=confidence,
        contract_sections=sections,
        trace=_trace(
            "contract_parser",
            f"{extraction_method}+detect_contract_sections_tool",
            {"page_count": len(pages)},
            {"text_length": len(text), "has_special_terms_section": bool(sections.special_terms_text)},
        ),
    )


def contract_field_extractor_node(state: DiagnosisState) -> DiagnosisState:
    fields = extract_contract_fields(state.get("contract_text", ""), state.get("contract_sections"))
    validation = validate_contract_fields(fields)
    missing = list(state.get("missing_inputs", []))
    missing.extend(f"field:{name}" for name in validation.missing_fields)
    missing.extend(validation.warnings)
    return _merge(
        state,
        contract_fields=fields,
        field_validation=validation,
        missing_inputs=list(dict.fromkeys(missing)),
        trace=_trace("contract_field_extractor", "extract_contract_fields_tool+validate_contract_fields_tool", {}, {"fields": fields, "field_validation": asdict(validation)}),
    )


def contract_supervisor_node(state: DiagnosisState) -> DiagnosisState:
    next_state = _base_state(state)
    if "diagnosis_plan" not in next_state:
        field_validation = next_state.get("field_validation")
        missing = field_validation.missing_fields if field_validation else []
        plan = run_contract_supervisor_agent(next_state.get("contract_fields", {}), missing)
        next_state["diagnosis_plan"] = plan
        next_state["pending_tasks"] = list(plan.pending_tasks)
        next_state["completed_tasks"] = []
        next_state["review_count"] = 0
        next_state["max_review_count"] = 2
        next_state["agent_trace"].append(asdict(_trace("contract_supervisor_agent", "build_v7_task_queue", {"missing_fields": missing}, asdict(plan))))

    next_task = _next_pending_task(next_state)
    next_state["current_task"] = next_task
    next_state["current_agent"] = TASK_AGENT_MAP.get(next_task or "", None)
    next_state["review_count"] = 0
    next_state["agent_trace"].append({"agent": "contract_supervisor", "action": "select_next_task", "inputs": {}, "outputs": {"current_task": next_task, "current_agent": next_state.get("current_agent")}})
    return next_state


def special_clause_agent_node(state: DiagnosisState) -> DiagnosisState:
    return _store_task_result(state, run_special_clause_agent(state.get("contract_fields", {})))


def ownership_risk_agent_node(state: DiagnosisState) -> DiagnosisState:
    return _store_task_result(state, run_ownership_risk_agent(state.get("contract_fields", {}), state.get("registry_fields")))  # type: ignore[arg-type]


def market_risk_agent_node(state: DiagnosisState) -> DiagnosisState:
    return _store_task_result(state, run_market_risk_agent(state.get("contract_fields", {})))


def insurance_risk_agent_node(state: DiagnosisState) -> DiagnosisState:
    return _store_task_result(state, run_insurance_risk_agent(state.get("contract_fields", {})))


def required_check_agent_node(state: DiagnosisState) -> DiagnosisState:
    return _store_task_result(state, run_required_check_agent(state.get("contract_fields", {})))


def legal_basis_agent_node(state: DiagnosisState) -> DiagnosisState:
    return _store_task_result(state, run_legal_basis_agent(state.get("contract_fields", {}), state.get("task_results", {})))


def contract_review_node(state: DiagnosisState) -> DiagnosisState:
    task = state.get("current_task")
    result = state.get("task_results", {}).get(task or "")
    claims = result.claims if result else []
    evidence_refs = result.evidence_refs if result else []
    graph_context = result.graph_context if result else []
    review = review_agent_output(
        current_task=task,
        current_agent=state.get("current_agent"),
        claims=claims,
        evidence_refs=evidence_refs,
        graph_context=graph_context,
        draft_answer="\n".join(result.legal_points) if result else "",
        mode="diagnosis",
    )
    task_results = dict(state.get("task_results", {}))
    if result:
        result.review_status = review.status.value
        task_results[result.task] = result
    review_count = int(state.get("review_count", 0))
    if review.status != ReviewStatus.PASS:
        review_count += 1
    completed = list(state.get("completed_tasks", []))
    if review.status == ReviewStatus.PASS and task and task not in completed:
        completed.append(task)
    return _merge(
        state,
        review_result=review,
        review_count=review_count,
        completed_tasks=completed,
        task_results=task_results,
        trace=_trace("contract_review_node", "structured_review", {"task": task}, asdict(review)),
    )


def extra_rag_search_node(state: DiagnosisState) -> DiagnosisState:
    task = state.get("current_task")
    result = state.get("task_results", {}).get(task or "")
    query = state.get("review_result").missing_evidence_query if state.get("review_result") else None  # type: ignore[union-attr]
    pack = search_legal_basis_rag(query or task or "전세계약 위험 추가 근거", top_k=5)
    additional = normalize_evidence_refs([
        {
            "source_id": context.source_id,
            "title": context.title,
            "doc_type": context.doc_type,
            "score": context.score,
            "chunk_text": context.text,
            "metadata": context.metadata,
        }
        for context in pack.contexts
    ])
    task_results = dict(state.get("task_results", {}))
    if result:
        result.evidence_refs = merge_evidence_refs(result.evidence_refs, additional, current_task=task)
        result.graph_context = merge_graph_context(result.graph_context, pack.graph_context)
        result.status = "PARTIAL"
        task_results[result.task] = result
    return _merge(state, task_results=task_results, trace=_trace("extra_rag_search", "merge_evidence_then_retry_agent", {"task": task}, {"added": len(additional)}))


def graph_context_node(state: DiagnosisState) -> DiagnosisState:
    task = state.get("current_task")
    result = state.get("task_results", {}).get(task or "")
    query = state.get("review_result").graph_context_query if state.get("review_result") else None  # type: ignore[union-attr]
    pack = search_legal_basis_rag(query or task or "전세계약 관계 그래프 context", top_k=5)
    task_results = dict(state.get("task_results", {}))
    if result:
        result.graph_context = merge_graph_context(result.graph_context, pack.graph_context)
        result.status = "PARTIAL"
        task_results[result.task] = result
    return _merge(state, task_results=task_results, trace=_trace("graph_context_node", "merge_graph_context_then_retry_or_review", {"task": task}, {"graph_context_added": len(pack.graph_context)}))


def safe_contract_fallback_node(state: DiagnosisState) -> DiagnosisState:
    level = _fallback_level(state)
    task = state.get("current_task")
    completed = list(state.get("completed_tasks", []))
    if task and task not in completed:
        completed.append(task)
    safe_fallback = {
        "status": "SAFE_FALLBACK",
        "fallback_level": level,
        "reason": state.get("review_result").reason if state.get("review_result") else "review could not pass safely",  # type: ignore[union-attr]
        "recommended_next_step": _fallback_next_step(level),
        "task": task,
    }
    return _merge(
        state,
        fallback_level=level,
        safe_fallback=safe_fallback,
        completed_tasks=completed,
        trace=_trace("safe_contract_fallback", "mark_task_fallback", {"task": task}, safe_fallback),
    )


def risk_judge_node(state: DiagnosisState) -> DiagnosisState:
    findings: list[RiskFinding] = []
    blocked_tasks: list[str] = []
    claims: list[Claim] = []
    evidence_refs: list[dict[str, Any]] = []
    graph_context: list[GraphContextItem] = []
    legal_points: list[str] = []
    for task, result in state.get("task_results", {}).items():
        if result.status == "FAILED":
            blocked_tasks.append(task)
            continue
        findings.extend(result.risk_items)
        claims.extend(result.claims)
        evidence_refs = merge_evidence_refs(evidence_refs, result.evidence_refs, current_task=task)
        graph_context = merge_graph_context(graph_context, result.graph_context)
        legal_points.extend(result.legal_points)
    score = min(100, sum(max(0, finding.score_delta) for finding in findings))
    if blocked_tasks and score < 40:
        score = 40
    level = "CRITICAL" if score >= 75 else ("HIGH" if score >= 50 else ("MEDIUM" if score >= 25 else "LOW"))
    return _merge(
        state,
        risk_findings=findings,
        risk_score=score,
        risk_level=level,
        claims=claims,
        evidence_refs=evidence_refs,
        graph_context=graph_context,
        legal_points=legal_points,
        trace=_trace("risk_judge", "aggregate_agent_results", {"task_count": len(state.get("task_results", {}))}, {"risk_score": score, "risk_level": level, "blocked_tasks": blocked_tasks}),
    )


def report_writer_node(state: DiagnosisState) -> DiagnosisState:
    task_results = state.get("task_results", {})
    recommendations: list[str] = []
    missing_checks: list[dict[str, Any]] = []
    for result in task_results.values():
        recommendations.extend(result.recommendations)
        missing_checks.extend(result.missing_checks)
    report_trace = _trace("report_writer", "format_v7_diagnosis_report", {}, {"task_count": len(task_results)})
    full_trace = list(state.get("agent_trace", [])) + [asdict(report_trace)]
    report = {
        "title": "전세계약 PDF 위험 진단 리포트",
        "disclaimer": "본 결과는 법률 자문이 아니라 계약 전 위험 확인을 돕는 보조 정보입니다.",
        "diagnosis_status": _diagnosis_status(state),
        "contract_file": state.get("contract_file"),
        "contract_source": "uploaded_file" if state.get("contract_file") else "mock_contract",
        "risk_score": state.get("risk_score", 0),
        "risk_level": state.get("risk_level", "UNKNOWN"),
        "fallback_level": state.get("fallback_level"),
        "safe_fallback": state.get("safe_fallback", {}),
        "contract_fields": state.get("contract_fields", {}),
        "diagnosis_plan": _to_dict(state.get("diagnosis_plan")),
        "task_results": {key: _to_dict(value) for key, value in task_results.items()},
        "claims": [_to_dict(item) for item in state.get("claims", [])],
        "legal_points": state.get("legal_points", []),
        "findings": [asdict(finding) for finding in state.get("risk_findings", [])],
        "recommended_revisions": list(dict.fromkeys(item for item in recommendations if item)),
        "next_checks": list(dict.fromkeys([item.get("message", "") for item in missing_checks if item.get("message")])),
        "missing_checks": missing_checks,
        "evidence_refs": state.get("evidence_refs", []),
        "graph_context": [_to_dict(item) for item in state.get("graph_context", [])],
        "agent_trace": full_trace,
    }
    return _merge(state, report=report, trace=report_trace)


def route_after_supervisor(state: DiagnosisState) -> str:
    task = state.get("current_task")
    if not task:
        return "judge"
    return task


def route_after_review(state: DiagnosisState) -> str:
    review = state.get("review_result")
    status = review.status if review else ReviewStatus.FAIL
    if status == ReviewStatus.PASS:
        return "supervisor"
    if int(state.get("review_count", 0)) >= int(state.get("max_review_count", 2)):
        return "fallback"
    if status == ReviewStatus.NEED_MORE_EVIDENCE:
        return "extra_rag"
    if status == ReviewStatus.NEED_GRAPH_CONTEXT:
        return "graph_context"
    if status == ReviewStatus.REVISION_REQUIRED:
        return state.get("current_task") or "fallback"
    return "fallback"


def route_after_extra_rag(state: DiagnosisState) -> str:
    return state.get("current_task") or "fallback"


def route_after_graph_context(state: DiagnosisState) -> str:
    return state.get("current_task") or "fallback"


def _store_task_result(state: DiagnosisState, result: TaskResult) -> DiagnosisState:
    task_results = dict(state.get("task_results", {}))
    task_results[result.task] = result
    return _merge(
        state,
        current_task=result.task,
        current_agent=result.agent,
        task_results=task_results,
        trace=_trace(result.agent, "run_v7_task_agent", {"task": result.task}, _task_summary(result)),
    )


def _next_pending_task(state: DiagnosisState) -> str | None:
    completed = set(state.get("completed_tasks", []))
    for task in state.get("pending_tasks", []):
        if task not in completed:
            return task
    return None


def _diagnosis_status(state: DiagnosisState) -> dict[str, Any]:
    task_results = state.get("task_results", {})
    blocked_reasons: list[str] = []
    for task in state.get("pending_tasks", []):
        result = task_results.get(task)
        if result is None:
            blocked_reasons.append(f"{task} did not run")
        elif result.status in {"FAILED", "NOT_IMPLEMENTED"}:
            blocked_reasons.append(f"{task} status={result.status}")
    if state.get("fallback_level"):
        blocked_reasons.append(f"safe fallback used: {state.get('fallback_level')}")
    return {
        "complete": not blocked_reasons and not state.get("fallback_level"),
        "blocked_reasons": blocked_reasons,
        "fallback_level": state.get("fallback_level"),
        "fallback_policy": "SAFE_FALLBACK includes fallback_level when review cannot pass.",
    }


def _fallback_level(state: DiagnosisState) -> str:
    task = str(state.get("current_task") or "")
    if task in {"ownership_risk", "market_risk", "insurance_risk"}:
        return "HIGH"
    if task in {"legal_basis", "required_check"}:
        return "MEDIUM"
    return "LOW"


def _base_state(state: DiagnosisState) -> DiagnosisState:
    next_state: DiagnosisState = dict(state)
    next_state.setdefault("agent_trace", [])
    next_state.setdefault("errors", [])
    next_state.setdefault("missing_inputs", [])
    next_state.setdefault("context_packs", {})
    next_state.setdefault("task_results", {})
    next_state.setdefault("pending_tasks", [])
    next_state.setdefault("completed_tasks", [])
    next_state.setdefault("review_count", 0)
    next_state.setdefault("max_review_count", 2)
    next_state.setdefault("claims", [])
    next_state.setdefault("legal_points", [])
    next_state.setdefault("evidence_refs", [])
    next_state.setdefault("graph_context", [])
    next_state.setdefault("safe_fallback", {})
    return next_state


def _fallback_next_step(level: str) -> str:
    if level == "HIGH":
        return "핵심 근거 검증이 부족하므로 추가 서류 확인 또는 전문가 상담을 우선 권장합니다."
    if level == "MEDIUM":
        return "부족한 근거 자료를 보완한 뒤 해당 위험 항목을 다시 검토해야 합니다."
    return "일부 근거가 부족하므로 확인 가능한 자료를 추가로 대조해야 합니다."


def _task_summary(result: TaskResult) -> dict[str, Any]:
    return {
        "task": result.task,
        "status": result.status,
        "claim_count": len(result.claims),
        "legal_point_count": len(result.legal_points),
        "risk_count": len(result.risk_items),
        "recommendation_count": len(result.recommendations),
        "evidence_count": len(result.evidence_refs),
        "graph_context_count": len(result.graph_context),
        "missing_check_count": len(result.missing_checks),
    }


def _merge(state: DiagnosisState, *, trace: AgentTrace | None = None, **updates: Any) -> DiagnosisState:
    next_state: DiagnosisState = _base_state(state)
    next_state.update(updates)
    if trace:
        traces = list(next_state.get("agent_trace", []))
        traces.append(asdict(trace))
        next_state["agent_trace"] = traces
    return next_state


def _trace(agent: str, action: str, inputs: dict[str, Any], outputs: dict[str, Any]) -> AgentTrace:
    return AgentTrace(agent=agent, action=action, inputs=inputs, outputs=outputs)


def _to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_dict(item) for item in value]
    return value
