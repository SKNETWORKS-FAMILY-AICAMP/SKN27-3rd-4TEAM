"""PDF-first contract diagnosis LangGraph entrypoint."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from common.nodes.diagnosis_nodes import (
    contract_field_extractor_node,
    contract_intake_node,
    contract_parser_node,
    contract_supervisor_node,
    ownership_risk_agent_node,
    report_writer_node,
    risk_judge_node,
    special_clause_agent_node,
)
from common.schemas.diagnosis import DiagnosisState


def build_diagnosis_graph():
    """Build a conditional LangGraph for contract diagnosis."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(DiagnosisState)
    graph.add_node("contract_intake", contract_intake_node)
    graph.add_node("contract_parser", contract_parser_node)
    graph.add_node("contract_field_extractor", contract_field_extractor_node)
    graph.add_node("contract_supervisor", contract_supervisor_node)
    graph.add_node("special_clause_agent", special_clause_agent_node)
    graph.add_node("ownership_risk_agent", ownership_risk_agent_node)
    graph.add_node("risk_judge", risk_judge_node)
    graph.add_node("report_writer", report_writer_node)

    graph.add_edge(START, "contract_intake")
    graph.add_conditional_edges(
        "contract_intake",
        _route_after_intake,
        {
            "parse": "contract_parser",
            "report": "report_writer",
        },
    )
    graph.add_edge("contract_parser", "contract_field_extractor")
    graph.add_edge("contract_field_extractor", "contract_supervisor")
    graph.add_conditional_edges(
        "contract_supervisor",
        _route_after_supervisor,
        {
            "special_clause": "special_clause_agent",
            "ownership": "ownership_risk_agent",
            "judge": "risk_judge",
        },
    )
    graph.add_edge("special_clause_agent", "ownership_risk_agent")
    graph.add_edge("ownership_risk_agent", "risk_judge")
    graph.add_edge("risk_judge", "report_writer")
    graph.add_edge("report_writer", END)
    return graph.compile()


def run_diagnosis(contract_file: str | None = None, session_id: str = "demo-session") -> DiagnosisState:
    initial_state: DiagnosisState = {
        "session_id": session_id,
        "contract_file": contract_file,
        "analysis_ready": False,
        "errors": [],
        "missing_inputs": [],
        "context_packs": {},
        "task_results": {},
        "agent_trace": [],
    }
    try:
        graph = build_diagnosis_graph()
        return graph.invoke(initial_state)
    except ModuleNotFoundError:
        return _run_without_langgraph(initial_state)


def _route_after_intake(state: DiagnosisState) -> str:
    return "parse" if state.get("analysis_ready") else "report"


def _route_after_supervisor(state: DiagnosisState) -> str:
    plan = state.get("diagnosis_plan")
    if plan and plan.run_special_clause:
        return "special_clause"
    if plan and plan.run_ownership_risk:
        return "ownership"
    return "judge"


def _run_without_langgraph(state: DiagnosisState) -> DiagnosisState:
    state = contract_intake_node(state)
    if not state.get("analysis_ready"):
        return report_writer_node(state)
    state = contract_parser_node(state)
    state = contract_field_extractor_node(state)
    state = contract_supervisor_node(state)
    plan = state.get("diagnosis_plan")
    if plan and plan.run_special_clause:
        state = special_clause_agent_node(state)
    if plan and plan.run_ownership_risk:
        state = ownership_risk_agent_node(state)
    state = risk_judge_node(state)
    return report_writer_node(state)


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def run_interactive() -> DiagnosisState:
    print("\n[전세계약 PDF 진단 그래프]")
    print("계약서 PDF/TXT 경로를 입력하세요. 비워두면 mock 계약서로 실행합니다.")
    contract_file = input("> ").strip() or None
    return run_diagnosis(contract_file=contract_file, session_id="interactive-diagnosis-session")


if __name__ == "__main__":
    result = run_interactive()
    print(json.dumps(result.get("report", result), ensure_ascii=False, indent=2, default=_json_default))
