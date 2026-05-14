"""TypedDict state for the legal consultation graph."""
from __future__ import annotations

from typing import Any, TypedDict


class LegalConsultationState(TypedDict, total=False):
    session_id: str
    user_question: str
    conversation_history: list[dict[str, str]]

    intent: str
    question_type: str | None
    route: str
    needs_rag: bool
    needs_clarification: bool
    clarification_questions: list[str]
    reason: str
    supervisor_status: str

    legal_rag_result: dict[str, Any]
    counselor_result: dict[str, Any]

    current_task: str | None
    current_agent: str | None
    review_count: int
    max_review_count: int
    review_result: dict[str, Any]
    claims: list[dict[str, Any]]
    legal_points: list[str]
    evidence_refs: list[dict[str, Any]]
    graph_context: list[dict[str, Any]]
    fallback_level: str | None
    safe_fallback: dict[str, Any]

    draft_answer: str
    safe_answer: str
    report: dict[str, Any]

    agent_trace: list[dict[str, Any]]
    errors: list[str]
