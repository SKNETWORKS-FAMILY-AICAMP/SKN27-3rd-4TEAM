from __future__ import annotations

from langchain_community.vectorstores import PGVector
import langchain_community.vectorstores.pgvector as pgvector
from langchain_openai import OpenAIEmbeddings

# PGVector 소멸자 버그 패치 (AttributeError: 'PGVector' object has no attribute '_bind' 해결)
original_del = pgvector.PGVector.__del__
def patched_del(self):
    try:
        original_del(self)
    except (AttributeError, TypeError):
        pass
pgvector.PGVector.__del__ = patched_del

from .config import load_config

# PG Vector 연결 문자열 생성
def _pg_connection_string() -> str:
    cfg = load_config()
    # DB_PASSWORD가 비어 있으면 인증에 실패합니다. .env에서 설정하세요.
    return (
        f"postgresql+psycopg2://{cfg.pg_user}:{cfg.pg_password}"
        f"@{cfg.pg_host}:{cfg.pg_port}/{cfg.pg_db}"
    )

# 벡터 스토어 생성
def get_vectorstore() -> PGVector:
    cfg = load_config()
    embeddings = OpenAIEmbeddings(model=cfg.embedding_model)
    # DB 준비: CREATE EXTENSION IF NOT EXISTS vector;
    return PGVector(
        collection_name=cfg.collection,
        connection_string=_pg_connection_string(),
        embedding_function=embeddings,
        use_jsonb=True,
    )

