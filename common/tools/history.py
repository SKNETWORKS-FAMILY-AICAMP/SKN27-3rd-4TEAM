"""Helpers for diagnosis history statistics and comparison."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from langchain_core.tools import tool

from common.schemas.history import (
    DiagnosisComparisonResult,
    DiagnosisHistoryItem,
    DiagnosisHistoryStats,
    now_iso,
)

RISK_LEVEL_TO_BUCKET = {
    "CRITICAL": "RISK",
    "HIGH": "RISK",
    "MEDIUM": "CAUTION",
    "LOW": "SAFE",
    "UNKNOWN": "CAUTION",
}


def create_history_item(
    report: dict[str, Any],
    ui_response: dict[str, Any] | None = None,
    *,
    diagnosis_id: str | None = None,
    favorite: bool = False,
) -> DiagnosisHistoryItem:
    """Create a compact history record from a diagnosis graph report."""
    ui_response = ui_response or {}
    fields = _to_dict(report.get("contract_fields"))
    findings = _as_list(report.get("findings"))
    risk_score = _to_int(report.get("risk_score"))
    risk_level = str(report.get("risk_level") or "UNKNOWN").upper()
    if risk_level not in RISK_LEVEL_TO_BUCKET:
        risk_level = "UNKNOWN"

    item_id = diagnosis_id or _make_diagnosis_id(report)
    title = fields.get("address") or report.get("title") or "전세계약 진단 기록"
    summary = _summary_from_report(report)

    return DiagnosisHistoryItem(
        diagnosis_id=item_id,
        created_at=now_iso(),
        address=fields.get("address"),
        housing_type=fields.get("housing_type"),
        deposit_amount=_to_int(fields.get("deposit_amount")),
        monthly_rent=_to_int(fields.get("monthly_rent")),
        risk_score=risk_score,
        risk_level=risk_level,  # type: ignore[arg-type]
        risk_bucket=RISK_LEVEL_TO_BUCKET[risk_level],  # type: ignore[arg-type]
        favorite=favorite,
        title=str(title),
        summary=summary,
        evidence_chip_count=len(_as_list(ui_response.get("evidence_chips"))),
        finding_count=len(findings),
        high_priority_count=_count_high_priority(findings),
        report_json=report,
        ui_response_json=ui_response,
        metadata={
            "source_graph": "diagnosis_graph",
            "dong_name": fields.get("dong_name"),
            "contract_start": fields.get("contract_start"),
            "contract_end": fields.get("contract_end"),
        },
    )


def summarize_history(items: list[dict[str, Any] | DiagnosisHistoryItem]) -> DiagnosisHistoryStats:
    """Calculate four-way history statistics for the record screen."""
    normalized = [_normalize_item(item) for item in items]
    scores = [item.risk_score for item in normalized if item.risk_score is not None]
    return DiagnosisHistoryStats(
        total_count=len(normalized),
        risk_count=sum(1 for item in normalized if item.risk_bucket == "RISK"),
        caution_count=sum(1 for item in normalized if item.risk_bucket == "CAUTION"),
        safe_count=sum(1 for item in normalized if item.risk_bucket == "SAFE"),
        favorite_count=sum(1 for item in normalized if item.favorite),
        average_risk_score=round(sum(scores) / len(scores), 1) if scores else None,
    )


def compare_history_items(items: list[dict[str, Any] | DiagnosisHistoryItem]) -> DiagnosisComparisonResult:
    """Compare selected diagnosis history records side by side."""
    normalized = [_normalize_item(item) for item in items]
    finding_sets = [_finding_titles(item.report_json) for item in normalized]
    common = sorted(set.intersection(*finding_sets)) if len(finding_sets) >= 2 else sorted(finding_sets[0]) if finding_sets else []
    union = set.union(*finding_sets) if finding_sets else set()
    different = sorted(union - set(common))
    highest = _highest_risk_item(normalized)

    return DiagnosisComparisonResult(
        selected_count=len(normalized),
        items=[_comparison_card(item) for item in normalized],
        common_risks=common,
        different_risks=different,
        highest_risk_item_id=highest.diagnosis_id if highest else None,
        summary=_comparison_summary(normalized, highest),
    )


def sort_history_items(items: list[dict[str, Any] | DiagnosisHistoryItem], *, sort_by: str = "created_at", descending: bool = True) -> list[dict[str, Any]]:
    """Sort history items for the record screen."""
    normalized = [_normalize_item(item) for item in items]
    key_fn = {
        "risk_score": lambda item: item.risk_score if item.risk_score is not None else -1,
        "created_at": lambda item: item.created_at,
        "deposit_amount": lambda item: item.deposit_amount if item.deposit_amount is not None else -1,
        "favorite": lambda item: item.favorite,
    }.get(sort_by, lambda item: item.created_at)
    return [asdict(item) for item in sorted(normalized, key=key_fn, reverse=descending)]


def filter_history_items(
    items: list[dict[str, Any] | DiagnosisHistoryItem],
    *,
    risk_bucket: str | None = None,
    favorite: bool | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """Filter history items by risk bucket, favorite flag, or keyword."""
    normalized = [_normalize_item(item) for item in items]
    result: list[DiagnosisHistoryItem] = []
    for item in normalized:
        if risk_bucket and item.risk_bucket != risk_bucket:
            continue
        if favorite is not None and item.favorite != favorite:
            continue
        if keyword:
            haystack = " ".join(str(value or "") for value in [item.title, item.address, item.housing_type, item.summary])
            if keyword not in haystack:
                continue
        result.append(item)
    return [asdict(item) for item in result]


def _normalize_item(item: dict[str, Any] | DiagnosisHistoryItem) -> DiagnosisHistoryItem:
    if isinstance(item, DiagnosisHistoryItem):
        return item
    return DiagnosisHistoryItem(**item)


def _summary_from_report(report: dict[str, Any]) -> str:
    risk_score = report.get("risk_score", "알 수 없음")
    risk_level = report.get("risk_level", "UNKNOWN")
    findings = _as_list(report.get("findings"))
    titles = [str(_to_dict(finding).get("title")) for finding in findings[:2] if _to_dict(finding).get("title")]
    if titles:
        return f"위험도 {risk_score}점({risk_level}), 주요 항목: {', '.join(titles)}"
    return f"위험도 {risk_score}점({risk_level})"


def _make_diagnosis_id(report: dict[str, Any]) -> str:
    fields = _to_dict(report.get("contract_fields"))
    seed = json.dumps({
        "address": fields.get("address"),
        "deposit_amount": fields.get("deposit_amount"),
        "risk_score": report.get("risk_score"),
        "risk_level": report.get("risk_level"),
    }, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"diag-{digest}"


def _finding_titles(report: dict[str, Any]) -> set[str]:
    return {str(_to_dict(finding).get("title")) for finding in _as_list(report.get("findings")) if _to_dict(finding).get("title")}


def _comparison_card(item: DiagnosisHistoryItem) -> dict[str, Any]:
    return {
        "diagnosis_id": item.diagnosis_id,
        "title": item.title,
        "address": item.address,
        "housing_type": item.housing_type,
        "deposit_amount": item.deposit_amount,
        "risk_score": item.risk_score,
        "risk_level": item.risk_level,
        "risk_bucket": item.risk_bucket,
        "favorite": item.favorite,
        "finding_titles": sorted(_finding_titles(item.report_json)),
    }


def _highest_risk_item(items: list[DiagnosisHistoryItem]) -> DiagnosisHistoryItem | None:
    if not items:
        return None
    return max(items, key=lambda item: item.risk_score if item.risk_score is not None else -1)


def _comparison_summary(items: list[DiagnosisHistoryItem], highest: DiagnosisHistoryItem | None) -> str:
    if not items:
        return "비교할 진단 기록이 없습니다."
    if len(items) == 1:
        return "진단 기록 1건이 선택되었습니다. 2건 이상 선택하면 비교가 가능합니다."
    if highest:
        return f"선택한 {len(items)}건 중 위험도가 가장 높은 기록은 {highest.title}입니다."
    return f"선택한 {len(items)}건을 비교했습니다."


def _count_high_priority(findings: list[Any]) -> int:
    return sum(1 for finding in findings if str(_to_dict(finding).get("severity", "")).upper() in {"HIGH", "CRITICAL"})


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


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


@tool
def create_history_item_tool(report: dict[str, Any], ui_response: dict[str, Any] | None = None, diagnosis_id: str | None = None, favorite: bool = False) -> dict[str, Any]:
    """Create a compact diagnosis history item from a graph report."""
    return asdict(create_history_item(report, ui_response, diagnosis_id=diagnosis_id, favorite=favorite))


@tool
def summarize_history_tool(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate total/risk/caution/safe/favorite statistics for history items."""
    return asdict(summarize_history(items))


@tool
def compare_history_items_tool(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare selected diagnosis history items side by side."""
    return asdict(compare_history_items(items))