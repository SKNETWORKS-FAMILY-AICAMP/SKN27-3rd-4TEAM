"""Diagnosis graph entrypoint.

The graph is intentionally sequential for MVP, but each step is isolated as an agent
node so routing/supervision can be added later without rewriting the agents.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Callable

from common.agents.diagnosis_nodes import (
    contract_field_extractor_agent,
    contract_intake_agent,
    contract_parser_agent,
    market_analyzer_agent,
    report_writer_agent,
    required_check_analyzer_agent,
    risk_judge_agent,
    special_clause_analyzer_agent,
)
from common.schemas.diagnosis import DiagnosisState

NODE_SEQUENCE: list[tuple[str, Callable[[DiagnosisState], DiagnosisState]]] = [
    ("contract_intake", contract_intake_agent),
    ("contract_parser", contract_parser_agent),
    ("contract_field_extractor", contract_field_extractor_agent),
    ("special_clause_analyzer", special_clause_analyzer_agent),
    ("market_analyzer", market_analyzer_agent),
    ("required_check_analyzer", required_check_analyzer_agent),
    ("risk_judge", risk_judge_agent),
    ("report_writer", report_writer_agent),
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


if __name__ == "__main__":
    result = run_diagnosis()
    print(json.dumps(result.get("report", result), ensure_ascii=False, indent=2, default=_json_default))

