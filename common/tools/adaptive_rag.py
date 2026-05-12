"""Adaptive RAG boundary for multi-agent graphs.

The RAG teammate can replace this module internals later. Agent graphs should keep
calling adaptive_rag(task_type, query, filters, top_k) and consume ContextPack only.
"""
from __future__ import annotations

import os
import json
import uuid
import urllib.error
import urllib.request
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - dependency fallback for minimal runtimes
    requests = None
from langchain_core.tools import tool

from common.schemas.shared import ContextPack, RetrievedContext, RetrievalQuality

TASK_SOURCE_MAP: dict[str, list[str]] = {
    "special_clause_analysis": ["사례집", "법령", "판례", "서식"],
    "required_check_analysis": ["사례집", "법령", "서식"],
    "report_generation": ["사례집", "법령"],
    "legal_basis": ["법령", "판례", "사례집"],
    "legal_case_search": ["판례", "사례집"],
    "legal_law_guide_search": ["법령", "사례집"],
    "defense_simulation_evidence": ["사례집", "법령", "판례"],
}

_FALLBACK_CONTEXTS: dict[str, list[RetrievedContext]] = {
    "special_clause_analysis": [
        RetrievedContext(
            source_id="mock-checklist-special-clause",
            title="전세계약 특약 점검 기준",
            doc_type="checklist",
            text=(
                "임차인에게 모든 수리비를 부담시키거나, 보증금 반환 시점을 과도하게 늦추거나, "
                "대항력 확보를 방해하는 특약은 위험 신호로 본다. 임대인의 추가 담보권 설정 제한과 "
                "잔금 다음날까지 권리 변동 금지 문구를 확인한다."
            ),
            score=0.75,
        )
    ],
    "required_check_analysis": [
        RetrievedContext(
            source_id="mock-checklist-required-docs",
            title="계약 전 필수 확인 서류",
            doc_type="checklist",
            text=(
                "계약서만으로는 등기부 권리관계, 임대인과 소유자 일치 여부, 선순위 보증금, 체납 세금, "
                "위반건축물 여부를 확정할 수 없다. 해당 자료를 별도로 확인해야 한다."
            ),
            score=0.72,
        )
    ],
    "legal_case_search": [
        RetrievedContext(
            source_id="mock-internal-case-deposit-return",
            title="내부 판례 샘플: 보증금 반환 지연 특약 관련",
            doc_type="case",
            text=(
                "임대인이 다음 임차인 입주나 자금 사정을 이유로 보증금 반환을 지연할 수 있는지에 관한 "
                "분쟁에서는 계약 종료, 목적물 인도, 반환 청구 사실, 특약의 구체적 문구가 핵심 쟁점이 된다. "
                "유사 판례는 임대인의 일방적 반환 지연 주장을 제한적으로 본 사례가 있다."
            ),
            score=0.78,
            metadata={
                "court": "내부 판례 자료",
                "case_number": "RAG_CASE_SAMPLE",
                "issue": "보증금 반환 지연 특약",
            },
        )
    ],
    "legal_law_guide_search": [
        RetrievedContext(
            source_id="mock-law-housing-lease",
            title="주택임대차보호법 및 임대차 가이드",
            doc_type="law",
            text=(
                "임차인은 대항력과 우선변제권 확보를 위해 전입신고, 점유, 확정일자 등 요건을 확인해야 하며, "
                "보증금 반환 분쟁에서는 계약 종료와 목적물 반환, 반환 요구 증거가 중요하다."
            ),
            score=0.72,
            metadata={"law": "주택임대차보호법", "issue": "보증금 반환 및 임차인 보호"},
        )
    ],
    "defense_simulation_evidence": [
        RetrievedContext(
            source_id="mock-casebook-defense-simulation",
            title="전세피해 사례집 기반 방어 훈련 기준",
            doc_type="casebook",
            text=(
                "전세사기 예방 훈련에서는 등기부 직접 발급, 신탁원부 확인, 임대인 신분 및 대리권 확인, "
                "전세가율과 보증보험 가능 여부 확인, 전입신고와 확정일자 확보, 불리한 특약 수정 요구를 "
                "핵심 방어 행동으로 본다."
            ),
            score=0.73,
        )
    ],
    "report_generation": [
        RetrievedContext(
            source_id="mock-guide-report",
            title="전세계약 위험 안내 리포트 작성 기준",
            doc_type="guide",
            text="위험도는 확정적 법률 판단이 아니라 계약 전 확인을 돕는 보조 정보로 설명해야 한다.",
            score=0.7,
        )
    ],
}


def adaptive_rag(task_type: str, query: str, filters: dict | None = None, top_k: int = 5) -> ContextPack:
    provider = os.getenv("RAG_PROVIDER", "remote").lower()
    if provider == "mock":
        return _fallback_rag(task_type=task_type, query=query, top_k=top_k)

    if provider in {"remote", "server", "http"}:
        remote_pack = _remote_rag(task_type=task_type, query=query, filters=filters, top_k=top_k)
        if remote_pack is not None:
            return remote_pack
        if _mock_fallback_enabled():
            return _fallback_rag(task_type=task_type, query=query, top_k=top_k)

    return ContextPack(
        task_type=task_type,
        query=query,
        contexts=[],
        quality=RetrievalQuality(
            sufficient=False,
            score=0.0,
            reason="remote RAG unavailable; set RAG_FALLBACK_TO_MOCK=1 only for offline demos",
        ),
    )


def _remote_rag(task_type: str, query: str, filters: dict | None = None, top_k: int = 5) -> ContextPack | None:
    """Call the RAG teammate's FastAPI server and adapt references to ContextPack."""
    base_url = os.getenv("RAG_SERVER_URL", "http://localhost:8000").rstrip("/")
    timeout = float(os.getenv("RAG_SERVER_TIMEOUT", "10"))
    session_id = str((filters or {}).get("session_id") or f"lg-{uuid.uuid4().hex[:12]}")
    message = _build_remote_query(task_type=task_type, query=query, filters=filters)

    try:
        payload = _post_json(
            url=f"{base_url}/api/v1/chat/query",
            body={"session_id": session_id, "message": message, "history": []},
            timeout=timeout,
        )
    except Exception as exc:
        return _remote_failure_pack(task_type, query, exc) if _remote_strict_enabled() else None

    references = payload.get("references", [])
    contexts = [_reference_to_context(ref, i) for i, ref in enumerate(references[:top_k], 1)]
    answer = str(payload.get("answer") or "").strip()
    if answer and len(contexts) < top_k:
        contexts.insert(
            0,
            RetrievedContext(
                source_id=f"remote-rag-answer-{session_id}",
                title="RAG 서버 생성 답변 요약",
                doc_type="rag_answer",
                text=answer[:1200],
                score=1.0,
                metadata={
                    "provider": "remote",
                    "endpoint": "/api/v1/chat/query",
                    "session_id": session_id,
                    "task_type": task_type,
                },
            ),
        )

    quality = RetrievalQuality(
        sufficient=bool(contexts),
        score=_average_score(contexts),
        reason="remote RAG server references adapted to ContextPack",
    )
    return ContextPack(task_type=task_type, query=query, contexts=contexts[:top_k], quality=quality)


def _fallback_rag(task_type: str, query: str, top_k: int = 5) -> ContextPack:
    contexts = list(_FALLBACK_CONTEXTS.get(task_type, []))[:top_k]
    quality = RetrievalQuality(
        sufficient=bool(contexts),
        score=0.7 if contexts else 0.0,
        reason="mock context pack; remote RAG disabled or unavailable",
    )
    return ContextPack(task_type=task_type, query=query, contexts=contexts, quality=quality)


def _build_remote_query(task_type: str, query: str, filters: dict | None = None) -> str:
    sources = TASK_SOURCE_MAP.get(task_type, [])
    filter_text = ""
    if filters:
        public_filters = {k: v for k, v in filters.items() if k != "session_id"}
        if public_filters:
            filter_text = f"\n필터 조건: {public_filters}"
    source_text = f"\n우선 참고 문서 유형: {', '.join(sources)}" if sources else ""
    return (
        "다음 전세계약 위험 진단 LangGraph 노드가 사용할 근거를 찾아줘.\n"
        f"작업 유형: {task_type}{source_text}{filter_text}\n"
        "답변은 간단히 요약하고, references에는 관련 법령/판례/가이드/사례집 근거가 포함되게 해줘.\n"
        f"질문: {query}"
    )


def _reference_to_context(reference: Any, index: int) -> RetrievedContext:
    ref = reference if isinstance(reference, dict) else _model_to_dict(reference)
    title = str(ref.get("title") or "RAG 근거 문서")
    doc_type = str(ref.get("doc_type") or "document")
    text = str(ref.get("chunk_text") or ref.get("content") or "")
    score = _to_float(ref.get("relevance_score", ref.get("score", 0.0)))
    metadata = ref.get("metadata") if isinstance(ref.get("metadata"), dict) else {}
    return RetrievedContext(
        source_id=str(ref.get("source_id") or f"remote-rag-ref-{index}"),
        title=title,
        doc_type=doc_type,
        text=text,
        score=score,
        metadata={
            "provider": "remote",
            **metadata,
            "raw_reference": ref,
        },
    )


def _post_json(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    if requests is not None:
        response = requests.post(url, json=body, timeout=timeout)
        response.raise_for_status()
        return response.json()

    encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded_body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _remote_failure_pack(task_type: str, query: str, exc: Exception) -> ContextPack:
    return ContextPack(
        task_type=task_type,
        query=query,
        contexts=[],
        quality=RetrievalQuality(
            sufficient=False,
            score=0.0,
            reason=f"remote RAG request failed: {exc}",
        ),
    )


def _remote_strict_enabled() -> bool:
    return os.getenv("RAG_STRICT", "0").lower() in {"1", "true", "yes", "on"}


def _mock_fallback_enabled() -> bool:
    return os.getenv("RAG_FALLBACK_TO_MOCK", "0").lower() in {"1", "true", "yes", "on"}


def _average_score(contexts: list[RetrievedContext]) -> float:
    if not contexts:
        return 0.0
    return round(sum(context.score for context in contexts) / len(contexts), 3)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _model_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {}


@tool
def adaptive_rag_tool(task_type: str, query: str, filters: dict | None = None, top_k: int = 5) -> ContextPack:
    """Retrieve a ContextPack for a task using the configured Adaptive RAG boundary."""
    return adaptive_rag(task_type=task_type, query=query, filters=filters, top_k=top_k)
