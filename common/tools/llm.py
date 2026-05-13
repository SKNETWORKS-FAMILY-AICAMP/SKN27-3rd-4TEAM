"""Small optional LLM helpers for structured extraction.

Agents must use an LLM-backed judgement path. The provider is configurable so
local Ollama can be swapped for Groq without changing graph/agent code.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from langchain_core.tools import tool
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", os.getenv("OLLAMA_TIMEOUT_SECONDS", "45")))
ENABLE_LLM = os.getenv("ENABLE_LLM", "1") not in {"0", "false", "False", "no"}

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://localhost:11434"))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")

GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class LLMUnavailable(RuntimeError):
    pass


def build_chat_llm(*, temperature: float = 0.0) -> ChatOpenAI:
    """Build a LangChain chat model for agent structured output."""
    if not ENABLE_LLM:
        raise LLMUnavailable("LLM disabled by ENABLE_LLM=0")
    if LLM_PROVIDER == "groq":
        if not GROQ_API_KEY:
            raise LLMUnavailable("GROQ_API_KEY is not configured")
        return ChatOpenAI(
            model=GROQ_MODEL,
            api_key=GROQ_API_KEY,
            base_url=GROQ_BASE_URL,
            temperature=temperature,
            timeout=LLM_TIMEOUT_SECONDS,
            max_tokens=4096,
        )
    if LLM_PROVIDER == "ollama":
        raise LLMUnavailable("Ollama provider does not support required structured-output ChatOpenAI path")
    raise LLMUnavailable(f"unsupported LLM_PROVIDER={LLM_PROVIDER}")


def llm_generate(prompt: str, *, system: str | None = None, temperature: float = 0.1) -> str:
    if not ENABLE_LLM:
        raise LLMUnavailable("LLM disabled by ENABLE_LLM=0")
    if LLM_PROVIDER == "groq":
        return _groq_generate(prompt, system=system, temperature=temperature)
    if LLM_PROVIDER == "ollama":
        return _ollama_generate(prompt, system=system, temperature=temperature)
    raise LLMUnavailable(f"unsupported LLM_PROVIDER={LLM_PROVIDER}")


def ollama_generate(prompt: str, *, system: str | None = None, temperature: float = 0.1) -> str:
    """Backward-compatible alias used by existing agent code."""
    return llm_generate(prompt=prompt, system=system, temperature=temperature)


def _ollama_generate(prompt: str, *, system: str | None = None, temperature: float = 0.1) -> str:
    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system:
        payload["system"] = system

    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=LLM_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMUnavailable(f"Ollama HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMUnavailable(str(exc)) from exc
    return str(data.get("response") or "").strip()


def _groq_generate(prompt: str, *, system: str | None = None, temperature: float = 0.1) -> str:
    if not GROQ_API_KEY:
        raise LLMUnavailable("GROQ_API_KEY is not configured")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if requests is not None:
        try:
            response = requests.post(
                f"{GROQ_BASE_URL.rstrip('/')}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "SKN27-Jeonse-Diagnosis/1.0",
                },
                timeout=LLM_TIMEOUT_SECONDS,
            )
            if not response.ok:
                raise LLMUnavailable(f"Groq HTTP {response.status_code}: {response.text[:1000]}")
            data = response.json()
        except LLMUnavailable:
            raise
        except Exception as exc:
            raise LLMUnavailable(str(exc)) from exc
        return _groq_content(data)

    request = urllib.request.Request(
        f"{GROQ_BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SKN27-Jeonse-Diagnosis/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=LLM_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMUnavailable(f"Groq HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMUnavailable(str(exc)) from exc

    return _groq_content(data)


def _groq_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise LLMUnavailable("Groq returned no choices")
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def extract_json_object(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    candidate = fenced.group(1) if fenced else text
    if "{" in candidate and "}" in candidate:
        candidate = candidate[candidate.find("{"): candidate.rfind("}") + 1]
    return json.loads(candidate)


@tool
def ollama_generate_tool(prompt: str, system: str | None = None, temperature: float = 0.1) -> str:
    """Generate text with the configured LLM provider."""
    return llm_generate(prompt=prompt, system=system, temperature=temperature)
