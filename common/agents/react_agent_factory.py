"""Reusable LangGraph ReAct agent builders for LLM-driven agent steps."""
from __future__ import annotations

import os
from typing import Any, Sequence

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from common.tools.llm import ENABLE_LLM, build_chat_ollama

ENABLE_REACT_AGENTS = os.getenv("ENABLE_REACT_AGENTS", "1") not in {"0", "false", "False", "no"}

_AGENT_CACHE: dict[str, Any] = {}


def invoke_react_agent(
    *,
    name: str,
    system_prompt: str,
    user_prompt: str,
    tools: Sequence[BaseTool] | None = None,
    temperature: float = 0.1,
) -> str | None:
    """Run a LangGraph prebuilt ReAct agent and return the final message content.

    The project keeps deterministic state transitions in graph nodes, but LLM-led
    judgement steps call this helper so they are backed by a real LangGraph
    ReAct agent with tool access. If local Ollama/tool-calling is unavailable,
    callers can safely fall back to deterministic MVP logic.
    """
    if not ENABLE_LLM or not ENABLE_REACT_AGENTS:
        return None

    tool_list = list(tools or [])
    cache_key = f"{name}:{temperature}:{','.join(tool.name for tool in tool_list)}"
    try:
        agent = _AGENT_CACHE.get(cache_key)
        if agent is None:
            model = build_chat_ollama(temperature=temperature)
            agent = create_react_agent(
                model=model,
                tools=tool_list,
                prompt=system_prompt,
                name=name,
            )
            _AGENT_CACHE[cache_key] = agent

        result = agent.invoke({"messages": [("user", user_prompt)]})
        messages = result.get("messages", []) if isinstance(result, dict) else []
        if not messages:
            return None
        last_message = messages[-1]
        return _message_content(last_message)
    except Exception:
        return None


def _message_content(message: BaseMessage | Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(item))
        return "\n".join(parts).strip()
    return str(content).strip()