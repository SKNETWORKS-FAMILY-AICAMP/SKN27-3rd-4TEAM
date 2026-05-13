"""LangGraph nodes for the redesigned PDF-first diagnosis workflow."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from common.agents.diagnosis_agents import (
    run_contract_supervisor_agent,
    run_ownership_risk_agent,
    run_special_clause_agent,
)
from common.schemas.diagnosis import DiagnosisState
from common.schemas.shared import AgentTrace, RiskFinding
from common.tools.pdf_contract import (
    detect_contract_sections,
    extract_contract_fields,
    extract_pdf_text,
    ocr_pdf,
    validate_contract_fields,
    validate_pdf,
)


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
        trace=_trace(
            "contract_field_extractor",
            "extract_contract_fields_tool+validate_contract_fields_tool",
            {},
            {"fields": fields, "field_validation": asdict(validation)},
        ),
    )


def contract_supervisor_node(state: DiagnosisState) -> DiagnosisState:
    field_validation = state.get("field_validation")
    missing = field_validation.missing_fields if field_validation else []
    plan = run_contract_supervisor_agent(state.get("contract_fields", {}), missing)
    return _merge(
        state,
        diagnosis_plan=plan,
        trace=_trace("contract_supervisor_agent", "build_diagnosis_plan_tool", {"missing_fields": missing}, asdict(plan)),
    )


def special_clause_agent_node(state: DiagnosisState) -> DiagnosisState:
    result = run_special_clause_agent(state.get("contract_fields", {}))
    task_results = dict(state.get("task_results", {}))
    task_results[result.task] = result
    return _merge(
        state,
        task_results=task_results,
        trace=_trace("special_clause_agent", "run_allowed_tools", {"tool_scope": result.metadata.get("allowed_tools")}, _task_summary(result)),
    )


def ownership_risk_agent_node(state: DiagnosisState) -> DiagnosisState:
    result = run_ownership_risk_agent(state.get("contract_fields", {}), state.get("registry_fields"))  # type: ignore[arg-type]
    task_results = dict(state.get("task_results", {}))
    task_results[result.task] = result
    return _merge(
        state,
        task_results=task_results,
        trace=_trace("ownership_risk_agent", "run_allowed_tools", {"tool_scope": result.metadata.get("allowed_tools")}, _task_summary(result)),
    )


def risk_judge_node(state: DiagnosisState) -> DiagnosisState:
    findings: list[RiskFinding] = []
    incomplete_tasks: list[str] = []
    plan = state.get("diagnosis_plan")
    if plan and (plan.status != "PLANNED" or not plan.llm_used):
        return _merge(
            state,
            risk_findings=[],
            risk_score=0,
            risk_level="UNKNOWN",
            trace=_trace(
                "risk_judge",
                "block_final_scoring_without_llm_supervisor_plan",
                {"plan_status": plan.status, "plan_llm_used": plan.llm_used},
                {"risk_score": 0, "risk_level": "UNKNOWN", "reason": "LLM supervisor plan required"},
            ),
        )
    for result in state.get("task_results", {}).values():
        if result.metadata.get("result_status") != "COMPLETE":
            incomplete_tasks.append(result.task)
        findings.extend(result.risk_items)
    if incomplete_tasks:
        return _merge(
            state,
            risk_findings=[],
            risk_score=0,
            risk_level="UNKNOWN",
            trace=_trace(
                "risk_judge",
                "block_final_scoring_without_llm_agent_results",
                {"incomplete_tasks": incomplete_tasks},
                {"risk_score": 0, "risk_level": "UNKNOWN", "reason": "LLM agent result required"},
            ),
        )
    score = min(100, sum(max(0, finding.score_delta) for finding in findings))
    if score >= 75:
        level = "CRITICAL"
    elif score >= 50:
        level = "HIGH"
    elif score >= 25:
        level = "MEDIUM"
    else:
        level = "LOW"
    return _merge(
        state,
        risk_findings=findings,
        risk_score=score,
        risk_level=level,
        trace=_trace("risk_judge", "aggregate_risk_items_tool+calculate_risk_score_tool", {"finding_count": len(findings)}, {"risk_score": score, "risk_level": level}),
    )


def report_writer_node(state: DiagnosisState) -> DiagnosisState:
    task_results = state.get("task_results", {})
    recommendations: list[str] = []
    refs: list[dict[str, Any]] = []
    missing_checks: list[dict[str, Any]] = []
    for result in task_results.values():
        recommendations.extend(result.recommendations)
        refs.extend(result.evidence_refs)
        missing_checks.extend(result.missing_checks)

    report_trace = _trace("report_writer", "format_diagnosis_report_tool+build_user_action_plan_tool", {}, {"task_count": len(task_results)})
    full_trace = list(state.get("agent_trace", [])) + [report_trace]
    report = {
        "title": "전세계약 PDF 위험 진단 리포트",
        "disclaimer": "본 결과는 법률 자문이 아니라 계약 전 위험 확인을 돕는 보조 정보입니다.",
        "diagnosis_status": _diagnosis_status(state),
        "contract_file": state.get("contract_file"),
        "contract_source": "uploaded_file" if state.get("contract_file") else "mock_contract",
        "risk_score": state.get("risk_score", 0),
        "risk_level": state.get("risk_level", "UNKNOWN"),
        "contract_fields": state.get("contract_fields", {}),
        "diagnosis_plan": _to_dict(state.get("diagnosis_plan")),
        "task_results": {key: _to_dict(value) for key, value in task_results.items()},
        "findings": [asdict(finding) for finding in state.get("risk_findings", [])],
        "recommended_revisions": list(dict.fromkeys(item for item in recommendations if item)),
        "next_checks": list(dict.fromkeys([item.get("message", "") for item in missing_checks if item.get("message")])),
        "missing_checks": missing_checks,
        "rag_references": refs,
        "agent_trace": [asdict(trace) for trace in full_trace],
    }
    return _merge(state, report=report, trace=report_trace)


def _diagnosis_status(state: DiagnosisState) -> dict[str, Any]:
    plan = state.get("diagnosis_plan")
    task_results = state.get("task_results", {})
    blocked_reasons: list[str] = []
    if plan and (plan.status != "PLANNED" or not plan.llm_used):
        blocked_reasons.append("LLM supervisor plan was not available")
    for result in task_results.values():
        if result.metadata.get("result_status") != "COMPLETE":
            blocked_reasons.append(f"{result.task} did not produce an LLM-backed result")
    return {
        "complete": not blocked_reasons,
        "blocked_reasons": blocked_reasons,
        "fallback_policy": "Fallback/rule outputs are reference-only and are not included in final scoring unless an LLM agent validates them.",
    }


def _task_summary(result) -> dict[str, Any]:
    return {
        "task": result.task,
        "risk_count": len(result.risk_items),
        "recommendation_count": len(result.recommendations),
        "evidence_count": len(result.evidence_refs),
        "missing_check_count": len(result.missing_checks),
    }


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


def _to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_dict(item) for item in value]
    return value
