"""LLM/ReAct agents used by the legal consultation graph."""
from __future__ import annotations

from common.agents.react_agent_factory import invoke_react_agent
from common.tools.adaptive_rag import adaptive_rag_tool
from common.tools.external_search import search_external_sources_tool
from common.tools.llm import extract_json_object, ollama_generate

LEGAL_QUESTION_TYPES = {
    "SPECIAL_CLAUSE",
    "DEPOSIT_RETURN",
    "OPPOSING_POWER",
    "PREFERRED_PAYMENT",
    "REGISTRY_RISK",
    "SENIOR_TENANT",
    "TRUST_REGISTRATION",
    "TAX_ARREARS",
    "JEONSE_FRAUD_CASE",
    "GENERAL_LEGAL_INFO",
    "UNKNOWN",
}


def run_legal_case_retriever_agent(question_type: str | None, query: str) -> str | None:
    """Retrieve and summarize internal case evidence with a ReAct agent."""
    return invoke_react_agent(
        name="legal_case_retriever_react_agent",
        system_prompt=(
            "너는 전세계약 법률 상담을 위한 판례 검색 ReAct Agent다. "
            "반드시 adaptive_rag_tool을 사용해 내부 판례/판결문 근거를 찾고, "
            "사용자 질문과 관련 있는 판례 쟁점을 요약한다."
        ),
        user_prompt=f"질문 유형: {question_type}\n질문: {query[:2500]}",
        tools=[adaptive_rag_tool],
        temperature=0.1,
    )


def run_legal_law_guide_retriever_agent(question_type: str | None, query: str) -> str | None:
    """Retrieve and summarize law/guide evidence with a ReAct agent."""
    return invoke_react_agent(
        name="legal_law_guide_retriever_react_agent",
        system_prompt=(
            "너는 전세계약 법률/가이드 검색 ReAct Agent다. "
            "반드시 adaptive_rag_tool을 사용해 법령, 공공 가이드, 체크리스트 근거를 찾고, "
            "사용자 질문에 필요한 확인사항을 요약한다."
        ),
        user_prompt=f"질문 유형: {question_type}\n질문: {query[:2500]}",
        tools=[adaptive_rag_tool],
        temperature=0.1,
    )


def classify_legal_question_with_llm(question: str) -> str | None:
    """Classify a legal consultation question with an LLM."""
    raw = ollama_generate(
        "다음 전세계약 법률 질문의 유형을 JSON으로만 분류해. "
        "가능한 type: SPECIAL_CLAUSE, DEPOSIT_RETURN, OPPOSING_POWER, PREFERRED_PAYMENT, REGISTRY_RISK, SENIOR_TENANT, TRUST_REGISTRATION, TAX_ARREARS, JEONSE_FRAUD_CASE, GENERAL_LEGAL_INFO, UNKNOWN\n"
        f"질문: {question[:1500]}",
        system="너는 한국 전세계약 법률 질문 분류기다. JSON만 반환한다.",
        temperature=0.0,
    )
    data = extract_json_object(raw)
    qtype = str(data.get("type", "UNKNOWN"))
    return qtype if qtype in LEGAL_QUESTION_TYPES else None


def run_case_based_answer_react_agent(answer_prompt: str) -> str | None:
    """Draft a grounded legal information answer with a ReAct agent."""
    return invoke_react_agent(
        name="case_based_answer_react_agent",
        system_prompt=(
            "너는 전세계약 판례 근거 설명 ReAct Agent다. "
            "필요하면 adaptive_rag_tool과 search_external_sources_tool을 사용한다. "
            "답변에는 결론 요약, 근거 판례/법령, 사안 관련성, 추가 확인사항, 법률 자문 아님 고지를 포함한다. "
            "승소 가능, 무조건, 반드시 같은 단정 표현은 피한다."
        ),
        user_prompt=answer_prompt,
        tools=[adaptive_rag_tool, search_external_sources_tool],
        temperature=0.2,
    )


def generate_legal_answer_with_llm(answer_prompt: str) -> str | None:
    """Draft a grounded legal information answer with plain LLM fallback."""
    raw = ollama_generate(
        answer_prompt,
        system="너는 전세계약 판례 근거 설명 상담사다. 단정적 법률 자문은 피하고 근거 중심으로 답한다.",
        temperature=0.2,
    )
    return raw.strip() if raw.strip() else None
