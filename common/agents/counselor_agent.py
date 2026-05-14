"""LLM-backed friendly legal counselor agent."""
from __future__ import annotations

import json
from typing import Any

from common.schemas.legal_consultation_schema import CounselorResult
from common.tools.counselor_tools import summarize_user_context
from common.tools.llm import LLMUnavailable, extract_json_object, llm_generate


def run_counselor_agent(
    *,
    user_question: str,
    intent: str | None,
    question_type: str | None,
    legal_rag_result: dict[str, Any] | None,
    clarification_questions: list[str] | None,
    conversation_history: list[dict[str, str]] | None,
) -> CounselorResult:
    context_summary = summarize_user_context(user_question, conversation_history)
    safe_rag_view = _safe_counselor_input(legal_rag_result)
    prompt = f"""
너는 친절한 부동산 법률 상담가다.

원칙:
- 겁주지 않는다.
- 어려운 법률 용어는 쉬운 말로 바꾼다.
- 사용자의 상황을 먼저 요약한다.
- 필요한 경우 추가 확인 질문을 한다.
- 법률 판단을 단정하지 않는다.
- RAG 근거가 있으면 그 내용을 쉽게 풀어 설명한다.

반환 JSON:
{{
  "answer": "사용자에게 보여줄 상담 답변",
  "followup_questions": ["필요 시 추가 질문"]
}}

user_question:
{user_question}

intent: {intent}
question_type: {question_type}
context_summary:
{json.dumps(context_summary, ensure_ascii=False)}

legal_rag_result:
{json.dumps(safe_rag_view, ensure_ascii=False, default=str)[:8000]}

clarification_questions:
{json.dumps(clarification_questions or [], ensure_ascii=False)}
""".strip()
    try:
        data = extract_json_object(
            llm_generate(
                prompt,
                system="너는 친절한 부동산 임대차 상담가다. JSON만 반환한다.",
                temperature=0.2,
            )
        )
    except Exception as exc:
        raise LLMUnavailable(f"counselor agent failed: {exc}") from exc

    return CounselorResult(
        answer=str(data.get("answer") or ""),
        followup_questions=[str(item) for item in data.get("followup_questions", [])],
        llm_used=True,
    )


def _safe_counselor_input(legal_rag_result: dict[str, Any] | None) -> dict[str, Any]:
    """v7: counselor receives expression-layer inputs, not full mutable state."""
    data = legal_rag_result or {}
    evidence_titles = [
        str(item.get("title"))
        for item in data.get("evidence_refs", [])
        if isinstance(item, dict) and item.get("title")
    ][:5]
    return {
        "question_type": data.get("question_type"),
        "legal_points": data.get("legal_points", []),
        "answer_draft": data.get("answer_draft", ""),
        "evidence_titles": evidence_titles,
        "confidence": data.get("confidence"),
        "blocked_reason": data.get("blocked_reason"),
    }
