# rag/jm/retrieval/search.py
# PGVector에서 질문과 유사한 문서 chunk를 검색합니다.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..core.index import get_vectorstore


@dataclass(frozen=True)
class SearchHit:
    content: str
    metadata: Dict[str, Any]
    score: float


def search(query: str, k: int = 5, where: Optional[Dict[str, Any]] = None) -> List[SearchHit]:
    vs = get_vectorstore()
    results = vs.similarity_search_with_relevance_scores(query, k=k, filter=where)
    return [
        SearchHit(content=doc.page_content, metadata=dict(doc.metadata or {}), score=float(score))
        for doc, score in results
    ]
