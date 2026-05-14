# rag/jm/core/config.py
# RAG 실행에 필요한 환경변수 설정을 한 곳에서 관리합니다.

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RagConfig:
    collection: str
    embedding_provider: str
    embedding_model: str
    llm_provider: str
    llm_model: str
    ollama_base_url: str
    chunk_size: int
    chunk_overlap: int
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str


def load_config() -> RagConfig:
    return RagConfig(
        collection=os.getenv("RAG_COLLECTION", "jeonse-rag"),
        embedding_provider=os.getenv("RAG_EMBEDDING_PROVIDER", "openai").lower(),
        embedding_model=os.getenv(
            "RAG_EMBEDDING_MODEL",
            "text-embedding-3-small",
        ),
        llm_provider=os.getenv("RAG_LLM_PROVIDER", "openai").lower(),
        llm_model=os.getenv("RAG_LLM_MODEL", "gpt-4o-mini"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "900")),
        chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "150")),
        pg_host=os.getenv("DB_HOST", "localhost"),
        pg_port=int(os.getenv("DB_PORT", "5432")),
        pg_db=os.getenv("DB_NAME", "jeonse_risk"),
        pg_user=os.getenv("DB_USER", "postgres"),
        pg_password=os.getenv("DB_PASSWORD", ""),
    )
