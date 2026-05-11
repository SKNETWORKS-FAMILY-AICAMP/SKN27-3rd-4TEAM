"""Jeonse fraud defense simulation graph entrypoint."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Callable

from common.nodes.defense_simulation_nodes import (
    campaign_loader_node,
    command_handler_node,
    defense_judge_node,
    evidence_connector_node,
    feedback_report_node,
    input_router_node,
    roleplay_node,
    stage_loader_node,
    stage_result_node,
    user_action_interpreter_node,
)
from common.schemas.defense_simulation import DefenseSimulationState

NODE_SEQUENCE: list[tuple[str, Callable[[DefenseSimulationState], DefenseSimulationState]]] = [
    ("campaign_loader", campaign_loader_node),
    ("stage_loader", stage_loader_node),
    ("roleplay", roleplay_node),
    ("input_router", input_router_node),
    ("command_handler", command_handler_node),
    ("user_action_interpreter", user_action_interpreter_node),
    ("defense_judge", defense_judge_node),
    ("stage_result", stage_result_node),
    ("evidence_connector", evidence_connector_node),
    ("feedback_report", feedback_report_node),
]


def build_defense_simulation_graph():
    """Build the LangGraph workflow for one RPG simulation turn."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(DefenseSimulationState)
    for node_name, node_fn in NODE_SEQUENCE:
        graph.add_node(node_name, node_fn)

    graph.add_edge(START, NODE_SEQUENCE[0][0])
    for (current_name, _), (next_name, _) in zip(NODE_SEQUENCE, NODE_SEQUENCE[1:]):
        graph.add_edge(current_name, next_name)
    graph.add_edge(NODE_SEQUENCE[-1][0], END)
    return graph.compile()


def run_defense_simulation(
    category_id: str = "RIGHTS_CONCEALMENT",
    user_message: str = "/도움말",
    current_stage_index: int = 0,
    session_id: str = "defense-demo-session",
    risk_exposure: int = 0,
    failed_stage_count: int = 0,
    hint_used_count: int = 0,
) -> DefenseSimulationState:
    initial_state: DefenseSimulationState = {
        "session_id": session_id,
        "category_id": category_id,
        "current_stage_index": current_stage_index,
        "user_message": user_message,
        "risk_exposure": risk_exposure,
        "failed_stage_count": failed_stage_count,
        "hint_used_count": hint_used_count,
        "agent_trace": [],
        "errors": [],
        "conversation_history": [],
        "game_status": "PLAYING",
    }
    try:
        graph = build_defense_simulation_graph()
        return graph.invoke(initial_state)
    except ModuleNotFoundError:
        state = initial_state
        for _, node in NODE_SEQUENCE:
            state = node(state)
        return state


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def run_interactive() -> DefenseSimulationState:
    print("\n[전세사기 방어 RPG 그래프]")
    print("카테고리 ID를 입력하세요. 비워두면 RIGHTS_CONCEALMENT로 실행합니다.")
    category_id = input("> ").strip() or "RIGHTS_CONCEALMENT"
    print("\n사용자 대응을 입력하세요. 예: 등기부를 인터넷등기소에서 직접 발급해서 잔금 직전에 다시 확인하겠습니다.")
    print("명령어: /힌트, /상태, /근거, /도움말, /포기")
    user_message = input("> ").strip() or "/도움말"
    return run_defense_simulation(category_id=category_id, user_message=user_message, session_id="interactive-defense-session")


if __name__ == "__main__":
    result = run_interactive()
    print(json.dumps(result.get("report", result), ensure_ascii=False, indent=2, default=_json_default))