# rag/jm/retrieval/generate.py
# 검색된 문서 조각을 바탕으로 최종 RAG 답변을 생성합니다.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..core.config import load_config
from .search import SearchHit, search


@dataclass
class GenerateResult:
    answer: str
    hits: List[SearchHit]


def _build_context(hits: List[SearchHit]) -> str:
    return "\n\n".join([f"[참고 문서 {i + 1}]\n{h.content}" for i, h in enumerate(hits)])


def _build_prompt(query: str, context: str) -> str:
    return (
        "당신은 전세사기 방어와 전세 계약 위험 분석을 돕는 전문가입니다.\n"
        "반드시 제공된 참고 문서를 근거로 답변하세요.\n"
        "참고 문서에서 확인할 수 없는 내용은 추측하지 말고, 추가 확인이 필요하다고 말하세요.\n\n"
        f"[참고 문서]\n{context}\n\n"
        f"[질문]\n{query}"
    )


def _generate_with_openai(query: str, context: str) -> str:
    cfg = load_config()
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 전세사기 방어와 전세 계약 위험 분석을 돕는 전문가입니다. "
                "제공된 참고 문서에 기반해 정확하고 간결하게 답변하세요.",
            ),
            ("human", "[참고 문서]\n{context}\n\n[질문]\n{query}"),
        ]
    )
    chain = prompt | ChatOpenAI(model=cfg.llm_model, temperature=0.0) | StrOutputParser()
    return chain.invoke({"context": context, "query": query})


def _generate_with_ollama(query: str, context: str) -> str:
    cfg = load_config()
    response = requests.post(
        f"{cfg.ollama_base_url.rstrip('/')}/api/generate",
        json={
            "model": cfg.llm_model,
            "prompt": _build_prompt(query, context),
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def generate_answer(
    query: str,
    k: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> GenerateResult:
    hits = search(query=query, k=k, where=where)
    context = _build_context(hits)
    cfg = load_config()

    if cfg.llm_provider == "ollama":
        answer = _generate_with_ollama(query, context)
    else:
        answer = _generate_with_openai(query, context)

    return GenerateResult(answer=answer, hits=hits)
