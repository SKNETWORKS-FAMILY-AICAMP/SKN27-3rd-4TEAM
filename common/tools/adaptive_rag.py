"""Adaptive RAG boundary for multi-agent graphs.

[엔드포인트 전략]
- RAG_PROVIDER=remote (기본): /api/v1/rag/retrieve 전용 엔드포인트 호출
  → task_type 기반 TASK_SOURCE_MAP 우선순위가 서버에 직접 전달됩니다.
  → 일반 채팅 /chat/query 를 통한 우회 호출을 하지 않습니다.
- RAG_PROVIDER=mock: 하드코딩된 mock 데이터 반환 (오프라인 테스트 전용)
- RAG_FALLBACK_TO_MOCK=1: 서버 연결 실패 시 mock 데이터로 fallback
  ※ 실서비스에서는 RAG_FALLBACK_TO_MOCK=0 으로 고정하세요.
    fallback 발동 시 응답에 경고 메시지가 포함됩니다.

[호출 인터페이스]
    pack = adaptive_rag(task_type, query, filters, top_k)
    pack.quality.sufficient  # 검색 품질 충분 여부
    pack.quality.reason      # 검색 상태 설명 (fallback 경고 포함)
    pack.contexts            # 검색된 문서 목록
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

# task_type → 우선 참고 문서 유형 매핑 (rag_server/api/routes/retrieve.py 와 동기화 유지)
TASK_SOURCE_MAP: dict[str, list[str]] = {
    "special_clause_analysis":     ["사례집", "법령", "판례", "서식"],
    "required_check_analysis":     ["사례집", "법령", "서식"],
    "report_generation":           ["사례집", "법령"],
    "legal_basis":                 ["법령", "판례", "사례집"],
    "legal_case_search":           ["판례", "사례집"],
    "legal_law_guide_search":      ["법령", "사례집"],
    "defense_simulation_evidence": ["사례집", "법령", "판례"],
}

# ── Fallback mock 컨텍스트 (오프라인 테스트 전용) ──────────────────────
_FALLBACK_WARNING = (
    "[데이터 조회 불가] RAG 서버에 연결할 수 없어 임시 예시 데이터를 사용하고 있습니다. "
    "실제 법령·판례 검색 결과가 아니므로 이 내용을 법적 근거로 활용하지 마세요. "
    "서비스 담당자에게 RAG 서버 상태를 확인하세요."
)

_FALLBACK_CONTEXTS: dict[str, list[RetrievedContext]] = {
    "special_clause_analysis": [
        RetrievedContext(
            source_id="mock-checklist-special-clause",
            title="[임시 예시] 전세계약 특약 점검 기준",
            doc_type="checklist",
            text=(
                _FALLBACK_WARNING + "\n\n"
                "임차인에게 모든 수리비를 부담시키거나, 보증금 반환 시점을 과도하게 늦추거나, "
                "대항력 확보를 방해하는 특약은 위험 신호로 본다. 임대인의 추가 담보권 설정 제한과 "
                "잔금 다음날까지 권리 변동 금지 문구를 확인한다."
            ),
            score=0.75,
            metadata={"is_mock": True},
        )
    ],
    "required_check_analysis": [
        RetrievedContext(
            source_id="mock-checklist-required-docs",
            title="[임시 예시] 계약 전 필수 확인 서류",
            doc_type="checklist",
            text=(
                _FALLBACK_WARNING + "\n\n"
                "계약서만으로는 등기부 권리관계, 임대인과 소유자 일치 여부, 선순위 보증금, 체납 세금, "
                "위반건축물 여부를 확정할 수 없다. 해당 자료를 별도로 확인해야 한다."
            ),
            score=0.72,
            metadata={"is_mock": True},
        )
    ],
    "legal_case_search": [
        RetrievedContext(
            source_id="mock-internal-case-deposit-return",
            title="[임시 예시] 보증금 반환 지연 특약 관련",
            doc_type="case",
            text=(
                _FALLBACK_WARNING + "\n\n"
                "임대인이 다음 임차인 입주나 자금 사정을 이유로 보증금 반환을 지연할 수 있는지에 관한 "
                "분쟁에서는 계약 종료, 목적물 인도, 반환 청구 사실, 특약의 구체적 문구가 핵심 쟁점이 된다."
            ),
            score=0.78,
            metadata={"is_mock": True},
        )
    ],
    "legal_law_guide_search": [
        RetrievedContext(
            source_id="mock-law-housing-lease",
            title="[임시 예시] 주택임대차보호법 및 임대차 가이드",
            doc_type="law",
            text=(
                _FALLBACK_WARNING + "\n\n"
                "임차인은 대항력과 우선변제권 확보를 위해 전입신고, 점유, 확정일자 등 요건을 확인해야 하며, "
                "보증금 반환 분쟁에서는 계약 종료와 목적물 반환, 반환 요구 증거가 중요하다."
            ),
            score=0.72,
            metadata={"is_mock": True},
        )
    ],
    "defense_simulation_evidence": [
        RetrievedContext(
            source_id="mock-casebook-defense-simulation",
            title="[임시 예시] 전세피해 사례집 기반 방어 훈련 기준",
            doc_type="casebook",
            text=(
                _FALLBACK_WARNING + "\n\n"
                "전세사기 예방 훈련에서는 등기부 직접 발급, 신탁원부 확인, 임대인 신분 및 대리권 확인, "
                "전세가율과 보증보험 가능 여부 확인, 전입신고와 확정일자 확보, 불리한 특약 수정 요구를 "
                "핵심 방어 행동으로 본다."
            ),
            score=0.73,
            metadata={"is_mock": True},
        )
    ],
    "report_generation": [
        RetrievedContext(
            source_id="mock-guide-report",
            title="[임시 예시] 전세계약 위험 안내 리포트 작성 기준",
            doc_type="guide",
            text=(
                _FALLBACK_WARNING + "\n\n"
                "위험도는 확정적 법률 판단이 아니라 계약 전 확인을 돕는 보조 정보로 설명해야 한다."
            ),
            score=0.7,
            metadata={"is_mock": True},
        )
    ],
}


# ── 메인 진입점 ───────────────────────────────────────────────────────

def adaptive_rag(task_type: str, query: str, filters: dict | None = None, top_k: int = 5) -> ContextPack:
    """task_type 에 맞는 RAG 검색을 수행하고 ContextPack 을 반환합니다.

    Args:
        task_type: TASK_SOURCE_MAP 키 (예: "legal_case_search")
        query:     검색 쿼리 텍스트
        filters:   추가 메타데이터 필터 (session_id 포함 가능)
        top_k:     최대 반환 문서 수

    Returns:
        ContextPack — quality.reason 에 fallback 경고 포함 가능
    """
    provider = os.getenv("RAG_PROVIDER", "remote").lower()

    if provider == "mock":
        return _fallback_rag(task_type=task_type, query=query, top_k=top_k, triggered_by="RAG_PROVIDER=mock")

    if provider in {"remote", "server", "http"}:
        remote_pack = _remote_rag(task_type=task_type, query=query, filters=filters, top_k=top_k)
        if remote_pack is not None:
            return remote_pack

        if _mock_fallback_enabled():
            print(
                f"[AdaptiveRAG] ⚠️  RAG 서버 연결 실패 — mock fallback 활성화 (task_type={task_type})\n"
                f"             실서비스에서는 RAG_FALLBACK_TO_MOCK=0 으로 설정하세요."
            )
            return _fallback_rag(
                task_type=task_type,
                query=query,
                top_k=top_k,
                triggered_by="RAG_FALLBACK_TO_MOCK=1 (서버 연결 실패)",
            )

    return ContextPack(
        task_type=task_type,
        query=query,
        contexts=[],
        quality=RetrievalQuality(
            sufficient=False,
            score=0.0,
            reason=(
                "[데이터 조회 불가] RAG 서버에 연결할 수 없습니다. "
                "오프라인 테스트 환경에서는 RAG_FALLBACK_TO_MOCK=1 을 설정하세요. "
                "실서비스에서는 RAG 서버 상태를 확인하세요."
            ),
        ),
    )


# ── 전용 retrieve 엔드포인트 호출 ─────────────────────────────────────

def _remote_rag(task_type: str, query: str, filters: dict | None = None, top_k: int = 5) -> ContextPack | None:
    """RAG 서버의 /api/v1/rag/retrieve 전용 엔드포인트를 호출합니다.

    - task_type 을 서버에 직접 전달 → TASK_SOURCE_MAP 기반 우선순위 검색
    - LLM 답변 생성 없이 references 만 반환받아 ContextPack 으로 변환
    """
    base_url = os.getenv("RAG_SERVER_URL", "http://localhost:8000").rstrip("/")
    timeout = float(os.getenv("RAG_SERVER_TIMEOUT", "10"))
    session_id = str((filters or {}).get("session_id") or f"lg-{uuid.uuid4().hex[:12]}")

    body = {
        "task_type": task_type,
        "query": query,
        "top_k": top_k,
        "filters": {k: v for k, v in (filters or {}).items() if k != "session_id"},
        "session_id": session_id,
    }

    try:
        payload = _post_json(
            url=f"{base_url}/api/v1/rag/retrieve",
            body=body,
            timeout=timeout,
        )
    except Exception as exc:
        print(f"[AdaptiveRAG] retrieve 엔드포인트 호출 실패: {exc}")
        return _remote_failure_pack(task_type, query, exc) if _remote_strict_enabled() else None

    references = payload.get("references", [])
    contexts = [_reference_to_context(ref, i) for i, ref in enumerate(references[:top_k], 1)]

    quality = RetrievalQuality(
        sufficient=bool(contexts),
        score=_average_score(contexts),
        reason=(
            f"RAG retrieve 엔드포인트 검색 완료 "
            f"(task_type={task_type}, doc_types={payload.get('doc_types_searched', [])})"
        ),
    )
    return ContextPack(task_type=task_type, query=query, contexts=contexts[:top_k], quality=quality)


# ── Fallback mock ─────────────────────────────────────────────────────

def _fallback_rag(task_type: str, query: str, top_k: int = 5, triggered_by: str = "unknown") -> ContextPack:
    """RAG 서버 미사용/연결 실패 시 임시 예시 데이터를 반환합니다.

    ⚠️  반환되는 contexts 의 title 과 text 에 '[임시 예시]' 경고 문구가 포함됩니다.
    ⚠️  quality.reason 에도 경고 메시지가 포함되어 상위 노드에서 사용자 안내에 활용할 수 있습니다.
    """
    contexts = list(_FALLBACK_CONTEXTS.get(task_type, []))[:top_k]
    reason = (
        f"[데이터 조회 불가 — {triggered_by}] "
        "실제 법령·판례 데이터베이스 대신 임시 예시 데이터를 사용 중입니다. "
        "이 결과를 법적 근거로 활용하지 마세요."
    )
    quality = RetrievalQuality(
        sufficient=False,   # mock 데이터는 항상 insufficient 로 표시
        score=0.0,
        reason=reason,
    )
    return ContextPack(task_type=task_type, query=query, contexts=contexts, quality=quality)


# ── 공통 헬퍼 ────────────────────────────────────────────────────────

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
        },
    )


def _post_json(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    if requests is not None:
        response = requests.post(url, json=body, timeout=timeout)
        response.raise_for_status()
        return response.json()

    encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded_body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
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
            reason=f"[데이터 조회 불가] RAG retrieve 요청 실패: {exc}",
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
