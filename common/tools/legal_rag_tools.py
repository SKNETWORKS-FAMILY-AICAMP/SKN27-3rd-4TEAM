"""Legal consultation RAG tools."""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from common.tools.adaptive_rag import adaptive_rag

QUESTION_TYPE_RAG_MAP: dict[str, dict[str, list[str]]] = {
    "DEPOSIT_RETURN": {
        "tables": ["law_documents", "case_documents", "procedure_guides", "public_guides"],
        "domain": ["deposit_return", "tenant_protection", "procedure"],
    },
    "REGISTRY_RISK": {
        "tables": ["registry_guides", "law_documents", "case_documents", "public_guides"],
        "domain": ["registry", "senior_debt", "trust_registration"],
    },
    "DEPOSIT_INSURANCE": {
        "tables": ["insurance_guides", "public_guides", "law_documents"],
        "domain": ["insurance", "HUG", "HF", "SGI"],
    },
    "PROCEDURE_GUIDE": {
        "tables": ["procedure_guides", "public_guides", "law_documents"],
        "domain": ["content_certification", "lease_registration_order", "payment_order"],
    },
    "SIMPLE_EXPLANATION": {
        "tables": ["faq_documents", "public_guides"],
        "domain": ["lease_basic", "tenant_protection"],
    },
}

DEFAULT_RAG_CONFIG = {
    "tables": ["law_documents", "case_documents", "public_guides"],
    "domain": ["lease_law", "tenant_protection"],
}


def search_legal_rag(
    query: str,
    question_type: str | None,
    *,
    top_k: int = 5,
    include_graph_context: bool = True,
) -> dict[str, Any]:
    qtype = question_type or "GENERAL"
    config = QUESTION_TYPE_RAG_MAP.get(qtype, DEFAULT_RAG_CONFIG)
    pack = adaptive_rag(
        "legal_basis",
        query,
        filters={
            "tables": config["tables"],
            "domain": config["domain"],
            "jurisdiction": "KR",
            "question_type": qtype,
            "include_graph_context": include_graph_context,
        },
        top_k=top_k,
    )
    references = [
        {
            "source_id": context.source_id,
            "title": context.title,
            "doc_type": context.doc_type,
            "score": context.score,
            "chunk_text": context.text[:700],
            "metadata": context.metadata,
        }
        for context in pack.contexts
    ]
    graph_context = [
        {"node": item.node, "relation": item.relation, "target": item.target}
        for item in pack.graph_context
    ]
    rag_status = _rag_status(references, pack.quality.score)
    return {
        "query": query,
        "question_type": qtype,
        "tables": config["tables"],
        "domain": config["domain"],
        "references": references,
        "graph_context": graph_context,
        "quality": {
            "sufficient": pack.quality.sufficient,
            "score": pack.quality.score,
            "reason": pack.quality.reason,
        },
        "rag_status": rag_status,
    }


def _rag_status(references: list[dict[str, Any]], score: float) -> str:
    if not references:
        return "RAG_UNAVAILABLE"
    if score < 0.45:
        return "RAG_LOW_QUALITY"
    return "RAG_OK"


@tool
def search_legal_rag_tool(
    query: str,
    question_type: str | None = None,
    top_k: int = 5,
    include_graph_context: bool = True,
) -> dict[str, Any]:
    """Search legal RAG evidence for a legal consultation question."""
    return search_legal_rag(
        query=query,
        question_type=question_type,
        top_k=top_k,
        include_graph_context=include_graph_context,
    )
