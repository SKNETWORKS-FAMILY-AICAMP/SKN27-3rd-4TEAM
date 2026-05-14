# rag/jm/legal/search.py
# PostgreSQL pgvector에서 법령, 판례, 표준계약서, 절차 문서를 범위별로 검색합니다.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from ..core.config import load_config
from ..core.index import get_embeddings


LEGAL_SEARCH_PATTERNS: dict[str, tuple[str, ...]] = {
    "all": (
        "%docs/pdf/law%",
        "%docs/pdf/judgement%",
        "%주택임대차표준계약서%",
    ),
    "law": (
        "%docs/pdf/law%",
    ),
    "judgement": (
        "%docs/pdf/judgement%",
    ),
    "standard_contract": (
        "%주택임대차표준계약서%",
        "%표준계약서%",
    ),
}


@dataclass(frozen=True)
class LegalSearchHit:
    """법률 전용 RAG 검색 결과 한 건을 담습니다."""

    content: str
    metadata: dict[str, Any]
    score: float


def _pg_connection_kwargs() -> dict[str, Any]:
    """환경 변수 기반 설정을 psycopg2 연결 인자로 변환합니다."""

    cfg = load_config()
    return {
        "host": cfg.pg_host,
        "port": cfg.pg_port,
        "dbname": cfg.pg_db,
        "user": cfg.pg_user,
        "password": cfg.pg_password,
    }


def _to_pgvector_literal(values: list[float]) -> str:
    """임베딩 숫자 배열을 pgvector가 읽을 수 있는 문자열로 변환합니다."""

    return "[" + ",".join(str(value) for value in values) + "]"


def _source_filter_sql(patterns: tuple[str, ...]) -> tuple[str, list[str]]:
    """source와 file_name 메타데이터에 적용할 SQL 필터와 파라미터를 만듭니다."""

    clauses: list[str] = []
    params: list[str] = []
    for pattern in patterns:
        clauses.append(
            "("
            "replace(e.cmetadata->>'source', '\\', '/') ILIKE %s "
            "OR e.cmetadata->>'file_name' ILIKE %s"
            ")"
        )
        params.extend([pattern, pattern])
    return " OR ".join(clauses), params


def search_legal_documents(
    query: str,
    k: int = 5,
    scope: str = "all",
) -> list[LegalSearchHit]:
    """법률 RAG 범위에 맞는 문서 chunk만 대상으로 유사도 검색을 수행합니다."""

    cfg = load_config()
    patterns = LEGAL_SEARCH_PATTERNS.get(scope)
    if patterns is None:
        valid_scopes = ", ".join(sorted(LEGAL_SEARCH_PATTERNS))
        raise ValueError(f"지원하지 않는 법률 검색 범위입니다: {scope}. 사용 가능: {valid_scopes}")

    embedding = get_embeddings().embed_query(query)
    vector_literal = _to_pgvector_literal(embedding)
    source_filter_sql, source_filter_params = _source_filter_sql(patterns)

    sql = f"""
        WITH query_vector AS (
            SELECT %s::vector AS embedding
        )
        SELECT
            e.document AS content,
            e.cmetadata AS metadata,
            1 - (e.embedding <=> query_vector.embedding) AS score
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON c.uuid = e.collection_id
        CROSS JOIN query_vector
        WHERE c.name = %s
          AND ({source_filter_sql})
        ORDER BY e.embedding <=> query_vector.embedding
        LIMIT %s
    """

    params = (
        vector_literal,
        cfg.collection,
        *source_filter_params,
        k,
    )

    with psycopg2.connect(**_pg_connection_kwargs()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        LegalSearchHit(
            content=row["content"],
            metadata=dict(row["metadata"] or {}),
            score=float(row["score"] or 0.0),
        )
        for row in rows
    ]
