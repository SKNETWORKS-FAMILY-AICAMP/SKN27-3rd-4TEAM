from __future__ import annotations

from typing import List, Optional
from langchain_core.tools import tool
from ..retrieval.search import search

@tool
def search_documents(query: str, k: int = 5) -> str:
    """전세사기 예방, 법률, 정책 등에 관한 문서 내용을 검색합니다. 
    질문과 관련된 구체적인 정보를 찾을 때 사용하세요."""
    hits = search(query=query, k=k)
    
    if not hits:
        return "관련된 문서를 찾지 못했습니다."
    
    context = []
    for i, h in enumerate(hits):
        context.append(f"[참고 문서 {i+1}]\n{h.content}")
        
    return "\n\n".join(context)
