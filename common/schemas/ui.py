"""UI-facing response schemas shared by service screens.

These dataclasses are intentionally frontend-oriented. Graph outputs can keep
rich internal state, while adapters convert them into this stable shape for the
chat, diagnosis, playbook, checklist, and simulator screens.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EvidenceChipType = Literal[
    "CONTRACT",
    "REGISTRY",
    "LAW",
    "CASE",
    "CASEBOOK",
    "GUIDE",
    "CHECKLIST",
    "MARKET",
    "EXTERNAL",
    "GRAPH",
    "UNKNOWN",
]

ScreenType = Literal[
    "CHAT_DIAGNOSIS",
    "LEGAL_CHAT",
    "DEFENSE_TRAINING",
    "DIAGNOSIS_HISTORY",
    "RECOVERY_SIMULATOR",
    "PLAYBOOK",
    "SAFETY_CHECKLIST",
]

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"]
ActionPriority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass
class EvidenceChip:
    """Small source chip shown under an answer or risk finding."""

    label: str
    chip_type: EvidenceChipType = "UNKNOWN"
    source_id: str | None = None
    title: str | None = None
    summary: str | None = None
    url: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskSummary:
    """Compact risk block for cards, chat headers, and comparison tables."""

    risk_score: int | None = None
    risk_level: RiskLevel = "UNKNOWN"
    title: str | None = None
    summary: str | None = None
    finding_count: int = 0
    high_priority_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecommendedAction:
    """User-facing next action item."""

    label: str
    priority: ActionPriority = "MEDIUM"
    reason: str | None = None
    related_source_ids: list[str] = field(default_factory=list)
    done: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChecklistProgress:
    """Progress summary for the safety checklist screen."""

    total_count: int = 0
    completed_count: int = 0
    caution_count: int = 0
    progress_percent: float = 0.0
    status_label: str = "UNKNOWN"


@dataclass
class RelatedCaseSummary:
    """Card-sized case or judgment summary."""

    title: str
    case_id: str | None = None
    court: str | None = None
    case_number: str | None = None
    issue: str | None = None
    summary: str = ""
    relevance: str = ""
    evidence_chip: EvidenceChip | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedUIResponse:
    """Stable response shape consumed by the frontend screens."""

    screen_type: ScreenType
    title: str
    session_id: str | None = None
    subtitle: str | None = None
    answer: str | None = None
    risk: RiskSummary | None = None
    evidence_chips: list[EvidenceChip] = field(default_factory=list)
    recommended_actions: list[RecommendedAction] = field(default_factory=list)
    checklist_progress: ChecklistProgress | None = None
    related_cases: list[RelatedCaseSummary] = field(default_factory=list)
    primary_payload: dict[str, Any] = field(default_factory=dict)
    agent_trace: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary for API responses."""
        return asdict(self)