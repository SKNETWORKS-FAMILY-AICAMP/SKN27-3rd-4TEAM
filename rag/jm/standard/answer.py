# rag/jm/standard/answer.py
# DB/RAG 검색 없이 LLM만 사용해 일반적인 전세 관련 질문에 답변합니다.

from __future__ import annotations

from dataclasses import dataclass

import requests
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

try:
    from .config import load_config
except ImportError:
    from config import load_config


@dataclass(frozen=True)
class StandardAnswerResult:
    """표준 LLM 답변 결과입니다."""

    question: str
    answer: str
    provider: str
    model: str


def _system_prompt() -> str:
    """일반 전세 상담 답변에 사용할 기본 시스템 프롬프트를 반환합니다."""

    return (
        "당신은 전세 계약, 특약, 임대차 기초 지식, 전세사기 예방을 쉽게 설명하는 상담 보조자입니다.\n"
        "DB 조회나 RAG 문서 검색 없이 일반 지식 기반으로 답변합니다.\n"
        "사용자가 이해하기 쉽게 핵심부터 설명하고, 필요한 경우 체크리스트 형태로 정리하세요.\n"
        "법률적 판단을 단정하지 말고, 실제 계약 전에는 등기부등본, 확정일자, 전입신고, 보증보험 가능 여부, "
        "공인중개사/법률 전문가 확인이 필요하다고 안내하세요.\n"
        "모르는 내용을 꾸며내지 말고, 추가 확인이 필요하다고 말하세요."
    )


def _answer_with_openai(question: str) -> str:
    """OpenAI 채팅 모델로 표준 답변을 생성합니다."""

    cfg = load_config()
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _system_prompt()),
            ("human", "{question}"),
        ]
    )
    chain = prompt | ChatOpenAI(model=cfg.llm_model, temperature=0.2) | StrOutputParser()
    return chain.invoke({"question": question})


def _answer_with_ollama(question: str) -> str:
    """Ollama 로컬 모델로 표준 답변을 생성합니다."""

    cfg = load_config()
    prompt = f"{_system_prompt()}\n\n[질문]\n{question}"
    response = requests.post(
        f"{cfg.ollama_base_url.rstrip('/')}/api/generate",
        json={"model": cfg.llm_model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def answer_standard_question(question: str) -> StandardAnswerResult:
    """사용자 일반 질문에 대해 DB/RAG 없이 LLM 단독 답변을 생성합니다."""

    cfg = load_config()
    if cfg.llm_provider == "ollama":
        answer = _answer_with_ollama(question)
    else:
        answer = _answer_with_openai(question)

    return StandardAnswerResult(
        question=question,
        answer=answer,
        provider=cfg.llm_provider,
        model=cfg.llm_model,
    )

