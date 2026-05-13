"""Case-based legal consultation graph entrypoint.

[조건부 분기 흐름]

    START
      │
    legal_intake → question_classifier
      │
    internal_case_retriever → internal_law_guide_retriever
      │
    evidence_grader
      │
      ├─ needs_external_search=True  → external_search ──┐
      └─ needs_external_search=False (증거 충분) ──────────┘
                                                          ↓
                                               citation_collector
                                                          │
                                               case_based_answer → legal_guardrail
                                                          │
                                               consultation_report → END

evidence_grader 에서 내부 판례·법령 근거가 충분하면 (sufficient=True)
external_search 를 건너뛰어 응답 속도를 높이고 불필요한 외부 호출을 줄입니다.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Literal

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

# 선형 실행 순서 (LangGraph 미설치 fallback 용)
_LINEAR_SEQUENCE: list[tuple[str, Callable[[LegalConsultationState], LegalConsultationState]]] = [
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


# ── 조건부 라우팅 함수 ────────────────────────────────────────────────

def _route_after_evidence_grader(
    state: LegalConsultationState,
) -> Literal["external_search", "citation_collector"]:
    """evidence_grader 결과에 따라 분기합니다.

    - needs_external_search=True  → external_search 노드 실행
    - needs_external_search=False → external_search 건너뛰고 citation_collector로 직행
    """
    if state.get("needs_external_search", False):
        print("[LegalGraph] 내부 근거 부족 → external_search 실행")
        return "external_search"
    print("[LegalGraph] 내부 근거 충분 → external_search 생략, citation_collector로 이동")
    return "citation_collector"


# ── 그래프 빌더 ───────────────────────────────────────────────────────

def build_legal_consultation_graph():
    """조건부 분기를 포함한 LangGraph StateGraph 빌드."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(LegalConsultationState)

    # 노드 등록
    for node_name, node_fn in _LINEAR_SEQUENCE:
        graph.add_node(node_name, node_fn)

    # ── 선형 구간 ─────────────────────────────────────────────────────
    graph.add_edge(START, "legal_intake")
    graph.add_edge("legal_intake", "question_classifier")
    graph.add_edge("question_classifier", "internal_case_retriever")
    graph.add_edge("internal_case_retriever", "internal_law_guide_retriever")
    graph.add_edge("internal_law_guide_retriever", "evidence_grader")

    # ── 조건부 분기: evidence_grader → external_search or citation_collector ──
    graph.add_conditional_edges(
        "evidence_grader",
        _route_after_evidence_grader,
        {
            "external_search": "external_search",
            "citation_collector": "citation_collector",
        },
    )

    # external_search 실행 후 citation_collector로 합류
    graph.add_edge("external_search", "citation_collector")

    # ── 합류 이후 선형 구간 ───────────────────────────────────────────
    graph.add_edge("citation_collector", "case_based_answer")
    graph.add_edge("case_based_answer", "legal_guardrail")
    graph.add_edge("legal_guardrail", "consultation_report")
    graph.add_edge("consultation_report", END)

    return graph.compile()


# ── 공개 실행 함수 ────────────────────────────────────────────────────

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
        # LangGraph 미설치: 선형 순차 실행 (external_search는 needs_external_search 플래그로 내부 제어)
        state = initial_state
        for _, node in _LINEAR_SEQUENCE:
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
