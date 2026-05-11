"""
전세계약 위험 진단 에이전트 - pgvector 기반 벡터 스토어
langchain_postgres.PGVector 사용 (langchain-postgres==0.0.16)
"""

from __future__ import annotations
import psycopg2
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from rag_server.config import Settings


class VectorStore:
    def __init__(self, settings: Settings):
        self._settings = settings

        self._embeddings = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
        )

        self._store = PGVector(
            collection_name=settings.PG_VECTOR_COLLECTION,
            connection=settings.PG_VECTOR_CONNECTION,
            embeddings=self._embeddings,
            use_jsonb=True,
            pre_delete_collection=False,
        )

    def similarity_search(
        self,
        query: str,
        k: int | None = None,
        filter_doc_type: str | None = None,
    ) -> list[dict]:
        k = k or self._settings.RAG_TOP_K
        filter_dict = {"doc_type": filter_doc_type} if filter_doc_type else None

        results = self._store.similarity_search_with_relevance_scores(
            query=query,
            k=k,
            filter=filter_dict,
        )
        return [
            {"content": doc.page_content, "metadata": doc.metadata, "score": float(score)}
            for doc, score in results
        ]

    def add_documents(self, texts: list[str], metadatas: list[dict]) -> list[str]:
        return self._store.add_texts(texts=texts, metadatas=metadatas)

    def count(self) -> int:
        try:
            conn = psycopg2.connect(
                host=self._settings.DB_HOST,
                port=self._settings.DB_PORT,
                database=self._settings.DB_NAME,
                user=self._settings.DB_USER,
                password=self._settings.DB_PASSWORD,
            )
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM langchain_pg_embedding WHERE collection_id = "
                "(SELECT uuid FROM langchain_pg_collection WHERE name = %s)",
                (self._settings.PG_VECTOR_COLLECTION,),
            )
            result = cur.fetchone()
            cur.close()
            conn.close()
            return result[0] if result else 0
        except Exception:
            return 0

    def is_ready(self) -> bool:
        try:
            conn = psycopg2.connect(
                host=self._settings.DB_HOST,
                port=self._settings.DB_PORT,
                database=self._settings.DB_NAME,
                user=self._settings.DB_USER,
                password=self._settings.DB_PASSWORD,
            )
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ok = cur.fetchone() is not None
            cur.close()
            conn.close()
            return ok
        except Exception:
            return False
