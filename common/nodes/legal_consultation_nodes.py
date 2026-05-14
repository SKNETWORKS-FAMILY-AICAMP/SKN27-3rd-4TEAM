"""v7 LangGraph nodes for legal consultation."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from common.agents.counselor_agent import run_counselor_agent
from common.agents.legal_guardrail_agent import run_legal_guardrail_agent
from common.agents.legal_rag_agent import run_legal_rag_agent
from common.agents.legal_supervisor_agent import run_legal_supervisor_agent
from common.agents.review_supervisor_agent import review_agent_output
from common.schemas.legal_consultation_schema import LegalRoute
from common.schemas.shared import ReviewStatus
from common.states.legal_consultation_state import LegalConsultationState
from common.tools.legal_rag_tools import search_legal_rag
from common.tools.llm import LLMUnavailable
from common.tools.v7_contracts import merge_evidence_refs, parse_graph_context


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
    next_state = _base_state(state)
    try:
        decision = run_legal_supervisor_agent(next_state["user_question"], next_state.get("conversation_history", []))
    except LLMUnavailable as exc:
        next_state.setdefault("errors", []).append(str(exc))
        next_state.update(
            {
                "supervisor_status": "LLM_REQUIRED_UNAVAILABLE",
                "route": "CLARIFICATION",
                "needs_clarification": True,
                "clarification_questions": ["현재 법률상담 LLM 라우팅이 불가능합니다. 잠시 후 다시 시도해주세요."],
            }
        )
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
            "current_task": "legal_consultation",
        }
    )
    if decision.route.value in {LegalRoute.LEGAL_RAG.value, LegalRoute.BOTH.value}:
        next_state["current_agent"] = "legal_rag_agent"
    else:
        next_state["current_agent"] = "friendly_counselor_agent"
    next_state["agent_trace"].append({"node": "legal_supervisor", "decision": decision.model_dump()})
    return next_state


def legal_rag_agent_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = _base_state(state)
    try:
        result = run_legal_rag_agent(next_state.get("user_question", ""), next_state.get("question_type"))
    except LLMUnavailable as exc:
        next_state.setdefault("errors", []).append(str(exc))
        dumped = {"llm_used": False, "rag_status": "AGENT_UNAVAILABLE", "blocked_reason": str(exc), "evidence_refs": [], "claims": [], "graph_context": []}
        next_state["legal_rag_result"] = dumped
        next_state["agent_trace"].append({"node": "legal_rag_agent", "status": "failed", "error": str(exc)})
        return next_state

    dumped = result.model_dump()
    next_state["legal_rag_result"] = dumped
    next_state["claims"] = dumped.get("claims", [])
    next_state["legal_points"] = dumped.get("legal_points", [])
    next_state["evidence_refs"] = dumped.get("evidence_refs", [])
    next_state["graph_context"] = dumped.get("graph_context", [])
    next_state["draft_answer"] = dumped.get("answer_draft", "") if dumped.get("rag_status") == "RAG_OK" else (
        "현재 법령·판례·공공기관 근거를 안정적으로 확인하지 못해 이 질문에 대한 법률 판단이나 절차 안내를 제공하지 않겠습니다."
    )
    next_state["current_agent"] = "legal_rag_agent"
    next_state["agent_trace"].append({"node": "legal_rag_agent", "question_type": next_state.get("question_type"), "rag_status": dumped.get("rag_status"), "llm_used": dumped.get("llm_used")})
    return next_state


def counselor_agent_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = _base_state(state)
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
        next_state["agent_trace"].append({"node": "friendly_counselor_agent", "status": "failed", "error": str(exc)})
        return next_state

    dumped = result.model_dump()
    next_state["counselor_result"] = dumped
    next_state["draft_answer"] = dumped.get("answer", "")
    if dumped.get("followup_questions"):
        next_state["clarification_questions"] = dumped["followup_questions"]
    next_state["current_agent"] = "friendly_counselor_agent"
    next_state["agent_trace"].append({"node": "friendly_counselor_agent", "intent": next_state.get("intent"), "llm_used": dumped.get("llm_used")})
    return next_state


def legal_review_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = _base_state(state)
    review = review_agent_output(
        current_task=next_state.get("current_task") or "legal_consultation",
        current_agent=next_state.get("current_agent"),
        claims=next_state.get("claims", []),
        evidence_refs=next_state.get("evidence_refs", []),
        graph_context=next_state.get("graph_context", []),
        draft_answer=next_state.get("draft_answer", ""),
        mode="legal_consultation",
    )
    count = int(next_state.get("review_count", 0))
    if review.status != ReviewStatus.PASS:
        count += 1
    next_state["review_result"] = asdict(review)
    next_state["review_count"] = count
    next_state["agent_trace"].append({"node": "legal_review_node", "review": asdict(review), "review_count": count})
    return next_state


def extra_legal_rag_search_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = _base_state(state)
    review = next_state.get("review_result", {})
    query = review.get("missing_evidence_query") or next_state.get("user_question", "")
    rag = search_legal_rag(query=query, question_type=next_state.get("question_type"), top_k=5, include_graph_context=True)
    additional = rag.get("results") or rag.get("references", [])
    next_state["evidence_refs"] = merge_evidence_refs(next_state.get("evidence_refs", []), additional, current_task="legal_consultation")
    next_state["graph_context"] = rag.get("graph_context", next_state.get("graph_context", []))
    if next_state.get("legal_rag_result"):
        next_state["legal_rag_result"]["evidence_refs"] = next_state["evidence_refs"]
        next_state["legal_rag_result"]["graph_context"] = next_state["graph_context"]
    next_state["agent_trace"].append({"node": "extra_legal_rag_search", "added": len(additional)})
    return next_state


def legal_graph_context_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = _base_state(state)
    rag = search_legal_rag(query=next_state.get("user_question", ""), question_type=next_state.get("question_type"), top_k=3, include_graph_context=True)
    graph_context = rag.get("graph_context", [])
    next_state["graph_context"] = graph_context or next_state.get("graph_context", [])
    if next_state.get("legal_rag_result"):
        next_state["legal_rag_result"]["graph_context"] = next_state["graph_context"]
    next_state["agent_trace"].append({"node": "legal_graph_context_node", "graph_context_count": len(next_state.get("graph_context", []))})
    return next_state


def legal_guardrail_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = _base_state(state)
    draft = next_state.get("draft_answer", "")
    if not draft:
        next_state.setdefault("errors", []).append("legal guardrail blocked: draft_answer is empty")
        next_state["safe_answer"] = ""
        next_state["agent_trace"].append({"node": "legal_guardrail", "status": "blocked", "reason": "empty draft"})
        return next_state
    try:
        result = run_legal_guardrail_agent(draft_answer=draft, evidence_refs=next_state.get("evidence_refs", []), question_type=next_state.get("question_type"))
    except LLMUnavailable as exc:
        next_state.setdefault("errors", []).append(str(exc))
        next_state["safe_answer"] = ""
        next_state["agent_trace"].append({"node": "legal_guardrail", "status": "failed", "error": str(exc)})
        return next_state

    dumped = result.model_dump()
    next_state["safe_answer"] = dumped.get("safe_answer", "")
    next_state["agent_trace"].append({"node": "legal_guardrail", "checked": True, "llm_used": dumped.get("llm_used"), "warnings": dumped.get("warnings", []), "immutable_fields_preserved": ["claims", "evidence_refs", "graph_context"]})
    return next_state


def safe_legal_fallback_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = _base_state(state)
    level = "HIGH" if next_state.get("route") in {LegalRoute.LEGAL_RAG.value, LegalRoute.BOTH.value} else "LOW"
    next_state["fallback_level"] = level
    next_state["safe_fallback"] = {
        "status": "SAFE_FALLBACK",
        "fallback_level": level,
        "reason": next_state.get("review_result", {}).get("reason", "review could not pass safely"),
        "recommended_next_step": _fallback_next_step(level),
        "task": next_state.get("current_task") or "legal_consultation",
    }
    next_state["draft_answer"] = "근거 검증이 충분하지 않아 확정적인 법률 판단을 제공하지 않습니다. 추가 자료 확인 또는 전문가 상담을 권장합니다."
    next_state["agent_trace"].append({"node": "safe_legal_fallback", **next_state["safe_fallback"]})
    return next_state


def consultation_report_node(state: LegalConsultationState) -> LegalConsultationState:
    next_state = _base_state(state)
    complete, blocked_reasons = _completion_status(next_state)
    next_state["report"] = {
        "answer": next_state.get("safe_answer") or next_state.get("draft_answer", ""),
        "status": {
            "complete": complete,
            "blocked_reasons": blocked_reasons,
            "fallback_level": next_state.get("fallback_level"),
            "fallback_policy": "SAFE_FALLBACK is used when review cannot pass.",
        },
        "safe_fallback": next_state.get("safe_fallback", {}),
        "intent": next_state.get("intent"),
        "route": next_state.get("route"),
        "question_type": next_state.get("question_type"),
        "needs_rag": next_state.get("needs_rag"),
        "needs_clarification": next_state.get("needs_clarification", False),
        "claims": next_state.get("claims", []),
        "legal_points": next_state.get("legal_points", []),
        "evidence_refs": next_state.get("evidence_refs", []),
        "graph_context": next_state.get("graph_context", []),
        "followup_questions": next_state.get("clarification_questions", []),
        "legal_rag_result": next_state.get("legal_rag_result", {}),
        "counselor_result": next_state.get("counselor_result", {}),
        "review_result": next_state.get("review_result", {}),
        "agent_trace": next_state.get("agent_trace", []),
        "errors": next_state.get("errors", []),
    }
    next_state["agent_trace"].append({"node": "consultation_report", "complete": complete})
    return next_state


def route_after_legal_supervisor(state: LegalConsultationState) -> str:
    route = state.get("route")
    if route in {LegalRoute.LEGAL_RAG.value, LegalRoute.BOTH.value}:
        return "legal_rag_agent"
    return "friendly_counselor_agent"


def route_after_legal_rag(state: LegalConsultationState) -> str:
    if state.get("route") == LegalRoute.BOTH.value and state.get("legal_rag_result", {}).get("rag_status") == "RAG_OK":
        return "friendly_counselor_agent"
    return "legal_review_node"


def route_after_legal_review(state: LegalConsultationState) -> str:
    review = state.get("review_result", {})
    status = review.get("status")
    if status == ReviewStatus.PASS.value:
        return "legal_guardrail"
    if int(state.get("review_count", 0)) >= int(state.get("max_review_count", 2)):
        return "safe_fallback"
    if status == ReviewStatus.NEED_MORE_EVIDENCE.value:
        return "extra_rag_search"
    if status == ReviewStatus.NEED_GRAPH_CONTEXT.value:
        return "graph_context_node"
    if status == ReviewStatus.NEED_COUNSELOR_REWRITE.value:
        return "friendly_counselor_agent"
    if status == ReviewStatus.REVISION_REQUIRED.value:
        return state.get("current_agent") or "safe_fallback"
    return "safe_fallback"


def route_after_extra_legal_rag(state: LegalConsultationState) -> str:
    return "legal_rag_agent"


def route_after_legal_graph_context(state: LegalConsultationState) -> str:
    return "legal_rag_agent"


def _base_state(state: LegalConsultationState) -> LegalConsultationState:
    next_state = dict(state)
    next_state.setdefault("agent_trace", [])
    next_state.setdefault("errors", [])
    next_state.setdefault("conversation_history", [])
    next_state.setdefault("evidence_refs", [])
    next_state.setdefault("claims", [])
    next_state.setdefault("legal_points", [])
    next_state.setdefault("graph_context", [])
    next_state.setdefault("review_count", 0)
    next_state.setdefault("max_review_count", 2)
    next_state.setdefault("safe_fallback", {})
    return next_state


def _fallback_next_step(level: str) -> str:
    if level == "HIGH":
        return "근거 검증이 부족하므로 확정적 법률 판단 대신 추가 자료 확인 또는 전문가 상담을 권장합니다."
    if level == "MEDIUM":
        return "핵심 근거를 보완한 뒤 같은 질문을 다시 검토해야 합니다."
    return "답변 신뢰도를 높이기 위해 추가 사실관계를 확인해야 합니다."


def _completion_status(state: LegalConsultationState) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if state.get("supervisor_status") not in {"COMPLETE", "INTAKE_EMPTY"}:
        reasons.append("legal supervisor LLM result is unavailable")
    if state.get("fallback_level"):
        reasons.append(f"safe fallback used: {state.get('fallback_level')}")
    if state.get("draft_answer") and not state.get("safe_answer"):
        reasons.append("legal guardrail LLM result is unavailable")
    if state.get("errors"):
        reasons.extend(state.get("errors", []))
    return not reasons, reasons
