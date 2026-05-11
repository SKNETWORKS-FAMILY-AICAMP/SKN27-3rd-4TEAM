"""
전세계약 위험 진단 에이전트 - ChromaDB 벡터 스토어
역할: 문서 임베딩 저장 + 시맨틱 유사도 검색
"""

from __future__ import annotations
import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

from app.config import Settings


class VectorStore:
    """
    ChromaDB 기반 벡터 스토어 래퍼.

    - 문서 청크를 임베딩하여 저장
    - 쿼리 텍스트와 가장 유사한 청크를 Top-K 반환
    """

    def __init__(self, settings: Settings):
        self._settings = settings

        # OpenAI 임베딩 모델
        self._embeddings = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
        )

        # ChromaDB HTTP 클라이언트 (Docker 서비스)
        self._client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # LangChain Chroma 래퍼 (검색 편의를 위해)
        self._store = Chroma(
            client=self._client,
            collection_name=settings.CHROMA_COLLECTION,
            embedding_function=self._embeddings,
        )

    # ── 검색 ──────────────────────────────────────────────

    def similarity_search(
        self,
        query: str,
        k: int | None = None,
        filter_doc_type: str | None = None,
    ) -> list[dict]:
        """
        쿼리와 유사한 문서 청크 반환.

        Args:
            query: 검색 텍스트
            k: 반환 개수 (None → settings.RAG_TOP_K)
            filter_doc_type: '판례' / '법령' / '사례집' / '서식' 필터

        Returns:
            [{"content": str, "metadata": dict, "score": float}, ...]
        """
        k = k or self._settings.RAG_TOP_K
        where = {"doc_type": filter_doc_type} if filter_doc_type else None

        results = self._store.similarity_search_with_relevance_scores(
            query=query,
            k=k,
            filter=where,
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
        """
        텍스트 청크 + 메타데이터를 임베딩하여 저장.

        Returns:
            저장된 document IDs
        """
        ids = self._store.add_texts(texts=texts, metadatas=metadatas)
        return ids

    def delete_collection(self) -> None:
        """컬렉션 전체 삭제 (재적재 시 사용)"""
        self._client.delete_collection(self._settings.CHROMA_COLLECTION)

    # ── 컬렉션 정보 ───────────────────────────────────────

    def count(self) -> int:
        """저장된 문서 수 반환"""
        try:
            col = self._client.get_collection(self._settings.CHROMA_COLLECTION)
            return col.count()
        except Exception:
            return 0

    def is_ready(self) -> bool:
        """ChromaDB 연결 상태 확인"""
        try:
            self._client.heartbeat()
            return True
        except Exception:
            return False
