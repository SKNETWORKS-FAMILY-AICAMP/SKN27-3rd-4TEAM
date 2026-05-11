"""
전세계약 위험 진단 에이전트 - RAG 파이프라인 오케스트레이터
역할: VectorStore + GraphStore + LLM을 조합하여 최종 답변 생성

흐름:
  1. 사용자 쿼리 수신
  2. ChromaDB 시맨틱 검색 → 관련 법령/판례/사례 청크 Top-K
  3. Neo4j 그래프 검색 → 위험 요소 + 관계 정보
  4. 컨텍스트 조합 → LLM 프롬프트 구성
  5. LLM 호출 → 답변 생성 (LangSmith 자동 트레이싱)
  6. 결과 반환
"""

from __future__ import annotations
import json
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage
from langsmith import traceable

from app.config import Settings
from app.core.vector_store import VectorStore
from app.core.graph_store import GraphStore
from app.core.llm import build_rag_chain, build_diagnosis_chain
from app.models.schemas import RagReference, RiskFactor


class RAGPipeline:
    """
    RAG 오케스트레이터.
    FastAPI lifespan에서 app.state에 저장된 VectorStore / GraphStore를 주입받아 사용.
    """

    def __init__(self, settings: Settings, vector_store: VectorStore, graph_store: GraphStore):
        self._settings = settings
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._rag_chain = build_rag_chain(settings)
        self._diag_chain = build_diagnosis_chain(settings)

    # ══════════════════════════════════════════════════════
    # 1. 일반 RAG 채팅
    # ══════════════════════════════════════════════════════

    @traceable(name="rag_chat")
    async def chat(
        self,
        session_id: str,
        question: str,
        history: list[dict],
    ) -> dict[str, Any]:
        """
        일반 전세 관련 질문에 RAG 기반 답변 생성.

        Args:
            session_id: 세션 식별자 (LangSmith 메타데이터용)
            question: 사용자 질문
            history: [{"role": "user"|"assistant", "content": str}, ...]

        Returns:
            {"answer": str, "references": [RagReference, ...]}
        """

        # ── Step 1: 벡터 검색 ─────────────────────────────
        raw_results = self._vector_store.similarity_search(
            query=question,
            k=self._settings.RAG_TOP_K,
        )

        # ── Step 2: 컨텍스트 조합 ─────────────────────────
        context_text = self._format_context(raw_results)

        # ── Step 3: 대화 이력 변환 ────────────────────────
        lc_history = []
        for msg in history:
            if msg["role"] == "user":
                lc_history.append(HumanMessage(content=msg["content"]))
            else:
                lc_history.append(AIMessage(content=msg["content"]))

        # ── Step 4: LLM 호출 ──────────────────────────────
        response = await self._rag_chain.ainvoke({
            "context": context_text,
            "history": lc_history,
            "question": question,
        })

        answer = response.content if hasattr(response, "content") else str(response)

        # ── Step 5: 참조 문서 정리 ────────────────────────
        references = self._build_references(raw_results)

        return {"answer": answer, "references": references}

    # ══════════════════════════════════════════════════════
    # 2. 계약서 진단
    # ══════════════════════════════════════════════════════

    @traceable(name="contract_diagnosis")
    async def diagnose(
        self,
        session_id: str,
        contract_text: str,
        contract_keywords: list[str],
    ) -> dict[str, Any]:
        """
        전세계약서 텍스트를 분석하여 위험 진단 결과 반환.

        Args:
            session_id: 세션 식별자
            contract_text: 계약서 전문 텍스트
            contract_keywords: 계약서에서 추출한 핵심 키워드

        Returns:
            {
              "risk_score": float,
              "risk_level": str,
              "risk_factors": [RiskFactor, ...],
              "references": [RagReference, ...],
              "summary": str,
            }
        """

        # ── Step 1: 계약서 관련 문서 벡터 검색 ───────────
        search_query = f"전세계약 위험 {' '.join(contract_keywords[:5])}"
        raw_results = self._vector_store.similarity_search(
            query=search_query,
            k=self._settings.RAG_TOP_K,
        )

        # ── Step 2: 그래프 DB에서 위험 요소 조회 ─────────
        graph_risks: list[dict] = []
        try:
            graph_risks = self._graph_store.get_risk_factors_by_keywords(contract_keywords)
        except Exception as e:
            print(f"[GraphStore] 위험 요소 조회 실패 (Neo4j 미연결?): {e}")
            # Neo4j 없어도 동작하도록 폴백
            graph_risks = self._get_fallback_risk_factors()

        # ── Step 3: LLM 진단 호출 ─────────────────────────
        context_text = self._format_context(raw_results)
        risk_factors_text = json.dumps(graph_risks, ensure_ascii=False, indent=2)

        response = await self._diag_chain.ainvoke({
            "context": context_text,
            "risk_factors": risk_factors_text,
            "contract_text": contract_text[:4000],  # 토큰 제한
        })

        raw_answer = response.content if hasattr(response, "content") else str(response)

        # ── Step 4: LLM 응답 파싱 ─────────────────────────
        parsed = self._parse_diagnosis_response(raw_answer, graph_risks)

        parsed["references"] = self._build_references(raw_results)
        return parsed

    # ══════════════════════════════════════════════════════
    # 내부 헬퍼
    # ══════════════════════════════════════════════════════

    def _format_context(self, results: list[dict]) -> str:
        """검색 결과를 LLM 프롬프트용 텍스트로 변환"""
        if not results:
            return "관련 문서를 찾지 못했습니다."

        parts = []
        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            doc_type = meta.get("doc_type", "문서")
            title = meta.get("title", "제목 없음")
            score = r.get("score", 0)
            parts.append(
                f"[{i}] [{doc_type}] {title} (유사도: {score:.2f})\n{r['content']}"
            )
        return "\n\n---\n\n".join(parts)

    def _build_references(self, results: list[dict]) -> list[RagReference]:
        """검색 결과를 RagReference 리스트로 변환"""
        refs = []
        for r in results:
            meta = r.get("metadata", {})
            refs.append(RagReference(
                doc_type=meta.get("doc_type", "문서"),
                title=meta.get("title", "제목 없음"),
                chunk_text=r["content"][:300] + "..." if len(r["content"]) > 300 else r["content"],
                relevance_score=r.get("score", 0.0),
            ))
        return refs

    def _parse_diagnosis_response(
        self, raw: str, graph_risks: list[dict]
    ) -> dict[str, Any]:
        """
        LLM 진단 응답을 파싱하여 구조화된 결과 반환.
        JSON 파싱 실패 시 그래프 DB 결과 기반으로 폴백.
        """
        # JSON 블록 추출 시도
        try:
            import re
            json_match = re.search(r"```json\s*([\s\S]+?)\s*```", raw)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(raw)

            return {
                "risk_score": float(data.get("risk_score", 50)),
                "risk_level": data.get("risk_level", "주의"),
                "risk_factors": [
                    RiskFactor(
                        factor_id=rf.get("factor_id", f"RF{i:03d}"),
                        category=rf.get("category", "기타"),
                        description=rf.get("description", ""),
                        severity=rf.get("severity", "MEDIUM"),
                        legal_basis=rf.get("legal_basis"),
                        advice=rf.get("advice", "전문가 상담 권고"),
                    )
                    for i, rf in enumerate(data.get("risk_factors", []), 1)
                ],
                "summary": data.get("summary", raw[:500]),
            }

        except (json.JSONDecodeError, KeyError, TypeError):
            # 폴백: 그래프 DB 위험 요소 기반으로 기본 진단
            return self._fallback_diagnosis(raw, graph_risks)

    def _fallback_diagnosis(self, summary: str, graph_risks: list[dict]) -> dict[str, Any]:
        """LLM JSON 파싱 실패 시 그래프 DB 결과 기반 폴백"""
        risk_factors = []
        high_count = 0
        medium_count = 0

        for rf in graph_risks[:10]:
            severity = rf.get("severity", "MEDIUM")
            if severity == "HIGH":
                high_count += 1
            elif severity == "MEDIUM":
                medium_count += 1

            laws = rf.get("laws", [])
            risk_factors.append(RiskFactor(
                factor_id=rf.get("factor_id", "RF000"),
                category=rf.get("category", "기타"),
                description=rf.get("description", ""),
                severity=severity,
                legal_basis=laws[0] if laws else None,
                advice=rf.get("advice", "전문가 상담 권고"),
            ))

        risk_score = min(100, high_count * 25 + medium_count * 10)
        if risk_score >= 80:
            risk_level = "위험"
        elif risk_score >= 60:
            risk_level = "주의"
        else:
            risk_level = "안전"

        return {
            "risk_score": float(risk_score),
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "summary": summary[:1000] if summary else "진단을 완료했습니다.",
        }

    def _get_fallback_risk_factors(self) -> list[dict]:
        """Neo4j 미연결 시 기본 위험 요소 목록 반환"""
        return [
            {
                "factor_id": "RF001", "category": "전세가율",
                "description": "전세가율 80% 초과", "severity": "HIGH",
                "keywords": "전세가율 보증금",
                "advice": "시세 대비 전세금 비율 확인", "laws": ["주택임대차보호법 제3조의3"],
            },
            {
                "factor_id": "RF002", "category": "권리관계",
                "description": "근저당·가압류 과다", "severity": "HIGH",
                "keywords": "근저당 가압류",
                "advice": "등기부등본 열람 후 선순위 권리 확인", "laws": ["민법 제356조"],
            },
            {
                "factor_id": "RF005", "category": "절차",
                "description": "임대인 신원 미확인", "severity": "HIGH",
                "keywords": "임대인 소유자",
                "advice": "신분증·등기권리증 대조 필수", "laws": ["공인중개사법 제25조"],
            },
        ]
