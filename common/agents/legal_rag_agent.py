"""LLM-backed legal RAG agent."""
from __future__ import annotations

import json
from typing import Any

from common.schemas.legal_consultation_schema import LegalRagResult
from common.tools.legal_rag_tools import search_legal_rag
from common.tools.llm import LLMUnavailable, extract_json_object, llm_generate


def run_legal_rag_agent(user_question: str, question_type: str | None) -> LegalRagResult:
    rag_result = search_legal_rag(
        query=user_question,
        question_type=question_type,
        top_k=5,
        include_graph_context=True,
    )
    if rag_result["rag_status"] != "RAG_OK":
        return LegalRagResult(
            question_type=question_type or "GENERAL",
            rag_status=rag_result["rag_status"],
            confidence="LOW",
            evidence_refs=rag_result.get("references", []),
            llm_used=False,
            blocked_reason=f"RAG evidence not reliable enough: {rag_result['rag_status']}",
        )

    prompt = f"""
너는 부동산 임대차 법률 근거 검색 Agent다.
역할:
- 사용자 질문 유형에 맞는 법령/판례/공공기관 가이드를 검색한 결과만 사용한다.
- 검색된 근거만 사용해서 설명 초안을 만든다.
- 근거 없는 추측은 하지 않는다.
- 최종 상담 말투는 만들지 않는다.
- evidence_refs는 그대로 유지한다.

반환 JSON:
{{
  "confidence": "LOW|MEDIUM|HIGH",
  "legal_points": ["근거 기반 핵심 포인트"],
  "answer_draft": "근거 기반 초안"
}}

user_question:
{user_question}

question_type:
{question_type}

rag_result:
{json.dumps(rag_result, ensure_ascii=False, default=str)[:12000]}
""".strip()
    try:
        data = extract_json_object(
            llm_generate(
                prompt,
                system="너는 법률 근거 검색 agent다. JSON만 반환한다.",
                temperature=0.0,
            )
        )
    except Exception as exc:
        raise LLMUnavailable(f"legal rag agent failed: {exc}") from exc

    return LegalRagResult(
        question_type=question_type or "GENERAL",
        rag_status=rag_result["rag_status"],
        confidence=str(data.get("confidence") or "LOW"),
        legal_points=[str(item) for item in data.get("legal_points", [])],
        answer_draft=str(data.get("answer_draft") or ""),
        evidence_refs=rag_result.get("references", []),
        llm_used=True,
    )
