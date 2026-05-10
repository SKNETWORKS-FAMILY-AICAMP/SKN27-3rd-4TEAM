from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .index import get_vectorstore

# 검색 결과 구조
@dataclass(frozen=True)
class SearchHit:
    content: str
    metadata: Dict[str, Any]
    score: float

# 검색
def search(query: str, k: int = 5, where: Optional[Dict[str, Any]] = None) -> List[SearchHit]:
    vs = get_vectorstore()
    results = vs.similarity_search_with_relevance_scores(query, k=k, filter=where)
    hits: List[SearchHit] = []
    for doc, score in results:
        hits.append(SearchHit(content=doc.page_content, metadata=dict(doc.metadata or {}), score=float(score)))
    return hits
