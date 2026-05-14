"""Compatibility schemas for legal consultation nodes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.states.legal_consultation_state import LegalConsultationState


@dataclass
class CitedCase:
    court: str | None = None
    case_number: str | None = None
    issue: str = ""
    summary: str = ""
    relevance: str = ""
    source_id: str = ""

    @property
    def case_name(self) -> str:
        parts = [part for part in [self.court, self.case_number] if part]
        return " ".join(parts) or self.issue or self.source_id


@dataclass
class CitedLaw:
    title: str = ""
    summary: str = ""
    source_id: str = ""

    @property
    def article(self) -> str:
        return self.title


@dataclass
class ExternalSource:
    title: str = ""
    url: str = ""
    publisher: str = ""
    summary: str = ""
    source_id: str = ""


@dataclass
class EvidenceQuality:
    sufficient: bool
    score: float
    basis_type: str
    reason: str = ""


__all__ = [
    "CitedCase",
    "CitedLaw",
    "EvidenceQuality",
    "ExternalSource",
    "LegalConsultationState",
]
