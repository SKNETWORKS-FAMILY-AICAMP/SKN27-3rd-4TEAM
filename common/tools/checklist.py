"""Safety checklist builder for jeonse contract workflows."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool

from common.schemas.ui import ChecklistProgress

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKLIST_PATH = PROJECT_ROOT / "data" / "safety_checklist.json"

ChecklistItemStatus = Literal["DONE", "CAUTION", "TODO"]
HIGH_RISK_SEVERITIES = {"HIGH", "CRITICAL"}


def load_safety_checklist() -> dict[str, Any]:
    """Load the safety checklist definition JSON."""
    return json.loads(CHECKLIST_PATH.read_text(encoding="utf-8"))


def build_safety_checklist_status(report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build checklist item statuses from a diagnosis report.

    The checklist is user-action oriented. Automated diagnosis can only mark
    evidence-backed safe items as DONE, risk-related items as CAUTION, and the
    rest as TODO for the user to confirm.
    """
    definition = load_safety_checklist()
    report = report or {}
    finding_codes = _finding_codes(report)
    high_risk_codes = _finding_codes(report, high_only=True)
    evidence_types = _evidence_types(report)

    stages: list[dict[str, Any]] = []
    total = 0
    done = 0
    caution = 0

    for stage in definition.get("stages", []):
        stage_items: list[dict[str, Any]] = []
        for item in stage.get("items", []):
            total += 1
            status, reason = _item_status(item, finding_codes, high_risk_codes, evidence_types)
            if status == "DONE":
                done += 1
            elif status == "CAUTION":
                caution += 1
            stage_items.append({
                "id": item.get("id"),
                "label": item.get("label"),
                "description": item.get("description"),
                "priority": item.get("priority", "MEDIUM"),
                "status": status,
                "status_reason": reason,
                "evidence_types": item.get("evidence_types", []),
                "related_risk_types": item.get("related_risk_types", []),
            })
        stages.append({
            "stage_id": stage.get("stage_id"),
            "title": stage.get("title"),
            "order": stage.get("order"),
            "items": stage_items,
            "progress": _progress_for_items(stage_items),
        })

    progress_percent = round((done / total * 100), 1) if total else 0.0
    progress = ChecklistProgress(
        total_count=total,
        completed_count=done,
        caution_count=caution,
        progress_percent=progress_percent,
        status_label=_status_label(progress_percent, caution),
    )

    return {
        "title": definition.get("title", "전세계약 안전 체크리스트"),
        "version": definition.get("version"),
        "safe_threshold_percent": definition.get("safe_threshold_percent", 80),
        "progress": progress.__dict__,
        "stages": stages,
    }


def _item_status(
    item: dict[str, Any],
    finding_codes: set[str],
    high_risk_codes: set[str],
    evidence_types: set[str],
) -> tuple[ChecklistItemStatus, str]:
    auto_keywords = set(item.get("auto_keywords", []))
    item_evidence_types = set(item.get("evidence_types", []))

    if auto_keywords and auto_keywords & high_risk_codes:
        return "CAUTION", "진단 결과에서 관련 고위험 항목이 발견되었습니다."
    if auto_keywords and auto_keywords & finding_codes:
        return "CAUTION", "진단 결과에서 관련 확인 필요 항목이 발견되었습니다."
    if item_evidence_types and item_evidence_types <= evidence_types:
        return "DONE", "업로드/검색 근거가 있어 기본 확인 완료로 표시했습니다."
    return "TODO", "사용자 확인이 필요한 항목입니다."


def _finding_codes(report: dict[str, Any], *, high_only: bool = False) -> set[str]:
    codes: set[str] = set()
    for finding in report.get("findings", []) or []:
        code = finding.get("code")
        severity = str(finding.get("severity", "")).upper()
        if not code:
            continue
        if high_only and severity not in HIGH_RISK_SEVERITIES:
            continue
        codes.add(str(code))
    return codes


def _evidence_types(report: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    for ref in report.get("rag_references", []) or []:
        doc_type = str(ref.get("doc_type", "")).upper()
        if doc_type:
            types.add(_normalize_evidence_type(doc_type))
    if report.get("contract_fields"):
        types.add("CONTRACT")
    if report.get("market_analysis"):
        types.add("MARKET")
    return types


def _normalize_evidence_type(value: str) -> str:
    mapping = {
        "LAW": "LAW",
        "CASE": "CASE",
        "JUDGEMENT": "CASE",
        "JUDGMENT": "CASE",
        "CASEBOOK": "CASEBOOK",
        "GUIDE": "GUIDE",
        "CHECKLIST": "CHECKLIST",
        "MARKET": "MARKET",
        "CONTRACT": "CONTRACT",
        "REGISTRY": "REGISTRY",
    }
    return mapping.get(value.upper(), value.upper())


def _progress_for_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    done = sum(1 for item in items if item.get("status") == "DONE")
    caution = sum(1 for item in items if item.get("status") == "CAUTION")
    return {
        "total_count": total,
        "completed_count": done,
        "caution_count": caution,
        "progress_percent": round((done / total * 100), 1) if total else 0.0,
    }


def _status_label(progress_percent: float, caution_count: int) -> str:
    if caution_count > 0:
        return "주의 필요"
    if progress_percent >= 80:
        return "안전권"
    if progress_percent >= 50:
        return "확인 중"
    return "확인 필요"


@tool
def build_safety_checklist_status_tool(report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the four-stage jeonse safety checklist with progress status."""
    return build_safety_checklist_status(report)