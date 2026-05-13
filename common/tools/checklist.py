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
VERIFICATION_EVIDENCE_TYPES = {"CONTRACT", "REGISTRY", "MARKET"}
AUTO_DONE_BY_EVIDENCE: dict[str, set[str]] = {
    "CHECK_CONTRACT_PARTIES": {"CONTRACT"},
    "CHECK_MARKET_RATIO": {"MARKET"},
    "CHECK_REGISTRY_OWNER": {"REGISTRY"},
    "CHECK_LIEN_SEIZURE_TRUST": {"REGISTRY"},
    "RECHECK_REGISTRY_BEFORE_BALANCE": {"REGISTRY_BALANCE_DAY"},
}


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
    verified_evidence_types = _verified_evidence_types(report)
    guidance_evidence_types = _guidance_evidence_types(report)
    user_checked_items = _user_checked_items(report)

    stages: list[dict[str, Any]] = []
    total = 0
    done = 0
    caution = 0

    for stage in definition.get("stages", []):
        stage_items: list[dict[str, Any]] = []
        for item in stage.get("items", []):
            total += 1
            status, reason = _item_status(
                item,
                finding_codes,
                high_risk_codes,
                verified_evidence_types,
                guidance_evidence_types,
                user_checked_items,
            )
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
    verified_evidence_types: set[str],
    guidance_evidence_types: set[str],
    user_checked_items: set[str],
) -> tuple[ChecklistItemStatus, str]:
    item_id = str(item.get("id") or "")
    auto_keywords = set(item.get("auto_keywords", []))
    item_evidence_types = set(item.get("evidence_types", []))
    allowed_requirements = AUTO_DONE_BY_EVIDENCE.get(item_id, set())
    verification_requirements = item_evidence_types & VERIFICATION_EVIDENCE_TYPES
    if item_id == "RECHECK_REGISTRY_BEFORE_BALANCE":
        verification_requirements = {"REGISTRY_BALANCE_DAY"}
    has_guidance = bool(item_evidence_types & guidance_evidence_types)

    if auto_keywords and auto_keywords & high_risk_codes:
        return "CAUTION", "진단 결과에서 관련 고위험 항목이 발견되었습니다."
    if auto_keywords and auto_keywords & finding_codes:
        return "CAUTION", "진단 결과에서 관련 확인 필요 항목이 발견되었습니다."
    if item_id and item_id in user_checked_items:
        return "DONE", "사용자가 직접 확인 완료로 표시한 항목입니다."
    if (
        verification_requirements
        and verification_requirements <= verified_evidence_types
        and verification_requirements <= allowed_requirements
    ):
        return "DONE", "업로드/분석된 실제 확인 자료가 있어 완료로 표시했습니다."
    if verification_requirements and verification_requirements <= verified_evidence_types:
        return "TODO", "관련 자료는 있지만, 이 항목은 사용자가 실제 이행 여부를 확인해야 완료됩니다."
    if has_guidance:
        return "TODO", "관련 RAG 근거는 있지만, 사용자가 실제 확인해야 완료됩니다."
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


def _verified_evidence_types(report: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    if _has_verified_contract_fields(report):
        types.add("CONTRACT")
    if _has_verified_market_analysis(report):
        types.add("MARKET")
    if _has_verified_registry_fields(report):
        types.add("REGISTRY")
    if _has_balance_day_registry_evidence(report):
        types.add("REGISTRY_BALANCE_DAY")
    for doc in report.get("uploaded_documents", []) or []:
        doc_type = _normalize_evidence_type(str(doc.get("doc_type") or doc.get("type") or ""))
        if doc_type in VERIFICATION_EVIDENCE_TYPES:
            types.add(doc_type)
        checked_at = str(doc.get("checked_at") or doc.get("timing") or "")
        if doc_type == "REGISTRY" and _is_balance_day_timing(checked_at):
            types.add("REGISTRY_BALANCE_DAY")
    return types


def _has_verified_contract_fields(report: dict[str, Any]) -> bool:
    fields = report.get("contract_fields")
    if not isinstance(fields, dict) or not fields:
        return False
    if report.get("contract_source") == "mock_contract":
        return False
    core_keys = ("landlord", "tenant", "address", "deposit_amount", "contract_start", "contract_end")
    return sum(1 for key in core_keys if fields.get(key) not in (None, "", [], {})) >= 3


def _has_verified_market_analysis(report: dict[str, Any]) -> bool:
    analysis = report.get("market_analysis")
    if not isinstance(analysis, dict) or not analysis:
        return False
    if analysis.get("input_deposit_amount") in (None, ""):
        return False
    if analysis.get("estimated_jeonse_ratio") not in (None, ""):
        return True
    comparable_counts = (
        int(_safe_number(analysis.get("comparable_jeonse_count")) or 0),
        int(_safe_number(analysis.get("comparable_sale_count")) or 0),
    )
    return any(count > 0 for count in comparable_counts)


def _has_verified_registry_fields(report: dict[str, Any]) -> bool:
    registry = report.get("registry_analysis") or report.get("registry_fields")
    if not isinstance(registry, dict) or not registry:
        return False
    return any(value not in (None, "", [], {}) for value in registry.values())


def _has_balance_day_registry_evidence(report: dict[str, Any]) -> bool:
    if report.get("balance_day_registry_fields") or report.get("registry_balance_day_analysis"):
        return True
    checked_at = str(report.get("registry_checked_at") or report.get("registry_timing") or "")
    return _is_balance_day_timing(checked_at)


def _safe_number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _is_balance_day_timing(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"balance_day", "before_balance", "잔금일", "잔금직전", "잔금 전", "잔금 전 확인"}


def _guidance_evidence_types(report: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    for ref in report.get("rag_references", []) or []:
        doc_type = str(ref.get("doc_type", ""))
        if doc_type:
            types.add(_normalize_evidence_type(doc_type))
    return types


def _user_checked_items(report: dict[str, Any]) -> set[str]:
    values = (
        report.get("user_checked_items")
        or report.get("checked_items")
        or report.get("completed_checklist_items")
        or []
    )
    if isinstance(values, dict):
        values = [key for key, checked in values.items() if checked]
    return {str(value) for value in values if value}


def _normalize_evidence_type(value: str) -> str:
    mapping = {
        "LAW": "LAW",
        "법령": "LAW",
        "CASE": "CASE",
        "판례": "CASE",
        "판결": "CASE",
        "JUDGEMENT": "CASE",
        "JUDGMENT": "CASE",
        "CASEBOOK": "CASEBOOK",
        "사례": "CASEBOOK",
        "사례집": "CASEBOOK",
        "GUIDE": "GUIDE",
        "가이드": "GUIDE",
        "CHECKLIST": "CHECKLIST",
        "체크리스트": "CHECKLIST",
        "서식": "CHECKLIST",
        "MARKET": "MARKET",
        "시세": "MARKET",
        "CONTRACT": "CONTRACT",
        "계약서": "CONTRACT",
        "REGISTRY": "REGISTRY",
        "등기부": "REGISTRY",
    }
    normalized = value.strip()
    return mapping.get(normalized, mapping.get(normalized.upper(), normalized.upper()))


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
