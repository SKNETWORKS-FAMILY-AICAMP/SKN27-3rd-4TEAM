"""External legal source search boundary.

Network access is intentionally optional.  In offline/local runs this returns
an empty result set while preserving the tool contract expected by agents.
"""
from __future__ import annotations

from typing import Any

try:
    from langchain_core.tools import tool
except ImportError:  # pragma: no cover
    def tool(func):
        return func


def search_external_sources(query: str, question_type: str | None = None) -> list[dict[str, Any]]:
    """Return external source snippets for a legal question.

    A real web/API integration can replace this body later.  The graph treats an
    empty list as "no external source available" and continues with internal RAG.
    """
    return []


@tool
def search_external_sources_tool(query: str, question_type: str | None = None) -> list[dict[str, Any]]:
    """Search public external legal sources for a Korean jeonse question."""
    return search_external_sources(query, question_type)
