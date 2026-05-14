"""Local LLM helper for pcj_common agents.

This replaces the former shared-package dependency so pcj_common can run on its
own.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*args, **kwargs):
        return False

from langchain_openai import ChatOpenAI

load_dotenv()


def build_chat_llm(*, temperature: float = 0.0) -> ChatOpenAI:
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=api_key,
            temperature=temperature,
            timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
        )

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    return ChatOpenAI(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        api_key=api_key,
        base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        temperature=temperature,
        timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
    )
