"""Legal consultation graph entrypoint."""
from __future__ import annotations

import json
from typing import Any

from common.nodes.legal_consultation_nodes import (
    consultation_report_node,
    counselor_agent_node,
    legal_guardrail_node,
    legal_intake_node,
    legal_rag_agent_node,
    legal_supervisor_node,
    route_after_legal_rag,
    route_after_legal_supervisor,
)
from common.states.legal_consultation_state import LegalConsultationState


def build_legal_consultation_graph():
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(LegalConsultationState)
    graph.add_node("legal_intake", legal_intake_node)
    graph.add_node("legal_supervisor", legal_supervisor_node)
    graph.add_node("legal_rag_agent", legal_rag_agent_node)
    graph.add_node("counselor_agent", counselor_agent_node)
    graph.add_node("legal_guardrail", legal_guardrail_node)
    graph.add_node("consultation_report", consultation_report_node)

    graph.add_edge(START, "legal_intake")
    graph.add_edge("legal_intake", "legal_supervisor")
    graph.add_conditional_edges(
        "legal_supervisor",
        route_after_legal_supervisor,
        {
            "legal_rag_agent": "legal_rag_agent",
            "counselor_agent": "counselor_agent",
        },
    )
    graph.add_conditional_edges(
        "legal_rag_agent",
        route_after_legal_rag,
        {
            "counselor_agent": "counselor_agent",
            "legal_guardrail": "legal_guardrail",
        },
    )
    graph.add_edge("counselor_agent", "legal_guardrail")
    graph.add_edge("legal_guardrail", "consultation_report")
    graph.add_edge("consultation_report", END)
    return graph.compile()


def run_legal_consultation(
    question: str | None = None,
    related_finding: dict[str, Any] | None = None,
    contract_context: dict[str, Any] | None = None,
    session_id: str = "legal-demo-session",
    conversation_history: list[dict[str, str]] | None = None,
    user_question: str | None = None,
) -> LegalConsultationState:
    resolved_question = (user_question if user_question is not None else question) or ""
    if related_finding or contract_context:
        context_parts = []
        if related_finding:
            context_parts.append(f"관련 진단 항목: {related_finding}")
        if contract_context:
            context_parts.append(f"계약 문맥: {contract_context}")
        if context_parts:
            resolved_question = f"{resolved_question}\n\n" + "\n".join(context_parts)

    initial_state: LegalConsultationState = {
        "session_id": session_id,
        "user_question": resolved_question,
        "conversation_history": list(conversation_history or []),
        "agent_trace": [],
        "errors": [],
        "evidence_refs": [],
    }
    try:
        return build_legal_consultation_graph().invoke(initial_state)
    except ModuleNotFoundError:
        return _run_without_langgraph(initial_state)


def _run_without_langgraph(state: LegalConsultationState) -> LegalConsultationState:
    state = legal_intake_node(state)
    state = legal_supervisor_node(state)
    route = route_after_legal_supervisor(state)
    if route == "legal_rag_agent":
        state = legal_rag_agent_node(state)
        if route_after_legal_rag(state) == "counselor_agent":
            state = counselor_agent_node(state)
    else:
        state = counselor_agent_node(state)
    state = legal_guardrail_node(state)
    return consultation_report_node(state)


def run_interactive() -> LegalConsultationState:
    print("\n[법률상담 AI Graph]")
    question = input("> ").strip()
    return run_legal_consultation(question=question, session_id="interactive-legal-session")


if __name__ == "__main__":
    print(json.dumps(run_interactive().get("report", {}), ensure_ascii=False, indent=2))
