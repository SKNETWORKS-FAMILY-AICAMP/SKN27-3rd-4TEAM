"""Task-aware RAG boundary for diagnosis agents."""
from __future__ import annotations

import json
import os
import uuid
import urllib.error
import urllib.request
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None
from langchain_core.tools import tool

from common.schemas.shared import ContextPack, GraphContextItem, RetrievedContext, RetrievalQuality

TASK_SOURCE_MAP: dict[str, list[str]] = {
    "special_clause_analysis": ["체크리스트", "표준계약서", "사례집", "법령"],
    "registry_risk_analysis": ["체크리스트", "사례집", "법령"],
    "market_risk_analysis": ["사례집", "법령", "가이드"],
    "insurance_risk_analysis": ["가이드", "법령", "체크리스트"],
    "required_check_analysis": ["체크리스트", "가이드", "법령"],
    "legal_basis": ["법령", "판례", "사례집"],
    "report_generation": ["체크리스트", "가이드", "법령"],
}

TASK_QUERY_HINTS: dict[str, str] = {
    "special_clause_analysis": (
        "전세계약 특약 위험, 불공정 특약, 표준임대차계약서, 보증금 반환 지연, "
        "수리비 부담, 원상복구, 권리변동 금지"
    ),
    "registry_risk_analysis": (
        "전세계약 등기부등본, 임대인 소유자 일치, 대리인 위임장, 인감증명서, "
        "신탁등기, 근저당, 가압류, 계약 권한 확인"
    ),
    "required_check_analysis": "계약 전 필수 확인서류 등기부 건축물대장 납세증명서 신분증 위임장",
}

_FALLBACK_CONTEXTS: dict[str, list[RetrievedContext]] = {
    "special_clause_analysis": [
        RetrievedContext(
            source_id="fallback-special-clause-checklist",
            title="전세계약 특약 점검 기준",
            doc_type="CHECKLIST",
            text=(
                "임차인에게 모든 수리비를 부담시키거나 보증금 반환 시점을 다음 임차인 입주 이후로 "
                "미루는 특약은 임차인에게 불리할 수 있다. 잔금일 전후 권리변동 금지 특약은 방어 "
                "특약으로 점검한다."
            ),
            score=0.7,
        )
    ],
    "registry_risk_analysis": [
        RetrievedContext(
            source_id="fallback-registry-checklist",
            title="등기부 및 계약 권한 확인 기준",
            doc_type="CHECKLIST",
            text=(
                "계약서상 임대인과 등기부상 소유자를 대조하고, 대리인 계약은 위임장과 인감증명서를 "
                "확인한다. 신탁등기가 있으면 신탁원부와 수탁자 동의 또는 계약 권한을 확인한다."
            ),
            score=0.7,
        )
    ],
}


def adaptive_rag(task_type: str, query: str, filters: dict | None = None, top_k: int = 5) -> ContextPack:
    provider = os.getenv("RAG_PROVIDER", "remote").lower()
    if provider == "mock":
        return _fallback_rag(task_type, query, top_k)

    if provider in {"remote", "server", "http"}:
        remote = _remote_rag(task_type, query, filters, top_k)
        if remote is not None:
            return remote
        if os.getenv("RAG_FALLBACK_TO_MOCK", "1").lower() in {"1", "true", "yes", "on"}:
            return _fallback_rag(task_type, query, top_k)

    return ContextPack(
        task_type=task_type,
        query=query,
        quality=RetrievalQuality(False, 0.0, "remote RAG unavailable"),
    )


def _remote_rag(task_type: str, query: str, filters: dict | None, top_k: int) -> ContextPack | None:
    base_url = os.getenv("RAG_SERVER_URL", "http://localhost:8001").rstrip("/")
    timeout = float(os.getenv("RAG_SERVER_TIMEOUT", "12"))
    session_id = str((filters or {}).get("session_id") or f"diag-{uuid.uuid4().hex[:12]}")
    try:
        payload = _post_json(
            f"{base_url}/api/v1/chat/query",
            {
                "session_id": session_id,
                "message": _build_remote_query(task_type, query, filters),
                "history": [],
            },
            timeout,
        )
    except Exception:
        return None

    contexts = [_reference_to_context(ref, index) for index, ref in enumerate(payload.get("references", [])[:top_k], 1)]
    graph_context = _parse_graph_context(payload.get("graph_context", []))
    return ContextPack(
        task_type=task_type,
        query=query,
        contexts=contexts,
        quality=RetrievalQuality(bool(contexts), _average_score(contexts), "remote RAG references adapted"),
        graph_context=graph_context,
    )


def _build_remote_query(task_type: str, query: str, filters: dict | None) -> str:
    sources = ", ".join(TASK_SOURCE_MAP.get(task_type, []))
    hint = TASK_QUERY_HINTS.get(task_type, "")
    filter_text = f"\n필터 조건: {filters}" if filters else ""
    return (
        "전세계약 진단 LangGraph의 특정 agent가 사용할 근거만 찾아줘.\n"
        f"작업 유형: {task_type}\n"
        f"우선 문서 유형: {sources}\n"
        f"검색 힌트: {hint}{filter_text}\n"
        "관련 없는 일반 판례/잡문보다 체크리스트, 표준계약서, 전세피해 예방자료, 법령 해설을 우선해.\n"
        f"질문: {query}"
    )


def _reference_to_context(reference: Any, index: int) -> RetrievedContext:
    ref = reference if isinstance(reference, dict) else {}
    metadata = ref.get("metadata") if isinstance(ref.get("metadata"), dict) else {}
    return RetrievedContext(
        source_id=str(ref.get("source_id") or f"remote-rag-ref-{index}"),
        title=str(ref.get("title") or "RAG 근거 문서"),
        doc_type=str(ref.get("doc_type") or "document"),
        text=str(ref.get("chunk_text") or ref.get("content") or ""),
        score=_to_float(ref.get("relevance_score", ref.get("score", 0.0))),
        metadata={"provider": "remote", **metadata, "raw_reference": ref},
    )


def _parse_graph_context(raw: list[Any]) -> list[GraphContextItem]:
    """RAG 서버 응답의 graph_context 배열을 GraphContextItem 리스트로 변환."""
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        node = str(item.get("node", ""))
        relation = str(item.get("relation", ""))
        target = str(item.get("target", ""))
        if node and relation and target:
            result.append(GraphContextItem(node=node, relation=relation, target=target))
    return result


def _fallback_rag(task_type: str, query: str, top_k: int) -> ContextPack:
    contexts = list(_FALLBACK_CONTEXTS.get(task_type, []))[:top_k]
    return ContextPack(
        task_type=task_type,
        query=query,
        contexts=contexts,
        quality=RetrievalQuality(bool(contexts), _average_score(contexts), "mock fallback context"),
    )


def _post_json(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    if requests is not None:
        response = requests.post(url, json=body, timeout=timeout)
        response.raise_for_status()
        return response.json()

    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode("utf-8", errors="replace")) from exc


def _average_score(contexts: list[RetrievedContext]) -> float:
    if not contexts:
        return 0.0
    return round(sum(context.score for context in contexts) / len(contexts), 3)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@tool
def adaptive_rag_tool(task_type: str, query: str, filters: dict | None = None, top_k: int = 5) -> ContextPack:
    """Retrieve task-aware RAG evidence for a diagnosis agent."""
    return adaptive_rag(task_type=task_type, query=query, filters=filters, top_k=top_k)
