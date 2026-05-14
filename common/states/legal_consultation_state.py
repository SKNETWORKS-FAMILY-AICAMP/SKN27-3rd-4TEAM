"""TypedDict state for the legal consultation graph."""
from __future__ import annotations

from typing import Any, TypedDict


class LegalConsultationState(TypedDict, total=False):
    session_id: str
    user_question: str
    conversation_history: list

    intent: str
    question_type: str
    route: str
    needs_rag: bool
    needs_clarification: bool
    clarification_questions: list
    reason: str
    supervisor_status: str

    legal_rag_result: dict
    counselor_result: dict

    current_task: str
    current_agent: str
    review_count: int
    max_review_count: int
    review_result: dict
    last_review_status: str
    claims: list
    legal_points: list
    evidence_refs: list
    graph_context: list
    fallback_level: str
    safe_fallback: dict

    # legal_consultation_nodes.py 필드
    question: str
    normalized_query: str
    question_type: str
    internal_case_context: Any
    internal_law_context: Any
    cited_cases: list
    cited_laws: list
    external_sources: list
    answer_draft: str
    recommended_actions: list
    basis_type: str
    evidence_quality: Any
    confidence: str
    needs_external_search: bool
    used_external_search: bool
    final_answer: str
    disclaimer: str

    draft_answer: str
    safe_answer: str
    report: dict

    agent_trace: list
    errors: list
