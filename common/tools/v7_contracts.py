"""v7 implementation contracts for RAG, evidence, graph context, and review."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, is_dataclass
from typing import Any

from common.schemas.shared import MAX_EVIDENCE_REFS, MAX_GRAPH_CONTEXT, GraphContextItem, RetrievedContext

LOGICAL_TABLE_DOC_TYPES: dict[str, list[str]] = {
    "law_documents": ["법령", "law"],
    "case_documents": ["판례", "분쟁조정례", "사례집", "case", "dispute_case"],
    "public_guides": ["가이드", "사례집", "정책자료", "public_guide"],
    "contract_checklists": ["체크리스트", "서식", "checklist", "form"],
    "special_clause_examples": ["특약", "서식", "체크리스트"],
    "registry_guides": ["등기", "권리관계", "체크리스트"],
    "insurance_guides": ["보증보험", "가이드", "약관", "insurance"],
    "market_risk_guides": ["시세데이터", "보고서", "시장분석", "market_data"],
    "procedure_guides": ["절차", "가이드", "서식"],
    "faq_documents": ["FAQ", "질의응답", "faq"],
}


def raw_rag_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """v7 standard uses results; legacy references are accepted as alias."""
    items = payload.get("results")
    if items is None:
        items = payload.get("references", [])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def normalize_evidence_refs(raw_items: list[dict[str, Any]], *, fallback_table: str | None = None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, 1):
        metadata = dict(item.get("metadata") or {})
        table = item.get("table") or metadata.get("table") or fallback_table or _table_from_doc_type(item.get("doc_type"))
        doc_id = (
            item.get("doc_id")
            or item.get("source_id")
            or item.get("chunk_id")
            or item.get("vector_id")
            or _generated_doc_id(item, index)
        )
        metadata["table"] = table
        normalized.append(
            {
                "doc_id": str(doc_id),
                "source_id": str(item.get("source_id") or doc_id),
                "title": str(item.get("title") or "RAG 근거 문서"),
                "table": str(table),
                "doc_type": str(item.get("doc_type") or metadata.get("doc_type") or ""),
                "source_type": str(item.get("source_type") or metadata.get("source_type") or ""),
                "domain": item.get("domain") or metadata.get("domain") or [],
                "authority_level": str(item.get("authority_level") or metadata.get("authority_level") or ""),
                "snippet": str(item.get("snippet") or item.get("chunk_text") or item.get("content") or "")[:700],
                "chunk_text": str(item.get("chunk_text") or item.get("content") or item.get("snippet") or "")[:1200],
                "score": _to_float(item.get("score", item.get("relevance_score", 0.0))),
                "source_url": item.get("source_url") or metadata.get("source_url"),
                "metadata": metadata,
            }
        )
    return prune_evidence_refs(normalized)


def references_to_contexts(items: list[dict[str, Any]]) -> list[RetrievedContext]:
    contexts: list[RetrievedContext] = []
    for index, item in enumerate(items, 1):
        metadata = dict(item.get("metadata") or {})
        contexts.append(
            RetrievedContext(
                source_id=str(item.get("source_id") or item.get("doc_id") or f"rag-ref-{index}"),
                title=str(item.get("title") or "RAG 근거 문서"),
                doc_type=str(item.get("doc_type") or ""),
                text=str(item.get("chunk_text") or item.get("snippet") or ""),
                score=_to_float(item.get("score", 0.0)),
                metadata=metadata,
            )
        )
    return contexts


def parse_graph_context(raw: Any) -> list[GraphContextItem]:
    items = raw if isinstance(raw, list) else []
    result: list[GraphContextItem] = []
    for item in items:
        data = asdict(item) if is_dataclass(item) else item
        if not isinstance(data, dict):
            continue
        node = str(data.get("node") or "").strip()
        relation = str(data.get("relation") or "").strip()
        target = str(data.get("target") or "").strip()
        if node and relation and target:
            result.append(
                GraphContextItem(
                    node=node,
                    relation=relation,
                    target=target,
                    severity=data.get("severity"),
                    confidence=data.get("confidence"),
                    source=data.get("source"),
                    metadata=dict(data.get("metadata") or {}),
                )
            )
    return prune_graph_context(result)


def graph_context_to_dicts(items: list[GraphContextItem] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        data = asdict(item) if is_dataclass(item) else item
        if isinstance(data, dict):
            result.append(data)
    return result


def prune_evidence_refs(items: list[dict[str, Any]], *, current_task: str | None = None, limit: int = MAX_EVIDENCE_REFS) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("doc_id") or item.get("source_id") or item.get("chunk_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)

    def rank(item: dict[str, Any]) -> tuple[int, int, float]:
        metadata_text = str(item.get("metadata", {}))
        task_match = int(bool(current_task and current_task in metadata_text))
        authority = str(item.get("authority_level") or item.get("metadata", {}).get("authority_level") or "")
        authority_rank = int(authority in {"official", "court", "public_institution"})
        return (task_match, authority_rank, _to_float(item.get("score", 0.0)))

    return sorted(unique, key=rank, reverse=True)[:limit]


def prune_graph_context(items: list[GraphContextItem], *, limit: int = MAX_GRAPH_CONTEXT) -> list[GraphContextItem]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[GraphContextItem] = []
    for item in items:
        key = (item.node, item.relation, item.target)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:limit]


def merge_evidence_refs(existing: list[dict[str, Any]], additional: list[dict[str, Any]], *, current_task: str | None = None) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in existing + additional:
        doc_id = str(item.get("doc_id") or item.get("source_id") or item.get("chunk_id") or "")
        if not doc_id:
            continue
        if doc_id not in merged or _to_float(item.get("score", 0.0)) > _to_float(merged[doc_id].get("score", 0.0)):
            merged[doc_id] = item
    return prune_evidence_refs(list(merged.values()), current_task=current_task)


def merge_graph_context(existing: list[GraphContextItem], additional: list[GraphContextItem]) -> list[GraphContextItem]:
    return prune_graph_context(existing + additional)


def table_filters_to_doc_types(tables: list[str]) -> list[str]:
    doc_types: list[str] = []
    for table in tables:
        doc_types.extend(LOGICAL_TABLE_DOC_TYPES.get(table, []))
    return list(dict.fromkeys(doc_types))


def _table_from_doc_type(doc_type: Any) -> str:
    value = str(doc_type or "")
    for table, doc_types in LOGICAL_TABLE_DOC_TYPES.items():
        if value in doc_types:
            return table
    return "public_guides"


def _generated_doc_id(item: dict[str, Any], index: int) -> str:
    digest = hashlib.sha1(str(sorted(item.items())).encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"generated-{index}-{digest}"


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
