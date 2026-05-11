"""Small Ollama client used by optional LLM-powered agent steps."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

try:
    from langchain_ollama import ChatOllama
except ImportError:  # fallback for environments not yet updated
    from langchain_community.chat_models import ChatOllama
from langchain_core.tools import tool

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")
ENABLE_LLM = os.getenv("ENABLE_LLM", "1") not in {"0", "false", "False", "no"}


class LLMUnavailable(RuntimeError):
    pass


def build_chat_ollama(*, temperature: float = 0.1) -> ChatOllama:
    """Build a LangChain chat model adapter for LangGraph ReAct agents."""
    if not ENABLE_LLM:
        raise LLMUnavailable("LLM disabled by ENABLE_LLM=0")
    return ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=temperature)


def ollama_generate(prompt: str, *, system: str | None = None, temperature: float = 0.1) -> str:
    if not ENABLE_LLM:
        raise LLMUnavailable("LLM disabled by ENABLE_LLM=0")

    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system:
        payload["system"] = system

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMUnavailable(str(exc)) from exc

    return str(result.get("response", "")).strip()


def extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort JSON object extraction for local models that add prose."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    candidate = fenced.group(1) if fenced else text
    if "{" in candidate and "}" in candidate:
        candidate = candidate[candidate.find("{"): candidate.rfind("}") + 1]
    return json.loads(candidate)


@tool
def ollama_generate_tool(prompt: str, system: str | None = None, temperature: float = 0.1) -> str:
    """Generate text with the configured local Ollama model."""
    return ollama_generate(prompt=prompt, system=system, temperature=temperature)