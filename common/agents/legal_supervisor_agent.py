"""LLM supervisor for legal consultation routing."""
from __future__ import annotations

from typing import Any

from common.schemas.legal_consultation_schema import LegalIntent, LegalQuestionType, LegalRoute, LegalSupervisorDecision
from common.tools.llm import LLMUnavailable, build_chat_llm


SUPERVISOR_PROMPT = """
너는 부동산 임대차 법률상담 AI의 Supervisor다.

사용자 질문을 보고 라우팅하라.

COUNSELOR:
- 일반 설명
- 감정적 응대
- 쉬운 개념 설명
- 추가 질문 필요

LEGAL_RAG:
- 법령, 판례, 공공기관 가이드 근거가 필요한 질문
- 절차 안내가 필요한 질문

BOTH:
- 법률 근거도 필요하고 사용자가 이해하기 쉬운 상담 말투도 필요한 질문

CLARIFICATION:
- 질문이 비어 있거나 상담에 필요한 최소 정보가 부족한 경우

MVP question_type은 다음 중 하나만 사용한다:
DEPOSIT_RETURN, REGISTRY_RISK, DEPOSIT_INSURANCE, PROCEDURE_GUIDE, SIMPLE_EXPLANATION, GENERAL

분류 예시:
- "전입신고와 확정일자가 뭐야? 쉽게 설명해줘" -> route=BOTH, intent=SIMPLE_EXPLANATION, question_type=SIMPLE_EXPLANATION
- "보증금을 안 돌려주면 어떻게 해야 해?" -> route=BOTH, intent=LEGAL_RAG_REQUIRED, question_type=DEPOSIT_RETURN
- "등기부에 근저당이 있는데 위험해?" -> route=BOTH, intent=CASE_SPECIFIC_ADVICE, question_type=REGISTRY_RISK
- "HUG 보증보험 가입 가능해?" -> route=LEGAL_RAG, intent=LEGAL_RAG_REQUIRED, question_type=DEPOSIT_INSURANCE
- "내용증명 보내는 절차 알려줘" -> route=LEGAL_RAG, intent=LEGAL_RAG_REQUIRED, question_type=PROCEDURE_GUIDE
- 임대차 법률 용어(대항력, 확정일자, 전입신고, 우선변제권, 임차권등기명령 등)를 설명하는 질문은 쉬운 설명이더라도 BOTH로 보낸다.
- 질문이 너무 짧거나 비어 있어 사실관계를 알 수 없는 경우만 CLARIFICATION을 사용한다.

반드시 스키마에 맞춰 구조화된 결과를 반환한다.
""".strip()


def run_legal_supervisor_agent(user_question: str, conversation_history: list[dict[str, str]] | None = None) -> LegalSupervisorDecision:
    try:
        llm = build_chat_llm(temperature=0.0)
        structured_llm = llm.with_structured_output(LegalSupervisorDecision)
        decision = structured_llm.invoke(
            [
                ("system", SUPERVISOR_PROMPT),
                (
                    "human",
                    "사용자 질문과 대화 기록을 보고 라우팅 결정을 내려줘.\n"
                    f"user_question: {user_question}\n"
                    f"conversation_history: {conversation_history or []}",
                ),
            ]
        )
    except Exception as exc:
        return _deterministic_decision(user_question, reason=f"structured LLM unavailable: {exc}")
    if not isinstance(decision, LegalSupervisorDecision):
        raise LLMUnavailable("legal supervisor returned invalid structured output")
    return decision


def _deterministic_decision(user_question: str, *, reason: str) -> LegalSupervisorDecision:
    text = user_question or ""
    if not text.strip():
        return LegalSupervisorDecision(
            intent=LegalIntent.CLARIFICATION_NEEDED,
            route=LegalRoute.CLARIFICATION,
            question_type=LegalQuestionType.GENERAL,
            needs_clarification=True,
            clarification_questions=["상담할 내용을 조금 더 자세히 알려주세요."],
            reason=reason,
        )
    if any(token in text for token in ["근저당", "등기", "가압류", "신탁", "소유자"]):
        qtype = LegalQuestionType.REGISTRY_RISK
    elif any(token in text for token in ["보증보험", "HUG", "HF", "SGI"]):
        qtype = LegalQuestionType.DEPOSIT_INSURANCE
    elif any(token in text for token in ["내용증명", "임차권등기", "지급명령", "소송", "절차"]):
        qtype = LegalQuestionType.PROCEDURE_GUIDE
    elif any(token in text for token in ["보증금", "반환", "못 돌려"]):
        qtype = LegalQuestionType.DEPOSIT_RETURN
    elif any(token in text for token in ["뭐야", "쉽게", "설명", "대항력", "확정일자", "전입신고"]):
        qtype = LegalQuestionType.SIMPLE_EXPLANATION
    else:
        qtype = LegalQuestionType.GENERAL
    route = LegalRoute.BOTH if qtype != LegalQuestionType.GENERAL else LegalRoute.COUNSELOR
    intent = LegalIntent.SIMPLE_EXPLANATION if qtype == LegalQuestionType.SIMPLE_EXPLANATION else LegalIntent.LEGAL_RAG_REQUIRED
    return LegalSupervisorDecision(
        intent=intent,
        route=route,
        question_type=qtype,
        needs_rag=route in {LegalRoute.LEGAL_RAG, LegalRoute.BOTH},
        needs_clarification=False,
        clarification_questions=[],
        reason=reason,
    )
