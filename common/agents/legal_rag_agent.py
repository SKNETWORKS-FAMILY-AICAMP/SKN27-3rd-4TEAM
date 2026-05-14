"""LLM-backed legal RAG agent."""
from __future__ import annotations

import json
from typing import Any

from common.schemas.legal_consultation_schema import LegalRagResult
from common.schemas.shared import Claim
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
        evidence = rag_result.get("results") or rag_result.get("references", [])
        return LegalRagResult(
            question_type=question_type or "GENERAL",
            rag_status=rag_result["rag_status"],
            confidence="LOW",
            evidence_refs=evidence,
            graph_context=rag_result.get("graph_context", []),
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
  "claims": [
    {{
      "text": "검증 가능한 법률 주장",
      "evidence_ids": ["doc_id"],
      "graph_context_ids": ["node|relation|target"]
    }}
  ],
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

    evidence = rag_result.get("results") or rag_result.get("references", [])
    graph_context = rag_result.get("graph_context", [])
    claims = _normalize_claims(data.get("claims", []), evidence, graph_context, question_type or "GENERAL")
    return LegalRagResult(
        question_type=question_type or "GENERAL",
        rag_status=rag_result["rag_status"],
        confidence=str(data.get("confidence") or "LOW"),
        claims=claims,
        legal_points=[str(item) for item in data.get("legal_points", [])],
        answer_draft=str(data.get("answer_draft") or ""),
        evidence_refs=evidence,
        graph_context=graph_context,
        llm_used=True,
    )


def _normalize_claims(raw_claims: Any, evidence_refs: list[dict[str, Any]], graph_context: list[dict[str, Any]], task: str) -> list[dict[str, Any]]:
    evidence_ids = [str(item.get("doc_id") or item.get("source_id")) for item in evidence_refs[:5] if item.get("doc_id") or item.get("source_id")]
    graph_ids = [f"{item.get('node')}|{item.get('relation')}|{item.get('target')}" for item in graph_context[:5]]
    claims: list[dict[str, Any]] = []
    if isinstance(raw_claims, list):
        for index, item in enumerate(raw_claims, 1):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            claims.append(
                {
                    "claim_id": str(item.get("claim_id") or f"legal_rag_claim_{index}"),
                    "task": task,
                    "text": text,
                    "evidence_ids": item.get("evidence_ids") or evidence_ids,
                    "graph_context_ids": item.get("graph_context_ids") or graph_ids,
                    "confidence": str(item.get("confidence") or "MEDIUM"),
                }
            )
    if not claims:
        claims.append(
            {
                "claim_id": "legal_rag_claim_1",
                "task": task,
                "text": "검색된 근거에 기반해 법률 설명 초안을 작성했습니다.",
                "evidence_ids": evidence_ids,
                "graph_context_ids": graph_ids,
                "confidence": "MEDIUM" if evidence_ids else "LOW",
            }
        )
    return claims
