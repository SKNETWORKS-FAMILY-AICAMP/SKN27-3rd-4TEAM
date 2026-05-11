"""
전세계약 위험 진단 에이전트 - RAG 파이프라인 오케스트레이터
VectorStore + GraphStore + LLM 통합 → 최종 답변/진단 생성
"""

from __future__ import annotations
import json
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage
from langsmith import traceable

from rag_server.config import Settings
from rag_server.core.vector_store import VectorStore
from rag_server.core.graph_store import GraphStore
from rag_server.core.llm import build_rag_chain, build_diagnosis_chain
from rag_server.models.schemas import RagReference, RiskFactor


class RAGPipeline:
    def __init__(self, settings: Settings, vector_store: VectorStore, graph_store: GraphStore):
        self._settings     = settings
        self._vector_store = vector_store
        self._graph_store  = graph_store
        self._rag_chain    = build_rag_chain(settings)
        self._diag_chain   = build_diagnosis_chain(settings)

    # ── 일반 RAG 채팅 ─────────────────────────────────────

    @traceable(name="rag_chat")
    async def chat(self, session_id: str, question: str, history: list[dict]) -> dict[str, Any]:
        raw_results  = self._vector_store.similarity_search(query=question, k=self._settings.RAG_TOP_K)
        context_text = self._format_context(raw_results)

        lc_history = [
            HumanMessage(content=m["content"]) if m["role"] == "user"
            else AIMessage(content=m["content"])
            for m in history
        ]

        response = await self._rag_chain.ainvoke({
            "context": context_text, "history": lc_history, "question": question,
        })
        return {
            "answer": response.content if hasattr(response, "content") else str(response),
            "references": self._build_references(raw_results),
        }

    # ── 계약서 진단 ───────────────────────────────────────

    @traceable(name="contract_diagnosis")
    async def diagnose(
        self, session_id: str, contract_text: str, contract_keywords: list[str],
    ) -> dict[str, Any]:
        search_query = f"전세계약 위험 {' '.join(contract_keywords[:5])}"
        raw_results  = self._vector_store.similarity_search(query=search_query, k=self._settings.RAG_TOP_K)

        graph_risks: list[dict] = []
        try:
            graph_risks = self._graph_store.get_risk_factors_by_keywords(contract_keywords)
        except Exception as e:
            print(f"[GraphStore] 조회 실패 (Neo4j 미연결?): {e}")
            graph_risks = self._get_fallback_risk_factors()

        response = await self._diag_chain.ainvoke({
            "context":       self._format_context(raw_results),
            "risk_factors":  json.dumps(graph_risks, ensure_ascii=False, indent=2),
            "contract_text": contract_text[:4000],
        })

        raw_answer = response.content if hasattr(response, "content") else str(response)
        parsed = self._parse_diagnosis_response(raw_answer, graph_risks)
        parsed["references"] = self._build_references(raw_results)
        return parsed

    # ── 내부 헬퍼 ─────────────────────────────────────────

    def _format_context(self, results: list[dict]) -> str:
        if not results:
            return "관련 문서를 찾지 못했습니다."
        parts = []
        for i, r in enumerate(results, 1):
            meta  = r.get("metadata", {})
            parts.append(
                f"[{i}] [{meta.get('doc_type','문서')}] {meta.get('title','제목없음')} "
                f"(유사도: {r.get('score', 0):.2f})\n{r['content']}"
            )
        return "\n\n---\n\n".join(parts)

    def _build_references(self, results: list[dict]) -> list[RagReference]:
        return [
            RagReference(
                doc_type=r.get("metadata", {}).get("doc_type", "문서"),
                title=r.get("metadata", {}).get("title", "제목없음"),
                chunk_text=r["content"][:300] + ("..." if len(r["content"]) > 300 else ""),
                relevance_score=r.get("score", 0.0),
            )
            for r in results
        ]

    def _parse_diagnosis_response(self, raw: str, graph_risks: list[dict]) -> dict[str, Any]:
        import re

        # JSON 추출 시도 (코드블록 → 중괄호 객체 순서로)
        json_str = None
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if m:
            json_str = m.group(1).strip()
        else:
            m = re.search(r"\{[\s\S]+\}", raw)
            if m:
                json_str = m.group(0).strip()

        if json_str:
            try:
                data = json.loads(json_str)
                risk_factors = [
                    RiskFactor(
                        factor_id=rf.get("factor_id", f"RF{i:03d}"),
                        category=rf.get("category", "기타"),
                        description=rf.get("description", ""),
                        severity=rf.get("severity", "MEDIUM"),
                        legal_basis=rf.get("legal_basis"),
                        advice=rf.get("advice", "전문가 상담 권고"),
                    )
                    for i, rf in enumerate(data.get("risk_factors", []), 1)
                ]
                # risk_factors가 비어있으면 graph_risks로 보완
                if not risk_factors and graph_risks:
                    risk_factors = self._risks_from_graph(graph_risks)

                return {
                    "risk_score": float(data.get("risk_score", 50)),
                    "risk_level": data.get("risk_level", "주의"),
                    "risk_factors": risk_factors,
                    "summary": data.get("summary", "진단을 완료했습니다."),
                }
            except Exception:
                pass

        return self._fallback_diagnosis(raw, graph_risks)

    def _risks_from_graph(self, graph_risks: list[dict]) -> list[RiskFactor]:
        return [
            RiskFactor(
                factor_id=r.get("factor_id", "RF000"),
                category=r.get("category", "기타"),
                description=r.get("description", ""),
                severity=r.get("severity", "MEDIUM"),
                legal_basis=(r.get("laws") or [None])[0],
                advice=r.get("advice", "전문가 상담 권고"),
            )
            for r in graph_risks[:10]
        ]

    def _fallback_diagnosis(self, summary: str, graph_risks: list[dict]) -> dict[str, Any]:
        # graph_risks가 비어있으면 기본 위험요소로 대체
        risks = graph_risks or self._get_fallback_risk_factors()
        risk_factors = self._risks_from_graph(risks)
        high = sum(1 for r in risks if r.get("severity") == "HIGH")
        med  = sum(1 for r in risks if r.get("severity") == "MEDIUM")
        score = min(100, high * 25 + med * 10)
        level = "위험" if score >= 80 else ("주의" if score >= 60 else "안전")

        # summary가 JSON 덩어리면 깔끔한 메시지로 대체
        clean_summary = summary.strip()
        if clean_summary.startswith("{") or clean_summary.startswith("```"):
            clean_summary = "계약서 분석을 완료했습니다. 상세 위험 요소를 확인하세요."

        return {
            "risk_score": float(score),
            "risk_level": level,
            "risk_factors": risk_factors,
            "summary": clean_summary[:1000],
        }

    def _get_fallback_risk_factors(self) -> list[dict]:
        return [
            {"factor_id": "RF001", "category": "전세가율",
             "description": "전세가율 80% 초과", "severity": "HIGH",
             "keywords": "전세가율 보증금", "advice": "시세 대비 전세금 비율 확인",
             "laws": ["주택임대차보호법 제3조의3"]},
            {"factor_id": "RF002", "category": "권리관계",
             "description": "근저당·가압류 과다", "severity": "HIGH",
             "keywords": "근저당 가압류", "advice": "등기부등본 열람 후 선순위 권리 확인",
             "laws": ["민법 제356조"]},
        ]
