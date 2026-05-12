"""Diagnosis graph entrypoint.

Top-level nodes connect project state inside LangGraph. LLM judgement steps
call create_react_agent-based sub-agents that use tools under common/tools.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Callable

from common.nodes.diagnosis_nodes import (
    contract_field_extractor_node,
    contract_intake_node,
    contract_parser_node,
    market_analysis_node,
    report_writer_node,
    required_check_node,
    risk_judge_node,
    special_clause_analysis_node,
)
from common.schemas.diagnosis import DiagnosisState

NODE_SEQUENCE: list[tuple[str, Callable[[DiagnosisState], DiagnosisState]]] = [
    ("contract_intake", contract_intake_node),
    ("contract_parser", contract_parser_node),
    ("contract_field_extractor", contract_field_extractor_node),
    ("special_clause_analyzer", special_clause_analysis_node),
    ("market_analyzer", market_analysis_node),
    ("required_check_analyzer", required_check_node),
    ("risk_judge", risk_judge_node),
    ("report_writer", report_writer_node),
]


def build_diagnosis_graph():
    """Build a real LangGraph StateGraph when langgraph is installed."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(DiagnosisState)
    for node_name, node_fn in NODE_SEQUENCE:
        graph.add_node(node_name, node_fn)

    graph.add_edge(START, NODE_SEQUENCE[0][0])
    for (current_name, _), (next_name, _) in zip(NODE_SEQUENCE, NODE_SEQUENCE[1:]):
        graph.add_edge(current_name, next_name)
    graph.add_edge(NODE_SEQUENCE[-1][0], END)
    return graph.compile()


def run_diagnosis(contract_file: str | None = None, session_id: str = "demo-session") -> DiagnosisState:
    initial_state: DiagnosisState = {
        "session_id": session_id,
        "contract_file": contract_file,
        "analysis_ready": False,
        "missing_inputs": [],
        "context_packs": {},
        "agent_trace": [],
        "errors": [],
    }
    try:
        graph = build_diagnosis_graph()
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


def run_interactive() -> DiagnosisState:
    print("\n[전세계약 진단 그래프]")
    print("계약서 PDF/TXT 경로를 입력하세요. 비워두면 mock 계약서로 실행합니다.")
    contract_file = input("> ").strip() or None
    return run_diagnosis(contract_file=contract_file, session_id="interactive-diagnosis-session")


if __name__ == "__main__":
    result = run_interactive()
    print(json.dumps(result.get("report", result), ensure_ascii=False, indent=2, default=_json_default))
