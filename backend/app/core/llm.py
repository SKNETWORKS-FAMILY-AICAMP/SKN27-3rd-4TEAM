"""
전세계약 위험 진단 에이전트 - OpenAI LLM 클라이언트
역할: LLM 호출 공통 유틸리티 (LangSmith 트레이싱 자동 적용)
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import Settings


def get_llm(settings: Settings, streaming: bool = False) -> ChatOpenAI:
    """
    LangChain ChatOpenAI 인스턴스 반환.
    LANGCHAIN_TRACING_V2 가 true면 모든 호출이 LangSmith에 자동 기록됨.
    """
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=settings.OPENAI_TEMPERATURE,
        openai_api_key=settings.OPENAI_API_KEY,
        streaming=streaming,
    )


# ── 프롬프트 템플릿 ────────────────────────────────────────

RAG_SYSTEM_PROMPT = """당신은 전세계약 위험 진단 전문 AI 에이전트입니다.
대한민국 주택임대차보호법, 민법, 공인중개사법 및 실제 전세사기 판례를 기반으로
임차인(세입자)의 권익을 보호하는 관점에서 정확하고 실용적인 답변을 제공합니다.

[컨텍스트 문서]
{context}

[답변 규칙]
1. 반드시 제공된 컨텍스트 문서에 근거하여 답변하세요.
2. 법령·판례를 인용할 때는 조문 번호와 내용을 명시하세요.
3. 위험 요소가 있을 경우 구체적인 대응 방법을 제시하세요.
4. 확실하지 않은 내용은 "공인중개사 또는 법률 전문가에게 상담하세요"라고 안내하세요.
5. 답변은 한국어로 작성하며, 전문 용어는 쉽게 풀어 설명하세요.
"""

DIAGNOSIS_SYSTEM_PROMPT = """당신은 전세계약서 위험 진단 전문 AI입니다.
제공된 계약서 내용과 참고 문서를 분석하여 위험도를 진단합니다.

[참고 법령·판례·사례]
{context}

[위험 요소 DB]
{risk_factors}

[진단 규칙]
1. 계약서에서 위험 신호(red flag)를 식별하고, 위험 요소 DB와 매핑하세요.
2. 각 위험 요소의 심각도(HIGH/MEDIUM/LOW)와 관련 법령을 명시하세요.
3. 위험 점수(0~100)를 산출하세요: 80+ 위험, 60~79 주의, 60 미만 안전.
4. 임차인 관점에서 구체적인 대응 조언을 제공하세요.
5. 반드시 JSON 형식으로 응답하세요.
"""


def build_rag_chain(settings: Settings):
    """일반 RAG 채팅 체인 반환"""
    llm = get_llm(settings)

    prompt = ChatPromptTemplate.from_messages([
        ("system", RAG_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ])

    return prompt | llm


def build_diagnosis_chain(settings: Settings):
    """계약서 진단 체인 반환"""
    llm = get_llm(settings)

    prompt = ChatPromptTemplate.from_messages([
        ("system", DIAGNOSIS_SYSTEM_PROMPT),
        ("human", "[계약서 내용]\n{contract_text}\n\n위 계약서를 진단해주세요."),
    ])

    return prompt | llm
