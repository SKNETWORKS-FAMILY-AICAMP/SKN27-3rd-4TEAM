"""Evidence chip builders for frontend-facing UI responses."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from langchain_core.tools import tool

from common.schemas.ui import EvidenceChip, EvidenceChipType

DOC_TYPE_TO_CHIP_TYPE: dict[str, EvidenceChipType] = {
    "contract": "CONTRACT",
    "registry": "REGISTRY",
    "law": "LAW",
    "case": "CASE",
    "judgement": "CASE",
    "judgment": "CASE",
    "casebook": "CASEBOOK",
    "guide": "GUIDE",
    "checklist": "CHECKLIST",
    "market": "MARKET",
    "external": "EXTERNAL",
    "graph": "GRAPH",
}

SOURCE_TYPE_TO_CHIP_TYPE: dict[str, EvidenceChipType] = {
    "naver_web_search": "EXTERNAL",
    "serpapi_google_search": "EXTERNAL",
    "custom_search": "EXTERNAL",
    "mock_external_fallback": "EXTERNAL",
}


def build_evidence_chips(report: dict[str, Any] | None) -> list[EvidenceChip]:
    """Build unified evidence chips from any graph report.

    Supported report shapes:
    - diagnosis report: rag_references
    - legal consultation report: cited_cases, cited_laws, external_sources
    - defense simulation report: evidence_report.references
    """
    if not report:
        return []

    chips: list[EvidenceChip] = []
    chips.extend(_chips_from_rag_references(report.get("rag_references", [])))
    chips.extend(_chips_from_cited_cases(report.get("cited_cases", [])))
    chips.extend(_chips_from_cited_laws(report.get("cited_laws", [])))
    chips.extend(_chips_from_external_sources(report.get("external_sources", [])))
    chips.extend(_chips_from_defense_evidence(report.get("evidence_report", {})))
    chips.extend(_chips_from_market_analysis(report.get("market_analysis")))
    return _dedupe_chips(chips)


def _chips_from_rag_references(items: Any) -> list[EvidenceChip]:
    chips: list[EvidenceChip] = []
    for item in _as_list(items):
        data = _to_dict(item)
        doc_type = str(data.get("doc_type") or "unknown").lower()
        title = data.get("title") or data.get("source_id") or "RAG 근거"
        chips.append(EvidenceChip(
            label=_label_for_doc_type(doc_type, title),
            chip_type=_chip_type_from_doc_type(doc_type),
            source_id=data.get("source_id"),
            title=title,
            score=_to_float(data.get("score")),
            metadata=_compact_metadata(data, exclude={"source_id", "title", "doc_type", "score"}),
        ))
    return chips


def _chips_from_cited_cases(items: Any) -> list[EvidenceChip]:
    chips: list[EvidenceChip] = []
    for item in _as_list(items):
        data = _to_dict(item)
        title = data.get("issue") or data.get("case_number") or "판례/사례 근거"
        label_parts = [part for part in [data.get("court"), data.get("case_number")] if part]
        label = " ".join(label_parts) if label_parts else str(title)
        chips.append(EvidenceChip(
            label=label,
            chip_type="CASE",
            source_id=data.get("source_id"),
            title=str(title),
            summary=data.get("summary"),
            metadata=_compact_metadata(data, exclude={"source_id", "issue", "summary"}),
        ))
    return chips


def _chips_from_cited_laws(items: Any) -> list[EvidenceChip]:
    chips: list[EvidenceChip] = []
    for item in _as_list(items):
        data = _to_dict(item)
        title = data.get("title") or "법령/가이드 근거"
        chips.append(EvidenceChip(
            label=str(title),
            chip_type="LAW",
            source_id=data.get("source_id"),
            title=str(title),
            summary=data.get("summary"),
            metadata=_compact_metadata(data, exclude={"source_id", "title", "summary"}),
        ))
    return chips


def _chips_from_external_sources(items: Any) -> list[EvidenceChip]:
    chips: list[EvidenceChip] = []
    for item in _as_list(items):
        data = _to_dict(item)
        title = data.get("title") or data.get("publisher") or "외부 자료"
        source_type = str(data.get("source_type") or "external")
        chips.append(EvidenceChip(
            label=str(data.get("publisher") or title),
            chip_type=SOURCE_TYPE_TO_CHIP_TYPE.get(source_type, "EXTERNAL"),
            source_id=data.get("source_id"),
            title=str(title),
            summary=data.get("summary"),
            url=data.get("url"),
            metadata=_compact_metadata(data, exclude={"source_id", "title", "summary", "url"}),
        ))
    return chips


def _chips_from_defense_evidence(evidence_report: Any) -> list[EvidenceChip]:
    data = _to_dict(evidence_report)
    chips: list[EvidenceChip] = []
    for item in _as_list(data.get("references", [])):
        ref = _to_dict(item)
        doc_type = str(ref.get("doc_type") or "casebook").lower()
        title = ref.get("title") or ref.get("source_id") or "사례집 근거"
        metadata = _compact_metadata(ref, exclude={"source_id", "title", "doc_type", "score"})
        if data.get("source_case"):
            metadata["source_case"] = data.get("source_case")
        if data.get("query"):
            metadata["query"] = data.get("query")
        chips.append(EvidenceChip(
            label=_label_for_doc_type(doc_type, title),
            chip_type=_chip_type_from_doc_type(doc_type),
            source_id=ref.get("source_id"),
            title=str(title),
            score=_to_float(ref.get("score")),
            metadata=metadata,
        ))
    return chips


def _chips_from_market_analysis(market_analysis: Any) -> list[EvidenceChip]:
    data = _to_dict(market_analysis)
    if not data:
        return []
    count = data.get("comparable_jeonse_count", 0) or 0
    sale_count = data.get("comparable_sale_count", 0) or 0
    if not count and not sale_count:
        return []
    label = f"시세 비교 {count}건"
    summary = None
    if data.get("estimated_jeonse_ratio") is not None:
        summary = f"추정 전세가율 {float(data['estimated_jeonse_ratio']):.1f}%"
    return [EvidenceChip(
        label=label,
        chip_type="MARKET",
        title="전월세/매매 실거래가 비교",
        summary=summary,
        score=None,
        metadata=data,
    )]


def _dedupe_chips(chips: list[EvidenceChip]) -> list[EvidenceChip]:
    seen: set[tuple[str, str | None, str | None]] = set()
    unique: list[EvidenceChip] = []
    for chip in chips:
        key = (chip.chip_type, chip.source_id, chip.title)
        if key in seen:
            continue
        seen.add(key)
        unique.append(chip)
    return unique


def _chip_type_from_doc_type(doc_type: str) -> EvidenceChipType:
    return DOC_TYPE_TO_CHIP_TYPE.get(doc_type.lower(), "UNKNOWN")


def _label_for_doc_type(doc_type: str, title: Any) -> str:
    chip_type = _chip_type_from_doc_type(doc_type)
    prefix = {
        "CONTRACT": "계약서",
        "REGISTRY": "등기부",
        "LAW": "법령",
        "CASE": "판례",
        "CASEBOOK": "사례",
        "GUIDE": "가이드",
        "CHECKLIST": "체크리스트",
        "MARKET": "시세",
        "EXTERNAL": "외부자료",
        "GRAPH": "관계근거",
        "UNKNOWN": "근거",
    }[chip_type]
    return f"{prefix}: {title}"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    return {}


def _compact_metadata(data: dict[str, Any], *, exclude: set[str]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in exclude and value not in (None, "", [], {})}


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@tool
def build_evidence_chips_tool(report: dict[str, Any]) -> list[EvidenceChip]:
    """Convert graph report evidence fields into frontend EvidenceChip objects."""
    return build_evidence_chips(report)