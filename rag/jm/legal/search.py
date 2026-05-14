# rag/jm/legal/search.py
# PostgreSQL pgvector에 적재된 문서 중 law 폴더의 법률 문서만 검색합니다.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from ..core.config import load_config
from ..core.index import get_embeddings


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
    """임베딩 숫자 배열을 pgvector가 읽을 수 있는 문자열로 바꿉니다."""

    return "[" + ",".join(str(value) for value in values) + "]"


def search_legal_documents(query: str, k: int = 5) -> list[LegalSearchHit]:
    """law 폴더에서 적재된 법률 chunk만 대상으로 유사도 검색을 수행합니다."""

    cfg = load_config()
    embedding = get_embeddings().embed_query(query)
    vector_literal = _to_pgvector_literal(embedding)

    sql = """
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
          AND replace(e.cmetadata->>'source', '\\', '/') ILIKE %s
        ORDER BY e.embedding <=> query_vector.embedding
        LIMIT %s
    """

    params = (
        vector_literal,
        cfg.collection,
        "%docs/pdf/law%",
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
