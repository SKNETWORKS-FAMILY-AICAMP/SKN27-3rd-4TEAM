# rag/jm/core/index.py
# PostgreSQL(pgvector) 벡터 스토어와 임베딩 모델을 생성합니다.

from __future__ import annotations

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
import langchain_community.vectorstores.pgvector as pgvector
from langchain_openai import OpenAIEmbeddings

from .config import load_config


_original_pgvector_del = pgvector.PGVector.__del__


def _patched_pgvector_del(self):
    try:
        _original_pgvector_del(self)
    except (AttributeError, TypeError):
        pass


pgvector.PGVector.__del__ = _patched_pgvector_del


def _pg_connection_string() -> str:
    cfg = load_config()
    return (
        f"postgresql+psycopg2://{cfg.pg_user}:{cfg.pg_password}"
        f"@{cfg.pg_host}:{cfg.pg_port}/{cfg.pg_db}"
    )


def get_embeddings():
    cfg = load_config()
    if cfg.embedding_provider == "openai":
        return OpenAIEmbeddings(model=cfg.embedding_model)

    return HuggingFaceEmbeddings(
        model_name=cfg.embedding_model,
        encode_kwargs={"normalize_embeddings": True},
    )


def get_vectorstore() -> PGVector:
    cfg = load_config()
    return PGVector(
        collection_name=cfg.collection,
        connection_string=_pg_connection_string(),
        embedding_function=get_embeddings(),
        use_jsonb=True,
    )
