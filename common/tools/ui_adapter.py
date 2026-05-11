"""Adapters that convert graph reports into frontend-facing UI responses."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from langchain_core.tools import tool

from common.schemas.ui import (
    ChecklistProgress,
    RecommendedAction,
    RelatedCaseSummary,
    RiskSummary,
    UnifiedUIResponse,
)
from common.tools.checklist import build_safety_checklist_status
from common.tools.evidence import build_evidence_chips

HIGH_RISK_LEVELS = {"HIGH", "CRITICAL"}


def build_diagnosis_ui_response(report: dict[str, Any], *, session_id: str | None = None) -> UnifiedUIResponse:
    """Convert a diagnosis graph report into the chat diagnosis screen shape."""
    data = _to_dict(report)
    findings = _as_list(data.get("findings"))
    risk_level = str(data.get("risk_level") or "UNKNOWN")
    risk_score = _to_int(data.get("risk_score"))
    address = _to_dict(data.get("contract_fields")).get("address")

    title = data.get("title") or "전세계약 위험 진단"
    subtitle = address or "계약서 기반 위험 진단 결과"
    summary = _diagnosis_summary(risk_score, risk_level, findings)

    checklist = build_safety_checklist_status(data)
    checklist_progress_data = checklist.get("progress", {})

    return UnifiedUIResponse(
        screen_type="CHAT_DIAGNOSIS",
        title=str(title),
        subtitle=subtitle,
        session_id=session_id,
        answer=summary,
        risk=RiskSummary(
            risk_score=risk_score,
            risk_level=_safe_risk_level(risk_level),
            title="계약 위험도",
            summary=summary,
            finding_count=len(findings),
            high_priority_count=_count_high_priority(findings),
            metadata={"address": address, "housing_type": _to_dict(data.get("contract_fields")).get("housing_type")},
        ),
        evidence_chips=build_evidence_chips(data),
        recommended_actions=_actions_from_diagnosis(data),
        checklist_progress=ChecklistProgress(**checklist_progress_data),
        primary_payload={
            "contract_fields": data.get("contract_fields", {}),
            "market_analysis": data.get("market_analysis"),
            "findings": findings,
            "recommended_revisions": data.get("recommended_revisions", []),
            "next_checks": data.get("next_checks", []),
            "safety_checklist": checklist,
        },
        agent_trace=_as_list(data.get("agent_trace")),
        warnings=_warnings_from_report(data),
        metadata={"source_graph": "diagnosis_graph"},
    )


def build_legal_chat_ui_response(report: dict[str, Any], *, session_id: str | None = None) -> UnifiedUIResponse:
    """Convert a legal consultation graph report into the legal chat screen shape."""
    data = _to_dict(report)
    answer = data.get("answer") or "답변을 생성하지 못했습니다."
    basis_type = data.get("basis_type", "INSUFFICIENT")
    question_type = data.get("question_type", "UNKNOWN")

    return UnifiedUIResponse(
        screen_type="LEGAL_CHAT",
        title="법률 정보 상담",
        subtitle=f"질문 유형: {question_type}",
        session_id=session_id,
        answer=str(answer),
        risk=None,
        evidence_chips=build_evidence_chips(data),
        recommended_actions=_actions_from_strings(data.get("recommended_actions", [])),
        related_cases=_related_cases_from_report(data),
        primary_payload={
            "basis_type": basis_type,
            "confidence": data.get("confidence", "LOW"),
            "question_type": question_type,
            "used_external_search": data.get("used_external_search", False),
            "disclaimer": data.get("disclaimer"),
        },
        agent_trace=_as_list(data.get("agent_trace")),
        warnings=_legal_warnings(data),
        metadata={"source_graph": "legal_consultation_graph"},
    )


def build_defense_training_ui_response(report: dict[str, Any], *, session_id: str | None = None) -> UnifiedUIResponse:
    """Convert a defense simulation report into a playbook/training screen shape."""
    data = _to_dict(report)
    stage_status = data.get("stage_status", "UNKNOWN")
    game_status = data.get("game_status", "UNKNOWN")
    risk_exposure = _to_int(data.get("risk_exposure")) or 0
    defense_score = _to_int(data.get("defense_score"))
    feedback = data.get("feedback") or data.get("command_response") or "훈련 결과를 확인하세요."

    return UnifiedUIResponse(
        screen_type="DEFENSE_TRAINING",
        title=str(data.get("stage_title") or "전세사기 방어 훈련"),
        subtitle=str(data.get("category_title") or "사례 기반 예방 시나리오"),
        session_id=session_id,
        answer=str(feedback),
        risk=RiskSummary(
            risk_score=risk_exposure,
            risk_level=_risk_level_from_exposure(risk_exposure, game_status),
            title="위험 노출도",
            summary=f"{stage_status} / {game_status}",
            finding_count=len(_as_list(data.get("missed_defenses"))) + len(_as_list(data.get("dangerous_actions"))),
            high_priority_count=len(_as_list(data.get("dangerous_actions"))),
            metadata={"defense_score": defense_score, "stage_status": stage_status, "game_status": game_status},
        ),
        evidence_chips=build_evidence_chips(data),
        recommended_actions=_actions_from_defense(data),
        related_cases=_related_cases_from_defense(data),
        primary_payload={
            "roleplay_message": data.get("roleplay_message"),
            "user_message": data.get("user_message"),
            "input_type": data.get("input_type"),
            "command_response": data.get("command_response"),
            "detected_defenses": data.get("detected_defenses", []),
            "missed_defenses": data.get("missed_defenses", []),
            "dangerous_actions": data.get("dangerous_actions", []),
            "next_stage": data.get("next_stage"),
        },
        agent_trace=_as_list(data.get("agent_trace")),
        warnings=_defense_warnings(data),
        metadata={"source_graph": "defense_simulation_graph", "source_case": data.get("source_case")},
    )


def build_ui_response(report: dict[str, Any], *, screen_type: str, session_id: str | None = None) -> UnifiedUIResponse:
    """Dispatch a graph report to the proper UI response adapter."""
    if screen_type == "CHAT_DIAGNOSIS":
        return build_diagnosis_ui_response(report, session_id=session_id)
    if screen_type == "LEGAL_CHAT":
        return build_legal_chat_ui_response(report, session_id=session_id)
    if screen_type == "DEFENSE_TRAINING":
        return build_defense_training_ui_response(report, session_id=session_id)
    raise ValueError(f"unsupported screen_type: {screen_type}")


def _diagnosis_summary(risk_score: int | None, risk_level: str, findings: list[Any]) -> str:
    score_text = "알 수 없음" if risk_score is None else f"{risk_score}점"
    if not findings:
        return f"현재 위험도는 {score_text}({risk_level})입니다. 주요 위험 항목은 발견되지 않았습니다."
    top_titles = [str(_to_dict(item).get("title")) for item in findings[:3] if _to_dict(item).get("title")]
    return f"현재 위험도는 {score_text}({risk_level})입니다. 주요 위험 항목은 {', '.join(top_titles)}입니다."


def _actions_from_diagnosis(report: dict[str, Any]) -> list[RecommendedAction]:
    actions: list[RecommendedAction] = []
    seen: set[str] = set()
    for finding in _as_list(report.get("findings")):
        data = _to_dict(finding)
        label = data.get("required_action")
        if not label or label in seen:
            continue
        seen.add(str(label))
        actions.append(RecommendedAction(
            label=str(label),
            priority=_priority_from_severity(data.get("severity")),
            reason=data.get("description"),
            metadata={"finding_code": data.get("code"), "source": data.get("source")},
        ))
    for item in _as_list(report.get("next_checks")):
        if item and str(item) not in seen:
            seen.add(str(item))
            actions.append(RecommendedAction(label=str(item), priority="MEDIUM"))
    return actions


def _actions_from_strings(items: Any) -> list[RecommendedAction]:
    return [RecommendedAction(label=str(item), priority="MEDIUM") for item in _as_list(items) if item]


def _actions_from_defense(report: dict[str, Any]) -> list[RecommendedAction]:
    actions: list[RecommendedAction] = []
    for item in _as_list(report.get("missed_defenses")):
        data = _to_dict(item)
        label = data.get("label")
        if label:
            actions.append(RecommendedAction(label=f"다음에는 확인하기: {label}", priority="HIGH", metadata={"defense_id": data.get("id")}))
    if report.get("game_status") == "GAME_OVER":
        actions.append(RecommendedAction(label="계약/입금 전 위험 신호를 다시 확인하세요.", priority="CRITICAL", reason=report.get("game_over_reason")))
    next_stage = _to_dict(report.get("next_stage"))
    if next_stage:
        actions.append(RecommendedAction(label=f"다음 단계 진행: {next_stage.get('title')}", priority="LOW", metadata=next_stage))
    return actions


def _related_cases_from_report(report: dict[str, Any]) -> list[RelatedCaseSummary]:
    cases: list[RelatedCaseSummary] = []
    chips_by_source = {chip.source_id: chip for chip in build_evidence_chips(report) if chip.source_id}
    for item in _as_list(report.get("cited_cases")):
        data = _to_dict(item)
        source_id = data.get("source_id")
        title = data.get("issue") or data.get("case_number") or "관련 판례/사례"
        cases.append(RelatedCaseSummary(
            title=str(title),
            case_id=source_id,
            court=data.get("court"),
            case_number=data.get("case_number"),
            issue=data.get("issue"),
            summary=data.get("summary", ""),
            relevance=data.get("relevance", ""),
            evidence_chip=chips_by_source.get(source_id),
        ))
    return cases


def _related_cases_from_defense(report: dict[str, Any]) -> list[RelatedCaseSummary]:
    source_case = report.get("source_case")
    if not source_case:
        return []
    chips = build_evidence_chips(report)
    return [RelatedCaseSummary(
        title=str(source_case),
        case_id=str(source_case),
        issue=report.get("stage_title"),
        summary=report.get("feedback", ""),
        relevance="현재 방어 훈련 stage의 기반 사례입니다.",
        evidence_chip=chips[0] if chips else None,
    )]


def _warnings_from_report(report: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if report.get("disclaimer"):
        warnings.append(str(report["disclaimer"]))
    for finding in _as_list(report.get("findings")):
        data = _to_dict(finding)
        if data.get("severity") in HIGH_RISK_LEVELS and data.get("title"):
            warnings.append(str(data["title"]))
    return _dedupe_strings(warnings)


def _legal_warnings(report: dict[str, Any]) -> list[str]:
    warnings = []
    if report.get("used_external_search"):
        warnings.append("내부 근거가 부족해 외부 자료를 함께 참고했습니다.")
    if report.get("disclaimer"):
        warnings.append(str(report["disclaimer"]))
    return _dedupe_strings(warnings)


def _defense_warnings(report: dict[str, Any]) -> list[str]:
    warnings = []
    if report.get("game_over_reason"):
        warnings.append(str(report["game_over_reason"]))
    for item in _as_list(report.get("dangerous_actions")):
        warnings.append(f"위험 행동 감지: {item}")
    return _dedupe_strings(warnings)


def _count_high_priority(findings: list[Any]) -> int:
    count = 0
    for finding in findings:
        severity = str(_to_dict(finding).get("severity") or "").upper()
        if severity in HIGH_RISK_LEVELS:
            count += 1
    return count

def _priority_from_severity(severity: Any) -> str:
    value = str(severity or "MEDIUM").upper()
    if value in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        return value
    return "MEDIUM"


def _safe_risk_level(value: str) -> str:
    value = value.upper()
    if value in {"LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}:
        return value
    return "UNKNOWN"


def _risk_level_from_exposure(exposure: int, game_status: Any) -> str:
    if game_status == "GAME_OVER" or exposure >= 75:
        return "CRITICAL"
    if exposure >= 50:
        return "HIGH"
    if exposure >= 25:
        return "MEDIUM"
    return "LOW"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    return {}


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


@tool
def build_diagnosis_ui_response_tool(report: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    """Convert a diagnosis graph report into a frontend UI response dictionary."""
    return build_diagnosis_ui_response(report, session_id=session_id).to_dict()


@tool
def build_legal_chat_ui_response_tool(report: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    """Convert a legal consultation graph report into a frontend UI response dictionary."""
    return build_legal_chat_ui_response(report, session_id=session_id).to_dict()


@tool
def build_defense_training_ui_response_tool(report: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    """Convert a defense simulation report into a frontend UI response dictionary."""
    return build_defense_training_ui_response(report, session_id=session_id).to_dict()