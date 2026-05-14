"""Structured Review Supervisor for v7 graph loops."""
from __future__ import annotations

import json
from typing import Any, Literal

try:
    from pydantic import BaseModel, ValidationError
except ImportError:  # pragma: no cover
    class ValidationError(Exception):
        pass

    class BaseModel:
        def __init__(self, **kwargs: Any):
            for key, value in kwargs.items():
                setattr(self, key, value)

        @classmethod
        def model_validate(cls, value: dict[str, Any]):
            return cls(**value)

from common.schemas.shared import ReviewResult, ReviewStatus
from common.tools.llm import LLMUnavailable, build_chat_llm


class ReviewResultModel(BaseModel):
    status: ReviewStatus
    reason: str
    required_action: str | None = None
    missing_evidence_query: str | None = None
    graph_context_query: str | None = None
    target_agent: str | None = None
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


def review_agent_output(
    *,
    current_task: str | None,
    current_agent: str | None,
    claims: list[Any],
    evidence_refs: list[dict[str, Any]],
    graph_context: list[Any],
    draft_answer: str | None = None,
    mode: str = "diagnosis",
) -> ReviewResult:
    """Return a structured ReviewResult. LLM path uses structured output; fallback is deterministic."""
    deterministic = _deterministic_review(
        current_task=current_task,
        current_agent=current_agent,
        claims=claims,
        evidence_refs=evidence_refs,
        graph_context=graph_context,
        draft_answer=draft_answer,
        mode=mode,
    )
    try:
        llm = build_chat_llm(temperature=0.0).with_structured_output(ReviewResultModel)
        result = llm.invoke(_review_prompt(current_task, current_agent, claims, evidence_refs, graph_context, draft_answer, mode))
        if isinstance(result, ReviewResultModel):
            return _to_dataclass(result)
        if isinstance(result, dict):
            return _to_dataclass(ReviewResultModel.model_validate(result))
    except (LLMUnavailable, ValidationError, Exception):
        return deterministic
    return deterministic


def _deterministic_review(
    *,
    current_task: str | None,
    current_agent: str | None,
    claims: list[Any],
    evidence_refs: list[dict[str, Any]],
    graph_context: list[Any],
    draft_answer: str | None,
    mode: str,
) -> ReviewResult:
    if not current_task and mode == "diagnosis":
        return ReviewResult(status=ReviewStatus.FAIL, reason="current_task is missing", confidence="HIGH")
    if current_agent == "friendly_counselor_agent":
        return ReviewResult(status=ReviewStatus.PASS, reason="counselor output is reviewed as expression layer", confidence="MEDIUM")
    if not evidence_refs and current_agent not in {"friendly_counselor_agent", "counselor_agent"}:
        return ReviewResult(
            status=ReviewStatus.NEED_MORE_EVIDENCE,
            reason="evidence_refs is empty",
            missing_evidence_query=str(draft_answer or current_task or ""),
            target_agent=current_agent,
            confidence="HIGH",
        )
    if claims and not _claims_have_evidence(claims):
        return ReviewResult(
            status=ReviewStatus.REVISION_REQUIRED,
            reason="one or more claims are not tied to evidence_ids or graph_context_ids",
            target_agent=current_agent,
            confidence="HIGH",
        )
    if _needs_graph_context(current_task, current_agent) and not graph_context:
        return ReviewResult(
            status=ReviewStatus.NEED_GRAPH_CONTEXT,
            reason="graph_context is required for this task but empty",
            graph_context_query=str(current_task or draft_answer or ""),
            target_agent=current_agent,
            confidence="MEDIUM",
        )
    return ReviewResult(status=ReviewStatus.PASS, reason="structured review passed", target_agent=current_agent, confidence="MEDIUM")


def _claims_have_evidence(claims: list[Any]) -> bool:
    for claim in claims:
        data = claim if isinstance(claim, dict) else getattr(claim, "__dict__", {})
        if not data.get("evidence_ids") and not data.get("graph_context_ids"):
            return False
    return True


def _needs_graph_context(current_task: str | None, current_agent: str | None) -> bool:
    text = f"{current_task or ''} {current_agent or ''}".lower()
    return any(token in text for token in ["ownership", "registry", "legal_basis", "insurance", "market"])


def _review_prompt(
    current_task: str | None,
    current_agent: str | None,
    claims: list[Any],
    evidence_refs: list[dict[str, Any]],
    graph_context: list[Any],
    draft_answer: str | None,
    mode: str,
) -> str:
    return f"""
You are the v7 Review Supervisor. Return only the structured ReviewResult schema.

Rules:
- PASS only when claims are grounded in evidence_refs or graph_context.
- NEED_MORE_EVIDENCE when evidence_refs are empty or insufficient.
- NEED_GRAPH_CONTEXT when relationship validation is needed but graph_context is empty.
- REVISION_REQUIRED when claims conflict with evidence or are not grounded.
- NEED_COUNSELOR_REWRITE only when legal basis is valid but expression needs counseling rewrite.
- FAIL for unrecoverable malformed output.

mode: {mode}
current_task: {current_task}
current_agent: {current_agent}
claims: {json.dumps(_jsonable(claims), ensure_ascii=False, default=str)[:6000]}
evidence_count: {len(evidence_refs)}
graph_context_count: {len(graph_context)}
draft_answer: {(draft_answer or '')[:2000]}
""".strip()


def _to_dataclass(model: ReviewResultModel) -> ReviewResult:
    return ReviewResult(
        status=model.status,
        reason=model.reason,
        required_action=model.required_action,
        missing_evidence_query=model.missing_evidence_query,
        graph_context_query=model.graph_context_query,
        target_agent=model.target_agent,
        confidence=model.confidence,
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return value
