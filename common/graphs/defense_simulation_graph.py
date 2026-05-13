"""Jeonse fraud defense simulation graph entrypoint."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
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

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "defense_scenarios.json"

NODE_SEQUENCE: list[tuple[str, Callable[[DefenseSimulationState], DefenseSimulationState]]] = [
    ("campaign_loader", campaign_loader_node),
    ("stage_loader", stage_loader_node),
    ("input_router", input_router_node),
    ("command_handler", command_handler_node),
    ("user_action_interpreter", user_action_interpreter_node),
    ("roleplay", roleplay_node),
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
    conversation_history: list[dict[str, str]] | None = None,
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
        "conversation_history": list(conversation_history or []),
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


def _load_categories() -> list[dict]:
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    return data.get("categories", [])


def _select_category() -> str:
    categories = _load_categories()
    print("\n플레이할 예방 시나리오를 선택하세요. 비워두면 1번으로 시작합니다.\n")
    for index, category in enumerate(categories, 1):
        print(f"{index}. {category.get('title')} - {category.get('description')}")

    selected = input("> ").strip()
    if not selected:
        return categories[0]["category_id"]
    if selected.isdigit():
        index = max(1, min(int(selected), len(categories)))
        return categories[index - 1]["category_id"]
    return selected


def _print_turn_summary(report: dict) -> None:
    print("\n" + "=" * 72)
    print(f"[{report.get('category_title')}] {report.get('stage_title')}")
    print(f"사례 기반: {report.get('source_case')}")
    print("-" * 72)
    print("상황")
    print(report.get("roleplay_message") or "상황 메시지가 없습니다.")

    if report.get("feedback"):
        print("\n피드백")
        print(report["feedback"])

    if report.get("normalized_user_action"):
        print("\n해석된 대응")
        print(report["normalized_user_action"])
    if report.get("intent_summary"):
        print(f"의도 요약: {report['intent_summary']}")
    if report.get("abusive_language"):
        print(f"폭언 감지: {report.get('abusive_reason')}")

    if report.get("detected_defenses"):
        labels = ", ".join(item.get("label", "") for item in report["detected_defenses"])
        print(f"\n확인한 방어 행동: {labels}")
    if report.get("missed_defenses"):
        labels = ", ".join(item.get("label", "") for item in report["missed_defenses"])
        print(f"놓친 방어 행동: {labels}")

    print("\n상태")
    print(f"단계: {report.get('stage_status')} / 게임: {report.get('game_status')} / 위험노출: {report.get('risk_exposure')} / 방어점수: {report.get('defense_score')}")
    if report.get("ending_type"):
        print(f"엔딩: {report.get('ending_type')}")

    next_stage = report.get("next_stage")
    if next_stage:
        print(f"다음 단계: {next_stage.get('title')}")
    print("=" * 72)


def run_interactive() -> DefenseSimulationState:
    print("\n[전세사기 방어 RPG 그래프]")
    category_id = _select_category()

    result: DefenseSimulationState = {
        "category_id": category_id,
        "current_stage_index": 0,
        "risk_exposure": 0,
        "failed_stage_count": 0,
        "hint_used_count": 0,
        "game_status": "PLAYING",
    }

    result = run_defense_simulation(
        category_id=category_id,
        user_message="/도움말",
        session_id="interactive-defense-session",
    )
    _print_turn_summary(result.get("report", result))

    print("\n당신의 대응을 입력하세요.")
    print("예: 등기부를 인터넷등기소에서 직접 발급하고, 신탁원부와 계약 권한자를 확인하겠습니다.")
    print("명령어: /힌트, /상태, /근거, /도움말, /포기, /json")
    print("종료: /종료, exit, quit")

    while True:
        user_message = input("> ").strip() or "/도움말"
        if user_message.lower() in {"/종료", "exit", "quit"}:
            return result
        if user_message == "/json":
            print(json.dumps(result.get("report", result), ensure_ascii=False, indent=2, default=_json_default))
            continue

        result = run_defense_simulation(
            category_id=category_id,
            user_message=user_message,
            current_stage_index=int(result.get("current_stage_index", 0)),
            session_id="interactive-defense-session",
            risk_exposure=int(result.get("risk_exposure", 0)),
            failed_stage_count=int(result.get("failed_stage_count", 0)),
            hint_used_count=int(result.get("hint_used_count", 0)),
            conversation_history=list(result.get("conversation_history", [])),
        )

        _print_turn_summary(result.get("report", result))
        if result.get("game_status") in {"GAME_OVER", "COMPLETED"}:
            return result


if __name__ == "__main__":
    run_interactive()
