# rag/jm/agent/tools.py
# LangGraph 에이전트가 호출하는 RAG 검색 도구 모음입니다.

from __future__ import annotations

from langchain_core.tools import tool

from ..retrieval.search import search


@tool
def search_documents(query: str, k: int = 5) -> str:
    """전세사기 방어/법률/정책/체크리스트 관련 문서를 검색합니다."""

    hits = search(query=query, k=k)
    if not hits:
        return "관련 문서를 찾지 못했습니다."

    context: list[str] = []
    for i, hit in enumerate(hits):
        context.append(f"[참고 문서 {i + 1}]\n{hit.content}")

    return "\n\n".join(context)
