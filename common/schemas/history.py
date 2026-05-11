"""Diagnosis history schemas for the record/comparison screen."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"]
RiskBucket = Literal["SAFE", "CAUTION", "RISK"]


@dataclass
class DiagnosisHistoryItem:
    """Compact diagnosis record stored for the history screen."""

    diagnosis_id: str
    created_at: str
    address: str | None = None
    housing_type: str | None = None
    deposit_amount: int | None = None
    monthly_rent: int | None = None
    risk_score: int | None = None
    risk_level: RiskLevel = "UNKNOWN"
    risk_bucket: RiskBucket = "CAUTION"
    favorite: bool = False
    title: str | None = None
    summary: str | None = None
    evidence_chip_count: int = 0
    finding_count: int = 0
    high_priority_count: int = 0
    report_json: dict[str, Any] = field(default_factory=dict)
    ui_response_json: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosisHistoryStats:
    """Risk statistics for the diagnosis history screen."""

    total_count: int = 0
    risk_count: int = 0
    caution_count: int = 0
    safe_count: int = 0
    favorite_count: int = 0
    average_risk_score: float | None = None


@dataclass
class DiagnosisComparisonResult:
    """Side-by-side comparison result for selected diagnosis records."""

    selected_count: int
    items: list[dict[str, Any]]
    common_risks: list[str] = field(default_factory=list)
    different_risks: list[str] = field(default_factory=list)
    highest_risk_item_id: str | None = None
    summary: str = ""


def now_iso() -> str:
    """Return current local-ish timestamp string for simple record creation."""
    return datetime.now().isoformat(timespec="seconds")