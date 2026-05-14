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

    @property
    def PG_VECTOR_CONNECTION(self) -> str:
        """LangChain PGVector용 연결 문자열"""
        return self.DATABASE_URL

    # ── OpenAI (embedding 전용 — chat LLM은 Groq 사용) ───
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TEMPERATURE: float = 0.0
    EMBEDDING_TEMPERATURE: float = 0.0   # 임베딩에는 미사용, 호환용

    # ── Groq (chat LLM) ───────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_TEMPERATURE: float = 0.0
    LLM_PROVIDER: str = "groq"

    # ── pgvector (Vector DB — PostgreSQL 내장) ────
    PG_VECTOR_COLLECTION: str = "jeonse_docs"
    # text-embedding-3-large: OpenAI 최고 품질 임베딩, 3072 dim
    # text-embedding-3-small(1536dim) 에서 변경 → 재적재 필요:
    #   python rag/ingestion/embed_to_pg.py --reset
    EMBEDDING_MODEL: str = "text-embedding-3-large"

    # ── Neo4j (Graph DB) ──────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
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
        env_file=("../.env", ".env"),   # 프로젝트 루트 .env 우선, backend/.env 보조
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """싱글톤 설정 반환 (FastAPI Depends 주입용)"""
    return Settings()
