"""Small deterministic helpers for counselor agent prompts."""
from __future__ import annotations

from typing import Any

try:
    from langchain_core.tools import tool
except ImportError:  # pragma: no cover
    def tool(func):
        return func


def summarize_user_context(user_question: str, conversation_history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "question": user_question.strip(),
        "history_turns": len(conversation_history or []),
        "has_prior_context": bool(conversation_history),
    }


@tool
def summarize_user_context_tool(user_question: str, conversation_history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Summarize user context for counselor wording."""
    return summarize_user_context(user_question, conversation_history)
