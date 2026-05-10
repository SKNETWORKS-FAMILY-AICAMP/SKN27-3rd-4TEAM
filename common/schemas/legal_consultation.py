"""Legal consultation graph-specific schemas."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from common.schemas.shared import AgentTrace, ContextPack

QuestionType = Literal[
    "SPECIAL_CLAUSE",
    "DEPOSIT_RETURN",
    "OPPOSING_POWER",
    "PREFERRED_PAYMENT",
    "REGISTRY_RISK",
    "SENIOR_TENANT",
    "TRUST_REGISTRATION",
    "TAX_ARREARS",
    "JEONSE_FRAUD_CASE",
    "GENERAL_LEGAL_INFO",
    "UNKNOWN",
]

BasisType = Literal["INTERNAL_CASE", "INTERNAL_LAW", "EXTERNAL_SOURCE", "MIXED", "INSUFFICIENT"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass
class CitedCase:
    court: str | None = None
    case_number: str | None = None
    issue: str | None = None
    summary: str = ""
    relevance: str = ""
    source_id: str | None = None


@dataclass
class CitedLaw:
    title: str
    summary: str
    source_id: str | None = None


@dataclass
class ExternalSource:
    title: str
    publisher: str | None = None
    url: str | None = None
    summary: str = ""
    source_type: str = "external"


@dataclass
class EvidenceQuality:
    sufficient: bool
    score: float
    basis_type: BasisType
    reason: str


class LegalConsultationState(TypedDict, total=False):
    session_id: str
    question: str
    related_finding: dict[str, Any] | None
    contract_context: dict[str, Any] | None

    question_type: QuestionType
    normalized_query: str

    internal_case_context: ContextPack
    internal_law_context: ContextPack
    evidence_quality: EvidenceQuality
    needs_external_search: bool
    used_external_search: bool
    external_sources: list[ExternalSource]

    cited_cases: list[CitedCase]
    cited_laws: list[CitedLaw]
    answer_draft: str
    final_answer: str
    basis_type: BasisType
    confidence: Confidence
    recommended_actions: list[str]
    disclaimer: str
    report: dict[str, Any]
    agent_trace: list[AgentTrace]
    errors: list[str]
