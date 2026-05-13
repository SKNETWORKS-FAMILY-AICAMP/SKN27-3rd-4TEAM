"""LangGraph state nodes for the jeonse fraud defense simulation."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from common.agents.defense_simulation_agents import run_action_interpreter_agent, run_defense_roleplay_agent
from common.schemas.defense_simulation import DefenseSimulationState
from common.schemas.shared import AgentTrace
from common.tools.adaptive_rag import adaptive_rag
from common.tools.llm import LLMUnavailable

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "defense_scenarios.json"
COMMANDS = {"/힌트", "/상태", "/근거", "/도움말", "/포기"}
COMMAND_ALIASES = {
    "/힌트": "/힌트",
    "/hint": "/힌트",
    "힌트": "/힌트",
    "/상태": "/상태",
    "/status": "/상태",
    "상태": "/상태",
    "상태 보여줘": "/상태",
    "/근거": "/근거",
    "/evidence": "/근거",
    "근거": "/근거",
    "/도움말": "/도움말",
    "/help": "/도움말",
    "도움말": "/도움말",
    "도와줘": "/도움말",
    "/포기": "/포기",
    "/quit": "/포기",
    "포기": "/포기",
}


def campaign_loader_node(state: DefenseSimulationState) -> DefenseSimulationState:
    categories = _load_categories()
    category_id = state.get("category_id") or categories[0]["category_id"]
    campaign = next((item for item in categories if item["category_id"] == category_id), categories[0])
    return _merge(
        state,
        category_id=campaign["category_id"],
        campaign=campaign,
        current_stage_index=int(state.get("current_stage_index", 0)),
        hint_used_count=int(state.get("hint_used_count", 0)),
        risk_exposure=int(state.get("risk_exposure", 0)),
        failed_stage_count=int(state.get("failed_stage_count", 0)),
        game_status=state.get("game_status", "PLAYING"),
        errors=list(state.get("errors", [])),
        trace=_trace("Campaign Loader Node", "load_campaign", {"category_id": category_id}, {"stage_count": len(campaign.get("stages", []))}),
    )


def stage_loader_node(state: DefenseSimulationState) -> DefenseSimulationState:
    stages = state.get("campaign", {}).get("stages", [])
    index = min(max(int(state.get("current_stage_index", 0)), 0), max(len(stages) - 1, 0))
    if not stages:
        return _merge(state, errors=list(state.get("errors", [])) + ["no stages found"], game_status="GAME_OVER")
    stage = stages[index]
    return _merge(state, current_stage_index=index, current_stage=stage, stage_status="READY", trace=_trace("Stage Loader Node", "load_stage", {"stage_index": index}, {"stage_id": stage.get("stage_id"), "title": stage.get("title")}))


def roleplay_node(state: DefenseSimulationState) -> DefenseSimulationState:
    if state.get("input_type") == "COMMAND" or state.get("game_status") in {"GAME_OVER", "COMPLETED"}:
        return _merge(
            state,
            roleplay_message=None,
            trace=_trace(
                "Defense Roleplay ReAct Agent",
                "skip_roleplay",
                {"input_type": state.get("input_type"), "game_status": state.get("game_status")},
                {"reason": "command_or_terminal_state"},
            ),
        )

    stage = state.get("current_stage", {})
    last_user = _last_user_message(state)
    fallback = f"{stage.get('scenario')}\n\n중개인/임대인: 이 정도는 관행이라 괜찮습니다. 오늘 바로 진행하시죠, 끌끌..."
    generated = run_defense_roleplay_agent(stage, last_user)
    roleplay_message = generated or fallback
    history = list(state.get("conversation_history", []))
    history.append({"role": "npc", "content": roleplay_message})
    return _merge(state, roleplay_message=roleplay_message, conversation_history=history, trace=_trace("Defense Roleplay ReAct Agent", "generate_scam_pressure_message", {"stage_id": stage.get("stage_id")}, {"react_agent_used": bool(generated)}))


def input_router_node(state: DefenseSimulationState) -> DefenseSimulationState:
    message = (state.get("user_message") or "").strip()
    command = _normalize_command(message)
    input_type = "COMMAND" if command in COMMANDS else "ACTION"
    history = list(state.get("conversation_history", []))
    if message:
        history.append({"role": "user", "content": message})
    return _merge(state, user_message=message, input_type=input_type, command=command, conversation_history=history, trace=_trace("Input Router Node", "route_user_input", {"user_message": message}, {"input_type": input_type, "command": command}))


def command_handler_node(state: DefenseSimulationState) -> DefenseSimulationState:
    if state.get("input_type") != "COMMAND":
        return _merge(state, command_response=None, trace=_trace("Command Handler Node", "skip_command", {}, {"reason": "action input"}))

    stage = state.get("current_stage", {})
    command = state.get("command")
    hint_count = int(state.get("hint_used_count", 0))
    status = "COMMAND"
    game_status = state.get("game_status", "PLAYING")
    risk_exposure = int(state.get("risk_exposure", 0))

    if command == "/힌트":
        hint_count += 1
        risk_exposure += 5
        response = stage.get("hint", "현재 단계의 핵심 확인 포인트를 다시 살펴보세요.")
    elif command == "/상태":
        response = f"카테고리: {state.get('campaign', {}).get('title')} / 단계: {stage.get('title')} / 위험노출: {risk_exposure}"
    elif command == "/근거":
        response = _evidence_summary(stage)
    elif command == "/도움말":
        response = "사용 가능 명령어: /힌트, /상태, /근거, /도움말, /포기"
    elif command == "/포기":
        status = "STAGE_FAILED"
        response = _give_up_explanation(stage)
    else:
        response = "알 수 없는 명령어입니다. /도움말을 입력해보세요."

    if risk_exposure >= 100:
        status = "GAME_OVER"
        game_status = "GAME_OVER"

    return _merge(state, command_response=response, hint_used_count=hint_count, risk_exposure=risk_exposure, stage_status=status, game_status=game_status, trace=_trace("Command Handler Node", "handle_command", {"command": command}, {"stage_status": status, "risk_exposure": risk_exposure}))


def user_action_interpreter_node(state: DefenseSimulationState) -> DefenseSimulationState:
    if state.get("input_type") == "COMMAND":
        return _merge(
            state,
            interpreted_actions=[],
            intent_summary="",
            normalized_user_action="",
            unsafe_behavior=False,
            unsafe_reason=None,
            abusive_language=False,
            abusive_reason=None,
            dangerous_acceptance=False,
            interpretation_confidence=1.0,
            interpretation_method="command_skip",
            trace=_trace("User Action Interpreter Node", "skip_command_input", {}, {}),
        )

    message = state.get("user_message", "")
    stage = state.get("current_stage", {})
    interpretation = _interpret_action_with_llm(message, stage)
    if interpretation["method"] == "fallback_keyword":
        interpretation = _interpret_action_with_keywords(message, stage)
    else:
        interpretation = _apply_keyword_guardrails(message, stage, interpretation)

    valid_action_ids = {defense.get("id") for defense in stage.get("critical_defenses", [])}
    actions = [action for action in dict.fromkeys(interpretation.get("normalized_actions", [])) if action in valid_action_ids]
    if interpretation.get("dangerous_acceptance"):
        actions.append("DANGEROUS_ACCEPTANCE")

    return _merge(
        state,
        interpreted_actions=actions,
        intent_summary=interpretation.get("intent_summary", ""),
        normalized_user_action=interpretation.get("normalized_user_action", ""),
        unsafe_behavior=bool(interpretation.get("unsafe_behavior", False)),
        unsafe_reason=interpretation.get("unsafe_reason"),
        abusive_language=bool(interpretation.get("abusive_language", False)),
        abusive_reason=interpretation.get("abusive_reason"),
        dangerous_acceptance=bool(interpretation.get("dangerous_acceptance", False)),
        interpretation_confidence=float(interpretation.get("confidence", 0.0)),
        interpretation_method=interpretation.get("method", "unknown"),
        trace=_trace(
            "LLM Action Interpreter Agent",
            "interpret_natural_language_defense",
            {"user_message": message},
            {
                "actions": actions,
                "unsafe_behavior": bool(interpretation.get("unsafe_behavior", False)),
                "abusive_language": bool(interpretation.get("abusive_language", False)),
                "dangerous_acceptance": bool(interpretation.get("dangerous_acceptance", False)),
                "method": interpretation.get("method", "unknown"),
                "confidence": interpretation.get("confidence", 0.0),
            },
        ),
    )


def defense_judge_node(state: DefenseSimulationState) -> DefenseSimulationState:
    if state.get("input_type") == "COMMAND":
        return _merge(state, trace=_trace("Defense Judge Node", "skip_command_input", {}, {}))

    stage = state.get("current_stage", {})
    actions = set(state.get("interpreted_actions", []))
    detected = [defense for defense in stage.get("critical_defenses", []) if defense.get("id") in actions]
    missed = [defense for defense in stage.get("critical_defenses", []) if defense.get("id") not in actions]
    dangerous = [action for action in actions if action == "DANGEROUS_ACCEPTANCE"]
    return _merge(state, detected_defenses=detected, missed_defenses=missed, dangerous_actions=dangerous, trace=_trace("Defense Judge Node", "grade_defense_action", {"actions": list(actions)}, {"detected_count": len(detected), "dangerous_count": len(dangerous)}))


def stage_result_node(state: DefenseSimulationState) -> DefenseSimulationState:
    if state.get("input_type") == "COMMAND":
        return _merge(state, trace=_trace("Stage Result Node", "skip_command_result", {}, {"stage_status": state.get("stage_status")}))

    stage = state.get("current_stage", {})
    risk_exposure = int(state.get("risk_exposure", 0))
    failed_count = int(state.get("failed_stage_count", 0))
    detected_count = len(state.get("detected_defenses", []))
    pass_threshold = int(stage.get("pass_threshold", 1))

    if state.get("unsafe_behavior"):
        risk_exposure += int(stage.get("risk_penalty", 30))
        status = "GAME_OVER"
        reason = f"불법적이거나 위험한 대응을 선택했습니다: {state.get('unsafe_reason') or '부적절한 대응'}"
        ending_type = "UNSAFE_ACTION"
    elif state.get("abusive_language"):
        risk_exposure += int(stage.get("risk_penalty", 30))
        status = "GAME_OVER"
        reason = f"폭언으로 계약 대응이 파탄났습니다: {state.get('abusive_reason') or '감정적 폭언'}"
        ending_type = "ABUSIVE_OUTBURST"
    elif state.get("dangerous_actions") or state.get("dangerous_acceptance"):
        risk_exposure += int(stage.get("risk_penalty", 30))
        status = "GAME_OVER"
        reason = "위험 신호를 확인하지 않고 계약/입금/수락 방향으로 응답했습니다."
        ending_type = "DEPOSIT_LOSS"
    elif detected_count >= pass_threshold:
        status = "STAGE_CLEAR"
        reason = None
        ending_type = None
    else:
        risk_exposure += int(stage.get("risk_penalty", 30))
        failed_count += 1
        status = "GAME_OVER" if risk_exposure >= 100 or failed_count >= 2 else "STAGE_FAILED"
        reason = "필수 방어 행동이 부족했습니다."
        ending_type = "INSUFFICIENT_DEFENSE" if status == "GAME_OVER" else None

    game_status = "GAME_OVER" if status == "GAME_OVER" else "PLAYING"
    stages = state.get("campaign", {}).get("stages", [])
    next_index = int(state.get("current_stage_index", 0))
    if status == "STAGE_CLEAR":
        next_index += 1
        if next_index >= len(stages):
            status = "COMPLETED"
            game_status = "COMPLETED"
            ending_type = "SAFE_ENDING"

    score = max(0, 100 - risk_exposure - int(state.get("hint_used_count", 0)) * 5)
    return _merge(state, current_stage_index=next_index, stage_status=status, game_status=game_status, risk_exposure=risk_exposure, failed_stage_count=failed_count, defense_score=score, game_over_reason=reason, ending_type=ending_type, trace=_trace("Stage Result Node", "decide_stage_outcome", {"detected_count": detected_count, "risk_exposure": risk_exposure}, {"stage_status": status, "game_status": game_status, "next_stage_index": next_index, "ending_type": ending_type}))


def evidence_connector_node(state: DefenseSimulationState) -> DefenseSimulationState:
    if state.get("input_type") == "COMMAND":
        return _merge(
            state,
            evidence_report={},
            trace=_trace("Evidence Connector Node", "skip_command_input", {}, {"reason": "command input"}),
        )

    stage = state.get("current_stage", {})
    pack = adaptive_rag("defense_simulation_evidence", stage.get("evidence_query", stage.get("title", "")), filters={"doc_type": ["casebook", "guide", "law", "checklist"]}, top_k=3)
    report = {
        "query": pack.query,
        "source_case": stage.get("source_case"),
        "references": [{"source_id": ctx.source_id, "title": ctx.title, "doc_type": ctx.doc_type, "score": ctx.score} for ctx in pack.contexts],
        "fallback_note": pack.quality.reason,
    }
    return _merge(state, evidence_report=report, trace=_trace("Evidence Connector Node", "attach_casebook_evidence", {"stage_id": stage.get("stage_id")}, {"reference_count": len(report["references"])}))


def feedback_report_node(state: DefenseSimulationState) -> DefenseSimulationState:
    stage = state.get("current_stage", {})
    feedback = _feedback_text(state)
    stages = state.get("campaign", {}).get("stages", [])
    next_stage = None
    if state.get("game_status") == "PLAYING" and int(state.get("current_stage_index", 0)) < len(stages):
        upcoming = stages[int(state.get("current_stage_index", 0))]
        next_stage = {"stage_index": state.get("current_stage_index"), "stage_id": upcoming.get("stage_id"), "title": upcoming.get("title")}

    report = {
        "category_id": state.get("category_id"),
        "category_title": state.get("campaign", {}).get("title"),
        "stage_id": stage.get("stage_id"),
        "stage_title": stage.get("title"),
        "source_case": stage.get("source_case"),
        "roleplay_message": state.get("roleplay_message"),
        "user_message": state.get("user_message"),
        "input_type": state.get("input_type"),
        "command_response": state.get("command_response"),
        "intent_summary": state.get("intent_summary"),
        "normalized_user_action": state.get("normalized_user_action"),
        "unsafe_behavior": state.get("unsafe_behavior", False),
        "unsafe_reason": state.get("unsafe_reason"),
        "abusive_language": state.get("abusive_language", False),
        "abusive_reason": state.get("abusive_reason"),
        "dangerous_acceptance": state.get("dangerous_acceptance", False),
        "interpretation_confidence": state.get("interpretation_confidence", 0.0),
        "interpretation_method": state.get("interpretation_method"),
        "detected_defenses": state.get("detected_defenses", []),
        "missed_defenses": state.get("missed_defenses", []),
        "dangerous_actions": state.get("dangerous_actions", []),
        "stage_status": state.get("stage_status"),
        "game_status": state.get("game_status"),
        "risk_exposure": state.get("risk_exposure", 0),
        "defense_score": state.get("defense_score", 100),
        "game_over_reason": state.get("game_over_reason"),
        "ending_type": state.get("ending_type"),
        "next_stage": next_stage,
        "feedback": feedback,
        "narrative_feedback": feedback,
        "evidence_report": state.get("evidence_report", {}),
        "agent_trace": [asdict(trace) for trace in state.get("agent_trace", [])],
    }
    return _merge(state, feedback=feedback, report=report, trace=_trace("Feedback Report Node", "package_simulation_report", {}, {"stage_status": state.get("stage_status"), "game_status": state.get("game_status")}))


def _load_categories() -> list[dict[str, Any]]:
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    return data.get("categories", [])


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _normalize_command(message: str) -> str | None:
    lowered = message.strip().lower()
    first = lowered.split()[0] if lowered else ""
    if lowered in COMMAND_ALIASES:
        return COMMAND_ALIASES[lowered]
    if first in COMMAND_ALIASES:
        return COMMAND_ALIASES[first]
    for alias, command in COMMAND_ALIASES.items():
        if not alias.startswith("/") and alias in lowered:
            return command
    return None


def _last_user_message(state: DefenseSimulationState) -> str | None:
    for item in reversed(state.get("conversation_history", [])):
        if item.get("role") == "user":
            return item.get("content")
    return None


def _interpret_action_with_llm(message: str, stage: dict[str, Any]) -> dict[str, Any]:
    try:
        data = run_action_interpreter_agent(message, stage)
        return _normalize_interpretation(data, method="llm_structured")
    except (LLMUnavailable, json.JSONDecodeError, TypeError, ValueError):
        return {"method": "fallback_keyword"}


def _interpret_action_with_keywords(message: str, stage: dict[str, Any]) -> dict[str, Any]:
    actions: list[str] = []
    for defense in stage.get("critical_defenses", []):
        if _contains_any(message, defense.get("keywords", [])):
            actions.append(defense.get("id", "UNKNOWN_DEFENSE"))

    unsafe, unsafe_reason = _detect_unsafe_keyword(message)
    abusive = _is_abusive_language(message)
    delegating = _is_delegating_or_giving_up(message)
    dangerous = delegating or _contains_any(message, stage.get("danger_keywords", [])) or _contains_any(message, ["그렇게 진행", "진행하시죠", "바로 계약", "바로 입금", "입금할게", "계약할게"])
    return {
        "normalized_actions": [] if unsafe or abusive or dangerous else actions,
        "intent_summary": _fallback_intent_summary(message, actions, unsafe, dangerous, abusive),
        "normalized_user_action": _fallback_normalized_action(stage, actions) if not (unsafe or abusive or dangerous) else "",
        "unsafe_behavior": unsafe,
        "unsafe_reason": unsafe_reason,
        "abusive_language": abusive,
        "abusive_reason": "폭언 또는 모욕적 표현" if abusive else None,
        "dangerous_acceptance": dangerous,
        "confidence": 0.55 if actions or unsafe or abusive or dangerous else 0.2,
        "method": "fallback_keyword",
    }


def _apply_keyword_guardrails(message: str, stage: dict[str, Any], interpretation: dict[str, Any]) -> dict[str, Any]:
    guarded = dict(interpretation)
    unsafe, unsafe_reason = _detect_unsafe_keyword(message)
    if unsafe:
        guarded["unsafe_behavior"] = True
        guarded["unsafe_reason"] = unsafe_reason
        guarded["dangerous_acceptance"] = False
        guarded["normalized_actions"] = []
    elif _is_abusive_language(message):
        guarded["normalized_actions"] = []
        guarded["abusive_language"] = True
        guarded["abusive_reason"] = "폭언 또는 모욕적 표현"
        guarded["dangerous_acceptance"] = False
    elif _is_delegating_or_giving_up(message):
        guarded["normalized_actions"] = []
        guarded["dangerous_acceptance"] = True
        guarded["intent_summary"] = "사용자는 스스로 확인하지 않고 상대방에게 계약 진행을 맡기려는 위험한 의도를 보였다."
        guarded["normalized_user_action"] = "확인 절차 포기 및 상대방에게 계약 진행 위임"
    elif _contains_any(message, stage.get("danger_keywords", [])) or _contains_any(message, ["그렇게 진행", "진행하시죠", "바로 계약", "바로 입금", "입금할게", "계약할게"]):
        guarded["normalized_actions"] = []
        guarded["dangerous_acceptance"] = True
    return guarded


def _normalize_interpretation(data: dict[str, Any], *, method: str) -> dict[str, Any]:
    actions = data.get("normalized_actions") or []
    if not isinstance(actions, list):
        actions = []
    confidence = data.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "normalized_actions": [str(action) for action in actions],
        "intent_summary": str(data.get("intent_summary") or ""),
        "normalized_user_action": str(data.get("normalized_user_action") or ""),
        "unsafe_behavior": bool(data.get("unsafe_behavior", False)),
        "unsafe_reason": data.get("unsafe_reason"),
        "abusive_language": bool(data.get("abusive_language", False)),
        "abusive_reason": data.get("abusive_reason"),
        "dangerous_acceptance": bool(data.get("dangerous_acceptance", False)),
        "confidence": confidence,
        "method": method,
    }


def _detect_unsafe_keyword(message: str) -> tuple[bool, str | None]:
    checks = [
        (["폭행", "때린", "때리", "패버", "죽", "살해"], "폭력 행위"),
        (["협박", "감금", "납치"], "협박 또는 감금"),
        (["위조", "조작", "가짜 서류"], "문서 위조 또는 조작"),
        (["훔치", "절도", "몰래 들어", "침입"], "절도 또는 주거침입"),
        (["개인정보", "해킹", "털어"], "개인정보 탈취"),
    ]
    for keywords, reason in checks:
        if _contains_any(message, keywords):
            return True, reason
    return False, None


def _is_abusive_language(message: str) -> bool:
    return _contains_any(
        message,
        [
            "씨발",
            "시발",
            "개새끼",
            "새끼",
            "좆",
            "ㅈ까",
            "좆까",
            "꺼져",
            "병신",
            "미친놈",
            "개자식",
        ],
    )


def _is_delegating_or_giving_up(message: str) -> bool:
    return _contains_any(
        message,
        [
            "알아서 해",
            "알아서 해주세요",
            "맡길게",
            "맡기겠습니다",
            "대신 해주세요",
            "잘 모르겠",
            "모르겠네요",
            "그냥 해주세요",
            "시키는대로",
            "시키는 대로",
            "서류는 맡길게요",
            "확인 안 해도",
            "확인하지 않아도",
        ],
    )


def _fallback_intent_summary(message: str, actions: list[str], unsafe: bool, dangerous: bool, abusive: bool = False) -> str:
    if unsafe:
        return "사용자는 폭력적이거나 불법적인 대응을 선택했다."
    if abusive:
        return "사용자는 감정적인 욕설 또는 모욕적 표현으로 대응했다."
    if dangerous:
        return "사용자는 추가 확인 없이 계약 진행 또는 입금을 수락하려는 의도를 보였다."
    if actions:
        return "사용자는 핵심 방어 행동 일부를 수행하려는 의도를 보였다."
    return f"사용자 의도가 명확하지 않습니다: {message}"


def _fallback_normalized_action(stage: dict[str, Any], actions: list[str]) -> str:
    if not actions:
        return ""
    labels = [defense.get("label", "") for defense in stage.get("critical_defenses", []) if defense.get("id") in actions]
    return ", ".join(label for label in labels if label)


def _evidence_summary(stage: dict[str, Any]) -> str:
    risks = ", ".join(stage.get("hidden_risks", []))
    defenses = ", ".join(defense.get("label", "") for defense in stage.get("critical_defenses", []))
    return f"관련 사례: {stage.get('source_case')} / 숨은 위험: {risks} / 핵심 방어: {defenses}"


def _give_up_explanation(stage: dict[str, Any]) -> str:
    return f"정답 해설: {stage.get('hint')} 핵심 방어는 {_evidence_summary(stage)}"


def _feedback_text(state: DefenseSimulationState) -> str:
    stage = state.get("current_stage", {})
    if state.get("input_type") == "COMMAND":
        return state.get("command_response") or "명령어를 처리했습니다."
    if state.get("ending_type") == "UNSAFE_ACTION":
        return (
            "GAME OVER: 잘못된 대응입니다.\n"
            f"{state.get('unsafe_reason') or '부적절한 행동'}을 선택해 오히려 법적 책임 위험이 생겼습니다.\n"
            "전세사기 대응은 폭력이나 협박이 아니라 계약 중단, 증거 확보, 공식 서류 확인, 전문가 상담으로 해야 합니다."
        )
    if state.get("ending_type") == "ABUSIVE_OUTBURST":
        return (
            "GAME OVER: 감정적 대응으로 협상이 파탄났습니다.\n"
            "사기 의심 상황에서 분노는 자연스럽지만, 욕설만으로는 보증금을 지킬 수 없습니다.\n"
            "상대는 태도를 문제 삼으며 빠져나갔고, 당신은 신탁원부와 계약 권한 확인 기회를 놓쳤습니다.\n"
            f"다음에는 이렇게 말해보세요: \"{_suggested_user_phrase(stage)}\""
        )
    if state.get("ending_type") == "DEPOSIT_LOSS":
        return (
            "GAME OVER: 전세금을 지키지 못했습니다.\n"
            "위험 신호를 확인하지 않은 채 계약 진행 방향으로 응답했습니다.\n"
            f"이 단계의 핵심은 { _required_defense_labels(stage) }입니다."
        )
    if state.get("ending_type") == "INSUFFICIENT_DEFENSE":
        return (
            "GAME OVER: 핵심 확인을 놓쳤습니다.\n"
            "상대의 말만 믿고 필요한 방어 행동을 충분히 하지 못했습니다.\n"
            f"다음에는 이렇게 말해보세요: \"{_suggested_user_phrase(stage)}\""
        )
    if state.get("ending_type") == "SAFE_ENDING":
        return "SAFE ENDING: 훌륭합니다. 위험 신호를 확인하고 보증금을 지키는 방향으로 대응했습니다."
    if state.get("stage_status") in {"STAGE_CLEAR", "COMPLETED"}:
        labels = [item.get("label") for item in state.get("detected_defenses", [])]
        normalized = state.get("normalized_user_action") or ", ".join(labels)
        return (
            "좋은 방어입니다.\n"
            f"사용자의 대응은 '{normalized}'에 해당합니다.\n"
            "상대가 서두르더라도 공식 서류와 계약 권한을 직접 확인하는 태도가 중요합니다."
        )
    if state.get("stage_status") == "GAME_OVER":
        return state.get("game_over_reason") or "위험 노출이 너무 커져 시뮬레이션이 종료되었습니다."
    missed = [item.get("label") for item in state.get("missed_defenses", [])]
    return (
        "아직 부족합니다.\n"
        "방어 의도는 일부 보일 수 있지만 핵심 확인 요구가 부족합니다.\n"
        "놓친 방어 항목: " + ", ".join(missed) + "\n"
        f"다음처럼 말해보세요: \"{_suggested_user_phrase(stage)}\""
    )


def _required_defense_labels(stage: dict[str, Any]) -> str:
    labels = [defense.get("label", "") for defense in stage.get("critical_defenses", [])]
    return ", ".join(label for label in labels if label) or "공식 서류 확인과 계약 권한 확인"


def _suggested_user_phrase(stage: dict[str, Any]) -> str:
    labels = _required_defense_labels(stage)
    if "신탁" in labels:
        return "신탁원부와 계약 권한 서류를 직접 확인하기 전에는 계약하지 않겠습니다."
    if "등기부" in labels:
        return "등기부등본을 공식 경로에서 직접 발급하고 잔금 직전에 다시 확인하겠습니다."
    if "신분증" in labels or "소유자" in labels:
        return "신분증과 등기부상 소유자 정보를 대조하고 계약 권한을 확인하겠습니다."
    if "전세가율" in labels or "보증보험" in labels:
        return "실거래가와 전세가율, 보증보험 가능 여부를 확인한 뒤 결정하겠습니다."
    if "반환" in labels:
        return "보증금 반환 기한을 명확히 쓰고 다음 임차인 조건부 반환 문구는 삭제하겠습니다."
    return f"{labels}을 확인하기 전에는 계약을 진행하지 않겠습니다."


def _merge(state: DefenseSimulationState, *, trace: AgentTrace | None = None, **updates: Any) -> DefenseSimulationState:
    next_state: DefenseSimulationState = dict(state)
    next_state.update(updates)
    if trace:
        traces = list(next_state.get("agent_trace", []))
        traces.append(trace)
        next_state["agent_trace"] = traces
    return next_state


def _trace(agent: str, action: str, inputs: dict[str, Any], outputs: dict[str, Any]) -> AgentTrace:
    return AgentTrace(agent=agent, action=action, inputs=inputs, outputs=outputs)
