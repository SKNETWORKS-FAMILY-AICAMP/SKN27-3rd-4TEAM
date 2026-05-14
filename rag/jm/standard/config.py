# rag/jm/standard/config.py
# standard 모듈 단독 실행에 필요한 환경변수 설정을 관리합니다.

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class StandardConfig:
    """standard 답변 생성에 필요한 설정값입니다."""

    llm_provider: str
    llm_model: str
    ollama_base_url: str


def load_config() -> StandardConfig:
    """환경변수에서 standard 모듈 설정을 읽어옵니다."""

    return StandardConfig(
        llm_provider=os.getenv("STANDARD_LLM_PROVIDER", os.getenv("RAG_LLM_PROVIDER", "openai")).lower(),
        llm_model=os.getenv("STANDARD_LLM_MODEL", os.getenv("RAG_LLM_MODEL", "gpt-4o-mini")),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )

