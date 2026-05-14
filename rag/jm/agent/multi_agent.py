# rag/jm/agent/multi_agent.py
# DB 분석 + RAG 문서 검색 결과를 결합해서 최종 답변을 생성하는 멀티 에이전트 로직입니다.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import psycopg2
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..core.config import load_config
from ..retrieval.search import SearchHit, search


@dataclass(frozen=True)
class DbAnalysisResult:
    """DB 분석 에이전트가 만든 요약/지표 결과입니다."""

    summary: str
    metrics: Dict[str, Any]


@dataclass(frozen=True)
class RagAgentResult:
    """RAG 문서 에이전트가 찾은 근거(검색 결과)와 요약입니다."""

    summary: str
    hits: List[SearchHit]


@dataclass(frozen=True)
class MultiAgentResult:
    """멀티 에이전트 전체 실행 결과입니다."""

    answer: str
    db_analysis: DbAnalysisResult
    rag_analysis: RagAgentResult


def _connect_db():
    """환경 설정값을 기반으로 PostgreSQL 연결을 생성합니다."""

    cfg = load_config()
    return psycopg2.connect(
        host=cfg.pg_host,
        port=cfg.pg_port,
        dbname=cfg.pg_db,
        user=cfg.pg_user,
        password=cfg.pg_password,
    )


def db_analysis_agent(query: str) -> DbAnalysisResult:
    """DB에서 기초 통계(건수/상위 위험 구간 등)를 조회해 요약합니다."""

    _ = query  # 현재는 쿼리와 무관하게 기본 통계만 계산합니다.

    with _connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM jeonse_transactions")
            jeonse_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM sale_transactions")
            sale_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM price_ratio")
            ratio_count = cur.fetchone()[0]

            cur.execute(
                """
                SELECT dong_name, housing_type, area_range, jeonse_ratio, risk_level
                FROM price_ratio
                WHERE jeonse_ratio IS NOT NULL
                ORDER BY jeonse_ratio DESC
                LIMIT 5
                """
            )
            top_risks = cur.fetchall()

    metrics = {
        "jeonse_count": jeonse_count,
        "sale_count": sale_count,
        "ratio_count": ratio_count,
        "top_risks": [
            {
                "dong_name": row[0],
                "housing_type": row[1],
                "area_range": row[2],
                "jeonse_ratio": float(row[3]) if row[3] is not None else None,
                "risk_level": row[4],
            }
            for row in top_risks
        ],
    }

    summary = (
        f"전세 거래 {jeonse_count:,}건, 매매 거래 {sale_count:,}건, "
        f"전세가율 분석 구간 {ratio_count:,}건이 DB에 있습니다."
    )
    return DbAnalysisResult(summary=summary, metrics=metrics)


def rag_document_agent(query: str, k: int = 5) -> RagAgentResult:
    """질문과 관련된 RAG 문서 청크를 검색하고, 출처 요약을 만듭니다."""

    hits = search(query=query, k=k)
    if not hits:
        return RagAgentResult(summary="질문과 관련된 RAG 문서를 찾지 못했습니다.", hits=[])

    sources: list[str] = []
    for hit in hits:
        metadata = hit.metadata
        file_name = metadata.get("file_name") or metadata.get("source") or "unknown"
        page = metadata.get("page_label") or metadata.get("page")
        sources.append(f"{file_name} p.{page}" if page is not None else file_name)

    summary = "관련 문서 근거: " + "; ".join(sources[:k])
    return RagAgentResult(summary=summary, hits=hits)


def _format_hits(hits: List[SearchHit]) -> str:
    """LLM 프롬프트에 넣기 좋은 형태로 검색 결과를 포맷합니다."""

    return "\n\n".join([f"[문서 {i + 1}]\n{hit.content}" for i, hit in enumerate(hits)])


def _generate_with_openai(query: str, db_result: DbAnalysisResult, rag_result: RagAgentResult) -> str:
    """OpenAI 모델로 DB 분석 + RAG 근거를 결합해 최종 답변을 생성합니다."""

    cfg = load_config()
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "너는 전세사기 위험을 설명하는 전문가 에이전트야. "
                "DB 분석 결과와 RAG 문서 근거를 함께 사용해서 답해줘.",
            ),
            (
                "human",
                "[질문]\n{query}\n\n[DB 분석]\n{db_summary}\n{db_metrics}\n\n[RAG 근거]\n{rag_summary}\n{rag_context}",
            ),
        ]
    )
    chain = prompt | ChatOpenAI(model=cfg.llm_model, temperature=0.0) | StrOutputParser()
    return chain.invoke(
        {
            "query": query,
            "db_summary": db_result.summary,
            "db_metrics": db_result.metrics,
            "rag_summary": rag_result.summary,
            "rag_context": _format_hits(rag_result.hits),
        }
    )


def risk_explanation_agent(query: str, db_result: DbAnalysisResult, rag_result: RagAgentResult) -> str:
    """OpenAI 모델로 최종 답변 생성 에이전트를 실행합니다."""

    return _generate_with_openai(query, db_result, rag_result)


def run_multi_agent(query: str, k: int = 5) -> MultiAgentResult:
    """DB 분석 → RAG 검색 → 최종 답변 생성을 순차적으로 실행합니다."""

    db_result = db_analysis_agent(query)
    rag_result = rag_document_agent(query, k=k)
    answer = risk_explanation_agent(query, db_result, rag_result)
    return MultiAgentResult(answer=answer, db_analysis=db_result, rag_analysis=rag_result)
