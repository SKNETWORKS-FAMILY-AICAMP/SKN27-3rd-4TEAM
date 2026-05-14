"""v7 PDF-first contract diagnosis LangGraph entrypoint."""
from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, is_dataclass
from typing import Any

from common.nodes.diagnosis_nodes import (
    contract_field_extractor_node,
    contract_intake_node,
    contract_parser_node,
    contract_review_node,
    contract_supervisor_node,
    extra_rag_search_node,
    graph_context_node,
    insurance_risk_agent_node,
    legal_basis_agent_node,
    market_risk_agent_node,
    ownership_risk_agent_node,
    report_writer_node,
    required_check_agent_node,
    risk_judge_node,
    route_after_extra_rag,
    route_after_graph_context,
    route_after_review,
    route_after_supervisor,
    safe_contract_fallback_node,
    special_clause_agent_node,
)
from common.schemas.diagnosis import DiagnosisState


# ── JSON 저장 노드 (flowchart: "JSON 저장 - 진단 결과 persist") ───────────────

def json_save_node(state: DiagnosisState) -> DiagnosisState:
    """report_writer 결과를 JSON 파일로 저장하여 chat의 JSON reader가 불러올 수 있게 함."""
    session_id = state.get("session_id", "unknown")
    report = state.get("report", {})

    save_dir = pathlib.Path(__file__).resolve().parents[2] / "data" / "diagnosis_results"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{session_id}.json"

    payload = {
        "session_id": session_id,
        "risk_score": state.get("risk_score", 0),
        "risk_level": state.get("risk_level", "UNKNOWN"),
        "report": report,
        "contract_file": state.get("contract_file"),
    }

    try:
        save_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        saved_path = str(save_path)
    except Exception as exc:
        saved_path = None
        print(f"[json_save_node] 저장 실패: {exc}")

    return {**dict(state), "saved_json_path": saved_path}


def build_diagnosis_graph():
    """Build the v7 task-queue + review-supervisor diagnosis graph."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(DiagnosisState)
    graph.add_node("contract_intake", contract_intake_node)
    graph.add_node("contract_parser", contract_parser_node)
    graph.add_node("contract_field_extractor", contract_field_extractor_node)
    graph.add_node("contract_supervisor", contract_supervisor_node)
    graph.add_node("special_clause", special_clause_agent_node)
    graph.add_node("ownership_risk", ownership_risk_agent_node)
    graph.add_node("market_risk", market_risk_agent_node)
    graph.add_node("insurance_risk", insurance_risk_agent_node)
    graph.add_node("required_check", required_check_agent_node)
    graph.add_node("legal_basis", legal_basis_agent_node)
    graph.add_node("contract_review_node", contract_review_node)
    graph.add_node("extra_rag_search", extra_rag_search_node)
    graph.add_node("graph_context_node", graph_context_node)
    graph.add_node("safe_contract_fallback", safe_contract_fallback_node)
    graph.add_node("risk_judge", risk_judge_node)
    graph.add_node("report_writer", report_writer_node)
    graph.add_node("json_save", json_save_node)

    graph.add_edge(START, "contract_intake")
    graph.add_conditional_edges(
        "contract_intake",
        _route_after_intake,
        {"parse": "contract_parser", "report": "report_writer"},
    )
    graph.add_edge("contract_parser", "contract_field_extractor")
    graph.add_edge("contract_field_extractor", "contract_supervisor")
    graph.add_conditional_edges(
        "contract_supervisor",
        route_after_supervisor,
        {
            "special_clause": "special_clause",
            "ownership_risk": "ownership_risk",
            "market_risk": "market_risk",
            "insurance_risk": "insurance_risk",
            "required_check": "required_check",
            "legal_basis": "legal_basis",
            "judge": "risk_judge",
        },
    )
    for node in ["special_clause", "ownership_risk", "market_risk", "insurance_risk", "required_check", "legal_basis"]:
        graph.add_edge(node, "contract_review_node")
    graph.add_conditional_edges(
        "contract_review_node",
        route_after_review,
        {
            "supervisor": "contract_supervisor",
            "extra_rag": "extra_rag_search",
            "graph_context": "graph_context_node",
            "special_clause": "special_clause",
            "ownership_risk": "ownership_risk",
            "market_risk": "market_risk",
            "insurance_risk": "insurance_risk",
            "required_check": "required_check",
            "legal_basis": "legal_basis",
            "fallback": "safe_contract_fallback",
        },
    )
    graph.add_conditional_edges(
        "extra_rag_search",
        route_after_extra_rag,
        {
            "special_clause": "special_clause",
            "ownership_risk": "ownership_risk",
            "market_risk": "market_risk",
            "insurance_risk": "insurance_risk",
            "required_check": "required_check",
            "legal_basis": "legal_basis",
            "fallback": "safe_contract_fallback",
        },
    )
    graph.add_conditional_edges(
        "graph_context_node",
        route_after_graph_context,
        {
            "special_clause": "special_clause",
            "ownership_risk": "ownership_risk",
            "market_risk": "market_risk",
            "insurance_risk": "insurance_risk",
            "required_check": "required_check",
            "legal_basis": "legal_basis",
            "fallback": "safe_contract_fallback",
        },
    )
    graph.add_edge("safe_contract_fallback", "contract_supervisor")
    graph.add_edge("risk_judge", "report_writer")
    graph.add_edge("report_writer", "json_save")  # flowchart: persist diagnosis JSON
    graph.add_edge("json_save", END)
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
        "pending_tasks": [],
        "completed_tasks": [],
        "review_count": 0,
        "max_review_count": 2,
        "claims": [],
        "legal_points": [],
        "evidence_refs": [],
        "graph_context": [],
    }
    try:
        return build_diagnosis_graph().invoke(initial_state, config={"recursion_limit": 100})
    except ModuleNotFoundError:
        return _run_without_langgraph(initial_state)


def _route_after_intake(state: DiagnosisState) -> str:
    return "parse" if state.get("analysis_ready") else "report"


def _run_without_langgraph(state: DiagnosisState) -> DiagnosisState:
    state = contract_intake_node(state)
    if not state.get("analysis_ready"):
        return report_writer_node(state)
    state = contract_parser_node(state)
    state = contract_field_extractor_node(state)
    state = contract_supervisor_node(state)
    while route_after_supervisor(state) != "judge":
        route = route_after_supervisor(state)
        agent = {
            "special_clause": special_clause_agent_node,
            "ownership_risk": ownership_risk_agent_node,
            "market_risk": market_risk_agent_node,
            "insurance_risk": insurance_risk_agent_node,
            "required_check": required_check_agent_node,
            "legal_basis": legal_basis_agent_node,
        }[route]
        state = agent(state)
        state = contract_review_node(state)
        if route_after_review(state) == "extra_rag":
            state = extra_rag_search_node(state)
            state = agent(state)
            state = contract_review_node(state)
        if route_after_review(state) == "graph_context":
            state = graph_context_node(state)
            state = agent(state)
            state = contract_review_node(state)
        if route_after_review(state) == "fallback":
            state = safe_contract_fallback_node(state)
        state = contract_supervisor_node(state)
    state = risk_judge_node(state)
    state = report_writer_node(state)
    return json_save_node(state)


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def run_interactive() -> DiagnosisState:
    print("\n[전세계약 PDF 진단 그래프 v7]")
    print("계약서 PDF/TXT 경로를 입력하세요. 비워두면 mock 계약서로 실행합니다.")
    contract_file = input("> ").strip() or None
    return run_diagnosis(contract_file=contract_file, session_id="interactive-diagnosis-session")


if __name__ == "__main__":
    result = run_interactive()
    print(json.dumps(result.get("report", result), ensure_ascii=False, indent=2, default=_json_default))
