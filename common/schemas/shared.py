"""Shared schemas used across multiple agent graphs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"]
FindingSeverity = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


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
class ContextPack:
    task_type: str
    query: str
    contexts: list[RetrievedContext] = field(default_factory=list)
    quality: RetrievalQuality = field(default_factory=lambda: RetrievalQuality(False, 0.0, "not evaluated"))
    rewritten_query: str | None = None


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
