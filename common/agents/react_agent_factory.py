"""Small ReAct-agent adapter used by graph agent wrappers.

This module keeps the rest of the codebase independent from a specific
LangChain/LangGraph agent API.  If a full ReAct implementation is available it
can be plugged in here; otherwise we fall back to direct LLM generation so the
graphs still run in local/test environments.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from common.tools.llm import LLMUnavailable, llm_generate


def invoke_react_agent(
    *,
    name: str,
    system_prompt: str,
    user_prompt: str,
    tools: Iterable[Callable[..., Any]] | None = None,
    temperature: float = 0.1,
) -> str | None:
    """Invoke a lightweight ReAct-style agent and return text output.

    The current project nodes only require a text result.  Tool-enabled agent
    runtimes differ by installed dependency versions, so this adapter provides a
    stable internal contract and a deterministic fallback.
    """
    tool_descriptions = _describe_tools(tools or [])
    prompt = user_prompt
    if tool_descriptions:
        prompt = (
            f"{user_prompt}\n\n"
            "Available tools:\n"
            f"{tool_descriptions}\n\n"
            "Use the retrieved context when it is relevant, then answer briefly."
        )

    try:
        return llm_generate(
            prompt,
            system=f"{system_prompt}\n\nAgent name: {name}",
            temperature=temperature,
        )
    except LLMUnavailable:
        return None
    except Exception:
        return None


def _describe_tools(tools: Iterable[Callable[..., Any]]) -> str:
    descriptions: list[str] = []
    for tool in tools:
        tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", tool.__class__.__name__)
        description = getattr(tool, "description", None) or getattr(tool, "__doc__", "") or ""
        descriptions.append(f"- {tool_name}: {str(description).strip()}")
    return "\n".join(descriptions)
