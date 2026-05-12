"""Defense simulation graph schemas."""
from __future__ import annotations

from typing import Any, Literal, TypedDict

from common.schemas.shared import AgentTrace

InputType = Literal["ACTION", "COMMAND"]
StageStatus = Literal["READY", "COMMAND", "STAGE_CLEAR", "STAGE_FAILED", "GAME_OVER", "COMPLETED"]
GameStatus = Literal["PLAYING", "GAME_OVER", "COMPLETED"]


class DefenseSimulationState(TypedDict, total=False):
    session_id: str
    category_id: str
    current_stage_index: int
    user_message: str

    campaign: dict[str, Any]
    current_stage: dict[str, Any]
    roleplay_message: str
    conversation_history: list[dict[str, str]]

    input_type: InputType
    command: str | None
    command_response: str | None
    hint_used_count: int

    interpreted_actions: list[str]
    intent_summary: str
    normalized_user_action: str
    unsafe_behavior: bool
    unsafe_reason: str | None
    abusive_language: bool
    abusive_reason: str | None
    dangerous_acceptance: bool
    interpretation_confidence: float
    interpretation_method: str
    detected_defenses: list[dict[str, Any]]
    missed_defenses: list[dict[str, Any]]
    dangerous_actions: list[str]

    stage_status: StageStatus
    game_status: GameStatus
    risk_exposure: int
    failed_stage_count: int
    defense_score: int
    game_over_reason: str | None
    ending_type: str | None

    evidence_report: dict[str, Any]
    feedback: str
    narrative_feedback: str
    report: dict[str, Any]
    agent_trace: list[AgentTrace]
    errors: list[str]
