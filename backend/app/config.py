"""
전세계약 위험 진단 에이전트 - 설정 관리
환경변수를 읽어 앱 전체에서 공유하는 Settings 싱글톤
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── FastAPI ───────────────────────────────────
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8001

    # ── PostgreSQL ────────────────────────────────
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "jeonse_risk"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "risk1234"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # ── OpenAI ────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TEMPERATURE: float = 0.0

    # ── pgvector (Vector DB — PostgreSQL 내장) ────
    PG_VECTOR_COLLECTION: str = "jeonse_docs"
    # text-embedding-3-large: OpenAI 최고 품질 임베딩, 3072 dim
    EMBEDDING_MODEL: str = "text-embedding-3-large"

    @property
    def PG_VECTOR_CONNECTION(self) -> str:
        """LangChain PGVector용 연결 문자열"""
        return self.DATABASE_URL

    # ── Neo4j (Graph DB) ──────────────────────────
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "jeonse1234"

    # ── LangSmith ────────────────────────────────
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "jeonse-rag"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    # ── RAG 파라미터 ──────────────────────────────
    RAG_TOP_K: int = 4
    RAG_SCORE_THRESHOLD: float = 0.25  # 유사도 임계값 (이하 문서 제외)
    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 80

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """싱글톤 설정 반환 (FastAPI Depends 주입용)"""
    return Settings()
