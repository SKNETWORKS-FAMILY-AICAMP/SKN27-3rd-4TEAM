# rag/jm/core/index.py
# PostgreSQL(pgvector) 벡터스토어와 OpenAI 임베딩 모델을 생성합니다.

from __future__ import annotations

from langchain_community.vectorstores import PGVector
import langchain_community.vectorstores.pgvector as pgvector
from langchain_openai import OpenAIEmbeddings

from .config import load_config


_original_pgvector_del = pgvector.PGVector.__del__


def _patched_pgvector_del(self):
    """PGVector 객체 정리 중 발생하는 일부 버전 호환 오류를 무시합니다."""

    try:
        _original_pgvector_del(self)
    except (AttributeError, TypeError):
        pass


pgvector.PGVector.__del__ = _patched_pgvector_del


def _pg_connection_string() -> str:
    """LangChain PGVector용 PostgreSQL 연결 문자열을 생성합니다."""

    cfg = load_config()
    return (
        f"postgresql+psycopg2://{cfg.pg_user}:{cfg.pg_password}"
        f"@{cfg.pg_host}:{cfg.pg_port}/{cfg.pg_db}"
    )


def get_embeddings() -> OpenAIEmbeddings:
    """OpenAI 임베딩 모델을 생성합니다."""

    cfg = load_config()
    return OpenAIEmbeddings(model=cfg.embedding_model)


def get_vectorstore() -> PGVector:
    """OpenAI 임베딩을 사용하는 PGVector 벡터스토어를 생성합니다."""

    cfg = load_config()
    return PGVector(
        collection_name=cfg.collection,
        connection_string=_pg_connection_string(),
        embedding_function=get_embeddings(),
        use_jsonb=True,
    )
