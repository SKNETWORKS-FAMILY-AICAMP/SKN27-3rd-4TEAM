"""Schemas for the legal consultation graph."""
from __future__ import annotations

from enum import Enum
from typing import Any

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    def Field(default=None, default_factory=None, **_: Any):
        return default_factory() if default_factory is not None else default

    class BaseModel:
        def __init__(self, **kwargs: Any):
            for name, value in self.__class__.__dict__.items():
                if name.startswith("_") or callable(value):
                    continue
                setattr(self, name, kwargs.pop(name, value))
            for name, value in kwargs.items():
                setattr(self, name, value)

        def model_dump(self) -> dict[str, Any]:
            result = {}
            for key, value in self.__dict__.items():
                result[key] = value.value if isinstance(value, Enum) else value
            return result


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
    claims: list[dict[str, Any]] = Field(default_factory=list)
    legal_points: list[str] = Field(default_factory=list)
    answer_draft: str = ""
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    graph_context: list[dict[str, Any]] = Field(default_factory=list)
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
