"""Shared dataclasses used by diagnosis agents and tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

FindingSeverity = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"]
AgentStatus = Literal["COMPLETE", "PARTIAL", "NOT_IMPLEMENTED", "FAILED"]
Confidence = Literal["LOW", "MEDIUM", "HIGH"]
FallbackLevel = Literal["LOW", "MEDIUM", "HIGH"]

MAX_EVIDENCE_REFS = 30
MAX_GRAPH_CONTEXT = 20


class ReviewStatus(str, Enum):
    PASS = "PASS"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    NEED_MORE_EVIDENCE = "NEED_MORE_EVIDENCE"
    NEED_GRAPH_CONTEXT = "NEED_GRAPH_CONTEXT"
    NEED_CLARIFICATION = "NEED_CLARIFICATION"
    NEED_COUNSELOR_REWRITE = "NEED_COUNSELOR_REWRITE"
    FAIL = "FAIL"


@dataclass
class RetrievedContext:
    source_id: str
    title: str
    doc_type: str
    text: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalQuality:
    sufficient: bool
    score: float
    reason: str


@dataclass
class GraphContextItem:
    """Graph context triple used for RAG response and review verification."""

    node: str
    relation: str
    target: str
    severity: str | None = None
    confidence: Confidence | None = None
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextPack:
    task_type: str
    query: str
    contexts: list[RetrievedContext] = field(default_factory=list)
    quality: RetrievalQuality = field(default_factory=lambda: RetrievalQuality(False, 0.0, "not evaluated"))
    graph_context: list[GraphContextItem] = field(default_factory=list)


@dataclass
class Claim:
    """Reviewable claim. Claims, not legal_points, must be tied to evidence."""

    claim_id: str
    text: str
    task: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    graph_context_ids: list[str] = field(default_factory=list)
    confidence: Confidence = "MEDIUM"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewResult:
    status: ReviewStatus
    reason: str
    required_action: str | None = None
    missing_evidence_query: str | None = None
    graph_context_query: str | None = None
    target_agent: str | None = None
    confidence: Confidence = "MEDIUM"


@dataclass
class RiskFinding:
    code: str
    title: str
    severity: FindingSeverity
    score_delta: int
    description: str
    evidence: list[str] = field(default_factory=list)
    required_action: str | None = None
    source: str = "agent"


@dataclass
class AgentTrace:
    agent: str
    action: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
