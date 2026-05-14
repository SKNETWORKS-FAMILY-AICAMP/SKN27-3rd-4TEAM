# rag/jm/legal/agent.py
# 법령, 판례, 표준계약서, 절차 문서를 근거로 전세 관련 법률 상담 답변을 생성합니다.

from __future__ import annotations

from dataclasses import dataclass

import requests
from langchain_openai import ChatOpenAI

from ..core.config import load_config
from .search import LegalSearchHit, search_legal_documents


@dataclass(frozen=True)
class LegalAgentResult:
    """법률 상담 에이전트의 최종 답변과 검색 근거를 함께 담습니다."""

    answer: str
    hits: list[LegalSearchHit]
    review_passed: bool
    review_message: str


def _format_legal_hits(hits: list[LegalSearchHit]) -> str:
    """검색된 법률 RAG chunk를 LLM 프롬프트에 넣기 좋은 형태로 정리합니다."""

    lines: list[str] = []
    for idx, hit in enumerate(hits, start=1):
        source = hit.metadata.get("source") or hit.metadata.get("file_name") or "출처 미상"
        page = hit.metadata.get("page")
        page_text = f", page={page}" if page is not None else ""
        lines.append(
            f"[근거 {idx}] score={hit.score:.4f}, source={source}{page_text}\n"
            f"{hit.content}"
        )
    return "\n\n".join(lines)


def _source_summary(hits: list[LegalSearchHit]) -> str:
    """최종 답변 하단에 붙일 출처 목록을 중복 없이 만듭니다."""

    sources: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        source = str(hit.metadata.get("source") or hit.metadata.get("file_name") or "출처 미상")
        page = hit.metadata.get("page")
        item = f"{source} p.{page}" if page is not None else source
        if item not in seen:
            sources.append(item)
            seen.add(item)
    return "\n".join(f"- {source}" for source in sources[:8])


def _legal_system_prompt() -> str:
    """법률 상담 에이전트가 지켜야 할 답변 원칙을 정의합니다."""

    return (
        "당신은 전세사기 방지 프로젝트의 legal_agent입니다. "
        "반드시 제공된 법령, 판례, 표준계약서, 법률 절차 문서 근거만 사용해 답변하세요. "
        "일반 예방 사례집, 부동산 거래 테이블, 감정 상담 데이터는 사용하지 마세요. "
        "답변은 한국어로 작성하고, 단정적인 법률 판단 대신 확인해야 할 조건과 다음 행동을 제시하세요. "
        "근거가 부족하면 부족하다고 말하고 추가 확인이 필요한 항목을 분명히 적으세요."
    )


def _draft_with_openai(question: str, context: str) -> str:
    """OpenAI 채팅 모델로 법률 상담 답변 초안을 생성합니다."""

    cfg = load_config()
    llm = ChatOpenAI(model=cfg.llm_model, temperature=0.2)
    messages = [
        ("system", _legal_system_prompt()),
        (
            "human",
            "사용자 질문:\n"
            f"{question}\n\n"
            "검색된 법률 RAG 근거:\n"
            f"{context}\n\n"
            "위 근거만 바탕으로 법률 상담 답변 초안을 작성해줘.",
        ),
    ]
    return str(llm.invoke(messages).content)


def _draft_with_ollama(question: str, context: str) -> str:
    """Ollama 로컬 모델로 법률 상담 답변 초안을 생성합니다."""

    cfg = load_config()
    prompt = (
        f"{_legal_system_prompt()}\n\n"
        f"사용자 질문:\n{question}\n\n"
        f"검색된 법률 RAG 근거:\n{context}\n\n"
        "위 근거만 바탕으로 법률 상담 답변 초안을 작성해줘."
    )
    response = requests.post(
        f"{cfg.ollama_base_url.rstrip('/')}/api/generate",
        json={"model": cfg.llm_model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return str(response.json().get("response", "")).strip()


def _draft_answer(question: str, hits: list[LegalSearchHit]) -> str:
    """설정된 LLM 제공자에 맞춰 법률 답변 초안을 생성합니다."""

    context = _format_legal_hits(hits)
    cfg = load_config()
    if cfg.llm_provider == "ollama":
        return _draft_with_ollama(question, context)
    return _draft_with_openai(question, context)


def _review_answer(answer: str, hits: list[LegalSearchHit]) -> tuple[bool, str]:
    """답변이 최소한의 법률 상담 품질 기준을 만족하는지 점검합니다."""

    if not hits:
        return False, "법률 RAG 검색 결과가 없습니다."
    if len(answer.strip()) < 80:
        return False, "답변 길이가 너무 짧아 근거 설명이 부족합니다."
    if not any(keyword in answer for keyword in ("근거", "확인", "계약", "법", "판례", "절차")):
        return False, "법률 근거 또는 확인 사항이 답변에 충분히 드러나지 않았습니다."
    return True, "PASS"


def _finalize_answer(answer: str, hits: list[LegalSearchHit], review_message: str) -> str:
    """답변 본문에 출처와 법률 자문 한계를 붙여 최종 답변으로 정리합니다."""

    source_text = _source_summary(hits)
    return (
        f"{answer.strip()}\n\n"
        "참고한 법률 RAG 문서:\n"
        f"{source_text if source_text else '- 검색된 법률 RAG 문서 없음'}\n\n"
        "주의: 이 답변은 DB에 적재된 법률 관련 문서 기반의 상담 보조 결과이며, "
        "최종 법률 판단은 변호사 또는 공공 법률 상담 기관에 확인해야 합니다.\n"
        f"검토 결과: {review_message}"
    )


def run_legal_agent(question: str, k: int = 5) -> LegalAgentResult:
    """법률 RAG 검색과 답변 검토를 순서대로 실행합니다."""

    hits = search_legal_documents(question, k=k, scope="all")
    answer = _draft_answer(question, hits)
    passed, message = _review_answer(answer, hits)

    if not passed:
        extra_hits = search_legal_documents(
            f"{question}\n법령 판례 표준계약서 절차",
            k=max(k * 2, 8),
            scope="all",
        )
        if len(extra_hits) > len(hits):
            hits = extra_hits
            answer = _draft_answer(question, hits)
            passed, message = _review_answer(answer, hits)

    final_answer = _finalize_answer(answer, hits, message)
    return LegalAgentResult(
        answer=final_answer,
        hits=hits,
        review_passed=passed,
        review_message=message,
    )
