import os
from dataclasses import dataclass

# RAG 설정
@dataclass(frozen=True)
class RagConfig:
    collection: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str

# 환경변수 로드
def load_config() -> RagConfig:
    return RagConfig(
        collection=os.getenv("RAG_COLLECTION", "jeonse-rag"),
        embedding_model=os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small"),
        chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "900")),
        chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "150")),
        pg_host=os.getenv("DB_HOST", "localhost"),
        pg_port=int(os.getenv("DB_PORT", "5432")),
        pg_db=os.getenv("DB_NAME", "jeonse_risk"),
        pg_user=os.getenv("DB_USER", "postgres"),
        pg_password=os.getenv("DB_PASSWORD", ""),
    )
