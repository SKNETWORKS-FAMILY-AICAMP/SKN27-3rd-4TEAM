"""Case-based legal consultation graph entrypoint.

Top-level nodes connect project state inside LangGraph. LLM judgement steps
call create_react_agent-based sub-agents that use tools under common/tools.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from common.nodes.legal_consultation_nodes import (
    case_based_answer_node,
    citation_collector_node,
    consultation_report_node,
    evidence_grader_node,
    external_search_node,
    internal_case_retriever_node,
    internal_law_guide_retriever_node,
    legal_guardrail_node,
    legal_intake_node,
    question_classifier_node,
)
from common.schemas.legal_consultation import LegalConsultationState

NODE_SEQUENCE: list[tuple[str, Callable[[LegalConsultationState], LegalConsultationState]]] = [
    ("legal_intake", legal_intake_node),
    ("question_classifier", question_classifier_node),
    ("internal_case_retriever", internal_case_retriever_node),
    ("internal_law_guide_retriever", internal_law_guide_retriever_node),
    ("evidence_grader", evidence_grader_node),
    ("external_search", external_search_node),
    ("citation_collector", citation_collector_node),
    ("case_based_answer", case_based_answer_node),
    ("legal_guardrail", legal_guardrail_node),
    ("consultation_report", consultation_report_node),
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


def run_interactive() -> LegalConsultationState:
    print("\n[법률 정보 상담 그래프]")
    print("질문을 입력하세요. 비워두면 기본 예시 질문으로 실행합니다.")
    question = input("> ").strip() or "보증금 반환은 다음 임차인 입주 이후에 한다는 특약이 위험한가요? 판례 근거가 있나요?"

    print("\n관련 특약/계약 문맥을 입력하세요. 비워두면 기본 예시 특약을 사용합니다.")
    clause = input("> ").strip() or "보증금 반환은 다음 임차인 입주 이후에 한다."

    return run_legal_consultation(
        question=question,
        related_finding={
            "code": "INTERACTIVE_LEGAL_QUESTION",
            "title": "사용자 법률 상담 질문",
            "description": question,
        },
        contract_context={"special_terms": [clause]},
        session_id="interactive-legal-session",
    )


if __name__ == "__main__":
    result = run_interactive()
    print(json.dumps(result.get("report", result), ensure_ascii=False, indent=2, default=_json_default))
