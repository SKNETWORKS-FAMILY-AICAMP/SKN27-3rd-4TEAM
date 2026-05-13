# rag/jm/core/config.py
# OpenAI 기반 RAG 실행에 필요한 환경변수 설정을 한 곳에서 관리합니다.

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RagConfig:
    """RAG 구성값(환경변수 기반) 묶음입니다."""

    collection: str
    embedding_model: str
    llm_model: str
    chunk_size: int
    chunk_overlap: int
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str


def load_config() -> RagConfig:
    """환경변수에서 OpenAI RAG 설정을 로드합니다."""

    return RagConfig(
        collection=os.getenv("RAG_COLLECTION", os.getenv("PG_VECTOR_COLLECTION", "jeonse_docs")),
        embedding_model=os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small"),
        llm_model=os.getenv("RAG_LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
        chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "900")),
        chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "150")),
        pg_host=os.getenv("DB_HOST", "localhost"),
        pg_port=int(os.getenv("DB_PORT", "5432")),
        pg_db=os.getenv("DB_NAME", "jeonse_risk"),
        pg_user=os.getenv("DB_USER", "postgres"),
        pg_password=os.getenv("DB_PASSWORD", "risk1234"),
    )
