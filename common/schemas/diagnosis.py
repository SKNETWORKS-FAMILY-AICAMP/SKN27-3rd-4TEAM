"""State and result schemas for the PDF-first diagnosis graph."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from common.schemas.shared import AgentTrace, ContextPack, RiskFinding, RiskLevel


@dataclass
class PdfValidationResult:
    valid: bool
    file_path: str | None
    extension: str | None = None
    file_size_bytes: int | None = None
    page_count: int | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ContractSections:
    full_text: str
    parties_text: str = ""
    property_text: str = ""
    payment_text: str = ""
    period_text: str = ""
    special_terms_text: str = ""


@dataclass
class FieldValidationResult:
    valid: bool
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DiagnosisPlan:
    run_special_clause: bool = False
    run_ownership_risk: bool = True
    run_market_risk: bool = False
    run_insurance_risk: bool = False
    run_required_check: bool = False
    run_legal_basis: bool = False
    reasons: list[str] = field(default_factory=list)
    skipped_agents: list[str] = field(default_factory=list)
    llm_required: bool = True
    llm_used: bool = False
    status: str = "PLANNED"


@dataclass
class TaskResult:
    task: str
    risk_items: list[RiskFinding] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    missing_checks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


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
    errors: list[str]
    missing_inputs: list[str]

    pdf_validation: PdfValidationResult
    contract_text: str
    page_texts: list[str]
    ocr_confidence: float | None
    contract_sections: ContractSections
    contract_fields: dict[str, Any]
    field_validation: FieldValidationResult
    diagnosis_plan: DiagnosisPlan

    context_packs: dict[str, ContextPack]
    task_results: dict[str, TaskResult]
    risk_findings: list[RiskFinding]
    risk_score: int
    risk_level: RiskLevel
    report: dict[str, Any]
    agent_trace: list[AgentTrace]
