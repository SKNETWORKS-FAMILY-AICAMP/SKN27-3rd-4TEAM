"""
전세계약 위험 진단 에이전트 - pgvector 기반 벡터 스토어
임베딩: OpenAI text-embedding-3-large (3072 dim, 한국어 포함 다국어 고품질)
"""

from __future__ import annotations
import psycopg2
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from app.config import Settings


class VectorStore:
    """pgvector 기반 벡터 스토어 래퍼.

    - 문서 청크를 text-embedding-3-large 임베딩으로 저장
    - 쿼리 텍스트와 코사인 유사도 기반 Top-K 반환
    """

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

    # ── 검색 ──────────────────────────────────────────────

    def similarity_search(
        self,
        query: str,
        k: int | None = None,
        filter_doc_type: str | None = None,
    ) -> list[dict]:
        """쿼리와 유사한 문서 청크 반환.

        Args:
            query: 검색 텍스트
            k: 반환 개수 (None → settings.RAG_TOP_K)
            filter_doc_type: '판례' / '법령' / '사례집' / '서식' 필터

        Returns:
            [{"content": str, "metadata": dict, "score": float}, ...]
        """
        k = k or self._settings.RAG_TOP_K
        filter_dict = {"doc_type": filter_doc_type} if filter_doc_type else None

        results = self._store.similarity_search_with_relevance_scores(
            query=query,
            k=k,
            filter=filter_dict,
        )

        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": float(score),
            }
            for doc, score in results
        ]

    # ── 적재 ──────────────────────────────────────────────

    def add_documents(self, texts: list[str], metadatas: list[dict]) -> list[str]:
        """텍스트 청크 + 메타데이터를 임베딩하여 저장."""
        return self._store.add_texts(texts=texts, metadatas=metadatas)

    def delete_collection(self) -> None:
        """컬렉션 전체 삭제 (재적재 시 사용)"""
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
                "DELETE FROM langchain_pg_embedding WHERE collection_id = "
                "(SELECT uuid FROM langchain_pg_collection WHERE name = %s)",
                (self._settings.PG_VECTOR_COLLECTION,),
            )
            cur.execute(
                "DELETE FROM langchain_pg_collection WHERE name = %s",
                (self._settings.PG_VECTOR_COLLECTION,),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[VectorStore] 컬렉션 삭제 실패: {e}")

    # ── 컬렉션 정보 ───────────────────────────────────────

    def count(self) -> int:
        """저장된 문서 수 반환"""
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
        """pgvector 확장 설치 여부로 연결 상태 확인"""
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
