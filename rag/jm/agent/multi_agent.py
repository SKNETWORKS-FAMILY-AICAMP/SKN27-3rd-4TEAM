# rag/jm/agent/multi_agent.py
# DB 분석, RAG 문서 검색, 위험도 설명을 역할별 에이전트로 분리합니다.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import psycopg2
import requests
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..core.config import load_config
from ..retrieval.search import SearchHit, search

# DB 분석 에이전트
@dataclass(frozen=True)
class DbAnalysisResult:
    summary: str
    metrics: Dict[str, Any]

# 문서 검색 에이전트
@dataclass(frozen=True)
class RagAgentResult:
    summary: str
    hits: List[SearchHit]

# 결과 취합
@dataclass(frozen=True)
class MultiAgentResult:
    answer: str
    db_analysis: DbAnalysisResult
    rag_analysis: RagAgentResult


def _connect_db():
    cfg = load_config()
    return psycopg2.connect(
        host=cfg.pg_host,
        port=cfg.pg_port,
        dbname=cfg.pg_db,
        user=cfg.pg_user,
        password=cfg.pg_password,
    )

# DB 분석
def db_analysis_agent(query: str) -> DbAnalysisResult:
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
    hits = search(query=query, k=k)
    if not hits:
        return RagAgentResult(summary="질문과 관련된 RAG 문서를 찾지 못했습니다.", hits=[])

    sources = []
    for hit in hits:
        metadata = hit.metadata
        file_name = metadata.get("file_name") or metadata.get("source") or "unknown"
        page = metadata.get("page_label") or metadata.get("page")
        sources.append(f"{file_name} p.{page}" if page is not None else file_name)

    summary = "관련 문서 근거: " + "; ".join(sources[:k])
    return RagAgentResult(summary=summary, hits=hits)


def _format_hits(hits: List[SearchHit]) -> str:
    return "\n\n".join([f"[문서 {i + 1}]\n{hit.content}" for i, hit in enumerate(hits)])

# OpenAI 모델을 사용한 답변 생성
def _generate_with_openai(query: str, db_result: DbAnalysisResult, rag_result: RagAgentResult) -> str:
    cfg = load_config()
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 전세사기 위험 분석을 돕는 설명 에이전트입니다. "
                "DB 분석 결과와 RAG 문서 근거를 함께 사용해 답변하세요.",
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

# Ollama 모델
def _generate_with_ollama(query: str, db_result: DbAnalysisResult, rag_result: RagAgentResult) -> str:
    cfg = load_config()
    prompt = (
        "당신은 전세사기 위험 분석을 돕는 설명 에이전트입니다.\n"
        "DB 분석 결과와 RAG 문서 근거를 함께 사용해 답변하세요.\n\n"
        f"[질문]\n{query}\n\n"
        f"[DB 분석]\n{db_result.summary}\n{db_result.metrics}\n\n"
        f"[RAG 근거]\n{rag_result.summary}\n{_format_hits(rag_result.hits)}"
    )
    response = requests.post(
        f"{cfg.ollama_base_url.rstrip('/')}/api/generate",
        json={"model": cfg.llm_model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()

# 설명 에이전트
def risk_explanation_agent(query: str, db_result: DbAnalysisResult, rag_result: RagAgentResult) -> str:
    cfg = load_config()
    if cfg.llm_provider == "ollama":
        return _generate_with_ollama(query, db_result, rag_result)
    return _generate_with_openai(query, db_result, rag_result)

# 멀티 에이전트 실행
def run_multi_agent(query: str, k: int = 5) -> MultiAgentResult:
    db_result = db_analysis_agent(query)
    rag_result = rag_document_agent(query, k=k)
    answer = risk_explanation_agent(query, db_result, rag_result)
    return MultiAgentResult(answer=answer, db_analysis=db_result, rag_analysis=rag_result)
