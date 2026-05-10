"""Case-based legal consultation graph entrypoint."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from common.agents.legal_consultation_nodes import (
    case_based_answer_agent,
    citation_collector_agent,
    consultation_report_agent,
    evidence_grader_agent,
    external_search_agent,
    internal_case_retriever_agent,
    internal_law_guide_retriever_agent,
    legal_guardrail_agent,
    legal_intake_agent,
    question_classifier_agent,
)
from common.schemas.legal_consultation import LegalConsultationState

NODE_SEQUENCE: list[tuple[str, Callable[[LegalConsultationState], LegalConsultationState]]] = [
    ("legal_intake", legal_intake_agent),
    ("question_classifier", question_classifier_agent),
    ("internal_case_retriever", internal_case_retriever_agent),
    ("internal_law_guide_retriever", internal_law_guide_retriever_agent),
    ("evidence_grader", evidence_grader_agent),
    ("external_search", external_search_agent),
    ("citation_collector", citation_collector_agent),
    ("case_based_answer", case_based_answer_agent),
    ("legal_guardrail", legal_guardrail_agent),
    ("consultation_report", consultation_report_agent),
]


def build_legal_consultation_graph():
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(LegalConsultationState)
    for node_name, node_fn in NODE_SEQUENCE:
        graph.add_node(node_name, node_fn)

    graph.add_edge(START, NODE_SEQUENCE[0][0])
    for (current_name, _), (next_name, _) in zip(NODE_SEQUENCE, NODE_SEQUENCE[1:]):
        graph.add_edge(current_name, next_name)
    graph.add_edge(NODE_SEQUENCE[-1][0], END)
    return graph.compile()


def run_legal_consultation(
    question: str,
    related_finding: dict[str, Any] | None = None,
    contract_context: dict[str, Any] | None = None,
    session_id: str = "legal-demo-session",
) -> LegalConsultationState:
    initial_state: LegalConsultationState = {
        "session_id": session_id,
        "question": question,
        "related_finding": related_finding,
        "contract_context": contract_context,
        "agent_trace": [],
        "errors": [],
        "used_external_search": False,
    }
    try:
        graph = build_legal_consultation_graph()
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
    result = run_legal_consultation(
        question="보증금 반환은 다음 임차인 입주 이후에 한다는 특약이 위험한가요? 판례 근거가 있나요?",
        related_finding={
            "code": "CLAUSE_LATE_RETURN",
            "title": "보증금 반환 지연 가능 특약",
            "description": "보증금 반환 시점을 과도하게 늦추는 문구는 반환 위험을 키울 수 있습니다.",
        },
        contract_context={
            "special_terms": ["보증금 반환은 다음 임차인 입주 이후에 한다."],
            "deposit_amount": 9500,
            "housing_type": "오피스텔",
        },
    )
    print(json.dumps(result.get("report", result), ensure_ascii=False, indent=2, default=_json_default))
