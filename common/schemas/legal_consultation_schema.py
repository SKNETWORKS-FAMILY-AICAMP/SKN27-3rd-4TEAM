"""Schemas for the legal consultation graph."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LegalIntent(str, Enum):
    GENERAL_CHAT = "GENERAL_CHAT"
    SIMPLE_EXPLANATION = "SIMPLE_EXPLANATION"
    LEGAL_RAG_REQUIRED = "LEGAL_RAG_REQUIRED"
    CASE_SPECIFIC_ADVICE = "CASE_SPECIFIC_ADVICE"
    EMOTIONAL_SUPPORT = "EMOTIONAL_SUPPORT"
    CLARIFICATION_NEEDED = "CLARIFICATION_NEEDED"


class LegalRoute(str, Enum):
    COUNSELOR = "COUNSELOR"
    LEGAL_RAG = "LEGAL_RAG"
    BOTH = "BOTH"
    CLARIFICATION = "CLARIFICATION"


class LegalQuestionType(str, Enum):
    DEPOSIT_RETURN = "DEPOSIT_RETURN"
    REGISTRY_RISK = "REGISTRY_RISK"
    DEPOSIT_INSURANCE = "DEPOSIT_INSURANCE"
    PROCEDURE_GUIDE = "PROCEDURE_GUIDE"
    SIMPLE_EXPLANATION = "SIMPLE_EXPLANATION"
    GENERAL = "GENERAL"


class LegalSupervisorDecision(BaseModel):
    intent: LegalIntent
    route: LegalRoute
    question_type: LegalQuestionType = LegalQuestionType.GENERAL
    needs_rag: bool = False
    needs_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    reason: str = ""


class LegalRagResult(BaseModel):
    question_type: LegalQuestionType | str
    rag_status: str = "RAG_UNAVAILABLE"
    confidence: str = "LOW"
    legal_points: list[str] = Field(default_factory=list)
    answer_draft: str = ""
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    llm_used: bool = False
    blocked_reason: str | None = None


class CounselorResult(BaseModel):
    answer: str = ""
    followup_questions: list[str] = Field(default_factory=list)
    llm_used: bool = False
    blocked_reason: str | None = None


class GuardrailResult(BaseModel):
    safe_answer: str = ""
    changed: bool = False
    warnings: list[str] = Field(default_factory=list)
    llm_used: bool = False
    blocked_reason: str | None = None
