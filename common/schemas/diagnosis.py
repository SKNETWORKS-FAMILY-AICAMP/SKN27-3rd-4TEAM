"""Diagnosis graph-specific schemas."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict, Any

from common.schemas.shared import AgentTrace, ContextPack, RiskFinding, RiskLevel


@dataclass
class MarketAnalysis:
    housing_type: str | None = None
    dong_name: str | None = None
    input_deposit_amount: int | None = None
    input_area_m2: float | None = None
    comparable_jeonse_count: int = 0
    comparable_sale_count: int = 0
    median_jeonse_deposit: float | None = None
    median_sale_price: float | None = None
    estimated_jeonse_ratio: float | None = None
    deposit_percentile: float | None = None
    predicted_jeonse_deposit_24m: float | None = None
    predicted_sale_price_24m: float | None = None
    predicted_jeonse_ratio_24m: float | None = None
    forecast_confidence: Literal["LOW", "MEDIUM", "HIGH"] | None = None
    forecast_source: str | None = None
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    notes: list[str] = field(default_factory=list)


class DiagnosisState(TypedDict, total=False):
    session_id: str
    contract_file: str | None
    analysis_ready: bool
    missing_inputs: list[str]

    contract_text: str
    page_texts: list[str]
    ocr_confidence: float | None
    contract_fields: dict[str, Any]

    context_packs: dict[str, ContextPack]
    clause_findings: list[RiskFinding]
    missing_defensive_clauses: list[RiskFinding]
    recommended_revisions: list[str]
    market_analysis: MarketAnalysis
    market_findings: list[RiskFinding]
    required_check_findings: list[RiskFinding]

    risk_findings: list[RiskFinding]
    risk_score: int
    risk_level: RiskLevel
    report: dict[str, Any]
    agent_trace: list[AgentTrace]
    errors: list[str]
