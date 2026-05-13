"""LangGraph nodes for legal consultation."""
from __future__ import annotations

from typing import Any

from common.agents.counselor_agent import run_counselor_agent
from common.agents.legal_guardrail_agent import run_legal_guardrail_agent
from common.agents.legal_rag_agent import run_legal_rag_agent
from common.agents.legal_supervisor_agent import run_legal_supervisor_agent
from common.schemas.legal_consultation_schema import LegalRoute
from common.states.legal_consultation_state import LegalConsultationState
from common.tools.llm import LLMUnavailable


def legal_intake_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = _base_state(state)
    question = (next_state.get("user_question") or "").strip()
    if not question:
        next_state.update(
            {
                "intent": "CLARIFICATION_NEEDED",
                "route": "CLARIFICATION",
                "needs_clarification": True,
                "clarification_questions": ["상담할 내용을 조금 더 자세히 알려주세요."],
                "draft_answer": "상담할 내용을 조금 더 자세히 알려주세요.",
                "supervisor_status": "INTAKE_EMPTY",
            }
        )
    else:
        next_state["user_question"] = question
    next_state["agent_trace"].append({"node": "legal_intake", "has_question": bool(question)})
    return next_state


def legal_supervisor_node(state: LegalConsultationState) -> LegalConsultationState:
    if state.get("supervisor_status") == "INTAKE_EMPTY":
        return state
    next_state = dict(state)
    try:
        decision = run_legal_supervisor_agent(
            next_state["user_question"],
            next_state.get("conversation_history", []),
        )
    except LLMUnavailable as exc:
        next_state.setdefault("errors", []).append(str(exc))
        next_state["supervisor_status"] = "LLM_REQUIRED_UNAVAILABLE"
        next_state["route"] = "CLARIFICATION"
        next_state["needs_clarification"] = True
        next_state["clarification_questions"] = ["현재 법률상담 LLM 라우팅이 불가능합니다. 잠시 후 다시 시도해주세요."]
        next_state["agent_trace"].append({"node": "legal_supervisor", "status": "failed", "error": str(exc)})
        return next_state

    next_state.update(
        {
            "intent": decision.intent.value,
            "route": decision.route.value,
            "question_type": decision.question_type.value,
            "needs_rag": decision.needs_rag,
            "needs_clarification": decision.needs_clarification,
            "clarification_questions": decision.clarification_questions,
            "reason": decision.reason,
            "supervisor_status": "COMPLETE",
        }
    )
    next_state["agent_trace"].append({"node": "legal_supervisor", "decision": decision.model_dump()})
    return next_state


def legal_rag_agent_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = dict(state)
    try:
        result = run_legal_rag_agent(
            next_state.get("user_question", ""),
            next_state.get("question_type"),
        )
    except LLMUnavailable as exc:
        next_state.setdefault("errors", []).append(str(exc))
        next_state["legal_rag_result"] = {
            "llm_used": False,
            "rag_status": "AGENT_UNAVAILABLE",
            "blocked_reason": str(exc),
            "evidence_refs": [],
        }
        next_state["agent_trace"].append({"node": "legal_rag_agent", "status": "failed", "error": str(exc)})
        return next_state

    dumped = result.model_dump()
    next_state["legal_rag_result"] = dumped
    next_state["evidence_refs"] = dumped.get("evidence_refs", [])
    if dumped.get("rag_status") == "RAG_OK":
        next_state["draft_answer"] = dumped.get("answer_draft", "")
    else:
        next_state["draft_answer"] = (
            "현재 법령·판례·공공기관 근거를 안정적으로 확인하지 못해 "
            "이 질문에 대한 법률 판단이나 절차 안내를 제공하지 않겠습니다. "
            "RAG 근거 재구축 후 다시 확인해야 합니다."
        )
    next_state["agent_trace"].append(
        {
            "node": "legal_rag_agent",
            "question_type": next_state.get("question_type"),
            "rag_status": dumped.get("rag_status"),
            "llm_used": dumped.get("llm_used"),
        }
    )
    return next_state


def counselor_agent_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = dict(state)
    try:
        result = run_counselor_agent(
            user_question=next_state.get("user_question", ""),
            intent=next_state.get("intent"),
            question_type=next_state.get("question_type"),
            legal_rag_result=next_state.get("legal_rag_result"),
            clarification_questions=next_state.get("clarification_questions", []),
            conversation_history=next_state.get("conversation_history", []),
        )
    except LLMUnavailable as exc:
        next_state.setdefault("errors", []).append(str(exc))
        next_state["counselor_result"] = {"llm_used": False, "blocked_reason": str(exc)}
        next_state["agent_trace"].append({"node": "counselor_agent", "status": "failed", "error": str(exc)})
        return next_state

    dumped = result.model_dump()
    next_state["counselor_result"] = dumped
    next_state["draft_answer"] = dumped.get("answer", "")
    if dumped.get("followup_questions"):
        next_state["clarification_questions"] = dumped["followup_questions"]
    next_state["agent_trace"].append({"node": "counselor_agent", "intent": next_state.get("intent"), "llm_used": dumped.get("llm_used")})
    return next_state


def legal_guardrail_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = dict(state)
    draft = next_state.get("draft_answer", "")
    if not draft:
        next_state.setdefault("errors", []).append("legal guardrail blocked: draft_answer is empty")
        next_state["safe_answer"] = ""
        next_state["agent_trace"].append({"node": "legal_guardrail", "status": "blocked", "reason": "empty draft"})
        return next_state
    try:
        result = run_legal_guardrail_agent(
            draft_answer=draft,
            evidence_refs=next_state.get("evidence_refs", []),
            question_type=next_state.get("question_type"),
        )
    except LLMUnavailable as exc:
        next_state.setdefault("errors", []).append(str(exc))
        next_state["safe_answer"] = ""
        next_state["agent_trace"].append({"node": "legal_guardrail", "status": "failed", "error": str(exc)})
        return next_state

    dumped = result.model_dump()
    next_state["safe_answer"] = dumped.get("safe_answer", "")
    next_state["agent_trace"].append({"node": "legal_guardrail", "checked": True, "llm_used": dumped.get("llm_used"), "warnings": dumped.get("warnings", [])})
    return next_state


def consultation_report_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = dict(state)
    complete, blocked_reasons = _completion_status(next_state)
    next_state["report"] = {
        "answer": next_state.get("safe_answer") or next_state.get("draft_answer", ""),
        "status": {
            "complete": complete,
            "blocked_reasons": blocked_reasons,
            "fallback_policy": "LLM-backed agent output is required. Fallbacks are not treated as final legal consultation.",
        },
        "intent": next_state.get("intent"),
        "route": next_state.get("route"),
        "question_type": next_state.get("question_type"),
        "needs_rag": next_state.get("needs_rag"),
        "needs_clarification": next_state.get("needs_clarification", False),
        "evidence_refs": next_state.get("evidence_refs", []),
        "followup_questions": next_state.get("clarification_questions", []),
        "legal_rag_result": next_state.get("legal_rag_result", {}),
        "counselor_result": next_state.get("counselor_result", {}),
        "agent_trace": next_state.get("agent_trace", []),
        "errors": next_state.get("errors", []),
    }
    next_state["agent_trace"].append({"node": "consultation_report", "complete": complete})
    return next_state


def route_after_legal_supervisor(state: LegalConsultationState) -> str:
    route = state.get("route")
    if route == LegalRoute.LEGAL_RAG.value:
        return "legal_rag_agent"
    if route == LegalRoute.BOTH.value:
        return "legal_rag_agent"
    return "counselor_agent"


def route_after_legal_rag(state: LegalConsultationState) -> str:
    if state.get("legal_rag_result", {}).get("rag_status") != "RAG_OK":
        return "legal_guardrail"
    if state.get("route") == LegalRoute.BOTH.value:
        return "counselor_agent"
    return "legal_guardrail"


def _base_state(state: LegalConsultationState) -> LegalConsultationState:
    next_state = dict(state)
    next_state.setdefault("agent_trace", [])
    next_state.setdefault("errors", [])
    next_state.setdefault("conversation_history", [])
    next_state.setdefault("evidence_refs", [])
    return next_state


def _completion_status(state: LegalConsultationState) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if state.get("supervisor_status") not in {"COMPLETE", "INTAKE_EMPTY"}:
        reasons.append("legal supervisor LLM result is unavailable")
    if state.get("route") in {LegalRoute.LEGAL_RAG.value, LegalRoute.BOTH.value}:
        rag = state.get("legal_rag_result", {})
        if rag.get("rag_status") != "RAG_OK":
            reasons.append(f"legal RAG evidence is not reliable: {rag.get('rag_status')}")
        elif not rag.get("llm_used"):
            reasons.append("legal RAG agent LLM result is unavailable")
    if state.get("route") in {LegalRoute.COUNSELOR.value, LegalRoute.BOTH.value, LegalRoute.CLARIFICATION.value}:
        counselor = state.get("counselor_result", {})
        if not counselor.get("llm_used"):
            reasons.append("counselor agent LLM result is unavailable")
    if state.get("draft_answer") and not state.get("safe_answer"):
        reasons.append("legal guardrail LLM result is unavailable")
    if state.get("errors"):
        reasons.extend(state.get("errors", []))
    return not reasons, reasons
