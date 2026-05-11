"""LangGraph state nodes for the jeonse fraud defense simulation."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from common.agents.react_agent_factory import invoke_react_agent
from common.schemas.defense_simulation import DefenseSimulationState
from common.schemas.shared import AgentTrace
from common.tools.adaptive_rag import adaptive_rag, adaptive_rag_tool

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "defense_scenarios.json"
COMMANDS = {"/힌트", "/상태", "/근거", "/도움말", "/포기"}


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
    stage = state.get("current_stage", {})
    fallback = f"{stage.get('scenario')}\n\n중개인/임대인: 이 정도는 관행이라 괜찮습니다. 오늘 바로 진행하시죠."
    generated = invoke_react_agent(
        name="defense_roleplay_react_agent",
        system_prompt=(
            "너는 전세사기 예방 교육용 롤플레이 ReAct Agent다. "
            "임대인 또는 중개인 역할로 위험 신호를 노골적으로 정답처럼 말하지 않고, "
            "사용자가 스스로 확인하도록 현실적인 압박 상황을 만든다. "
            "불법을 구체적으로 조언하지 말고 교육 시뮬레이션 범위에서만 말한다."
        ),
        user_prompt=f"상황: {stage.get('scenario')}\n역할 지시: {stage.get('roleplay_prompt')}\n짧은 대사 2~3문장으로 작성해.",
        tools=[adaptive_rag_tool],
        temperature=0.4,
    )
    roleplay_message = generated or fallback
    history = list(state.get("conversation_history", []))
    history.append({"role": "npc", "content": roleplay_message})
    return _merge(state, roleplay_message=roleplay_message, conversation_history=history, trace=_trace("Defense Roleplay ReAct Agent", "generate_scam_pressure_message", {"stage_id": stage.get("stage_id")}, {"react_agent_used": bool(generated)}))


def input_router_node(state: DefenseSimulationState) -> DefenseSimulationState:
    message = (state.get("user_message") or "").strip()
    command = message.split()[0] if message.startswith("/") else None
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
        return _merge(state, interpreted_actions=[], trace=_trace("User Action Interpreter Node", "skip_command_input", {}, {}))

    message = state.get("user_message", "")
    stage = state.get("current_stage", {})
    actions: list[str] = []
    for defense in stage.get("critical_defenses", []):
        if _contains_any(message, defense.get("keywords", [])):
            actions.append(defense.get("id", "UNKNOWN_DEFENSE"))
    if _contains_any(message, stage.get("danger_keywords", [])):
        actions.append("DANGEROUS_ACCEPTANCE")
    return _merge(state, interpreted_actions=actions, trace=_trace("User Action Interpreter Node", "interpret_defense_action", {"user_message": message}, {"actions": actions}))


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

    if state.get("dangerous_actions"):
        risk_exposure += int(stage.get("risk_penalty", 30))
        status = "GAME_OVER"
        reason = "위험 신호를 확인하지 않고 계약/입금/수락 방향으로 응답했습니다."
    elif detected_count >= pass_threshold:
        status = "STAGE_CLEAR"
        reason = None
    else:
        risk_exposure += int(stage.get("risk_penalty", 30))
        failed_count += 1
        status = "GAME_OVER" if risk_exposure >= 100 or failed_count >= 2 else "STAGE_FAILED"
        reason = "필수 방어 행동이 부족했습니다."

    game_status = "GAME_OVER" if status == "GAME_OVER" else "PLAYING"
    stages = state.get("campaign", {}).get("stages", [])
    next_index = int(state.get("current_stage_index", 0))
    if status == "STAGE_CLEAR":
        next_index += 1
        if next_index >= len(stages):
            status = "COMPLETED"
            game_status = "COMPLETED"

    score = max(0, 100 - risk_exposure - int(state.get("hint_used_count", 0)) * 5)
    return _merge(state, current_stage_index=next_index, stage_status=status, game_status=game_status, risk_exposure=risk_exposure, failed_stage_count=failed_count, defense_score=score, game_over_reason=reason, trace=_trace("Stage Result Node", "decide_stage_outcome", {"detected_count": detected_count, "risk_exposure": risk_exposure}, {"stage_status": status, "game_status": game_status, "next_stage_index": next_index}))


def evidence_connector_node(state: DefenseSimulationState) -> DefenseSimulationState:
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
        "detected_defenses": state.get("detected_defenses", []),
        "missed_defenses": state.get("missed_defenses", []),
        "dangerous_actions": state.get("dangerous_actions", []),
        "stage_status": state.get("stage_status"),
        "game_status": state.get("game_status"),
        "risk_exposure": state.get("risk_exposure", 0),
        "defense_score": state.get("defense_score", 100),
        "game_over_reason": state.get("game_over_reason"),
        "next_stage": next_stage,
        "feedback": feedback,
        "evidence_report": state.get("evidence_report", {}),
        "agent_trace": [asdict(trace) for trace in state.get("agent_trace", [])],
    }
    return _merge(state, feedback=feedback, report=report, trace=_trace("Feedback Report Node", "package_simulation_report", {}, {"stage_status": state.get("stage_status"), "game_status": state.get("game_status")}))


def _load_categories() -> list[dict[str, Any]]:
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    return data.get("categories", [])


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _evidence_summary(stage: dict[str, Any]) -> str:
    risks = ", ".join(stage.get("hidden_risks", []))
    defenses = ", ".join(defense.get("label", "") for defense in stage.get("critical_defenses", []))
    return f"관련 사례: {stage.get('source_case')} / 숨은 위험: {risks} / 핵심 방어: {defenses}"


def _give_up_explanation(stage: dict[str, Any]) -> str:
    return f"정답 해설: {stage.get('hint')} 핵심 방어는 {_evidence_summary(stage)}"


def _feedback_text(state: DefenseSimulationState) -> str:
    if state.get("input_type") == "COMMAND":
        return state.get("command_response") or "명령어를 처리했습니다."
    if state.get("stage_status") in {"STAGE_CLEAR", "COMPLETED"}:
        labels = [item.get("label") for item in state.get("detected_defenses", [])]
        return "좋은 방어입니다. 확인한 항목: " + ", ".join(labels)
    if state.get("stage_status") == "GAME_OVER":
        return state.get("game_over_reason") or "위험 노출이 너무 커져 시뮬레이션이 종료되었습니다."
    missed = [item.get("label") for item in state.get("missed_defenses", [])]
    return "아직 부족합니다. 놓친 방어 항목: " + ", ".join(missed)


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