"""RAG 전용 검색 라우터 — POST /api/v1/rag/retrieve

adaptive_rag.py 의 _remote_rag() 가 호출하는 전용 엔드포인트입니다.

일반 채팅 (/api/v1/chat/query) 과 달리:
- task_type 을 직접 받아 TASK_SOURCE_MAP 기반 문서 유형 우선순위 적용
- 질문 생성(LLM 답변) 없이 벡터 검색 결과(references)만 반환
- top_k, filters 를 외부에서 제어 가능
→ 멀티에이전트 그래프 노드가 task_type별로 최적화된 검색 결과를 얻습니다.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from rag_server.config import Settings, get_settings
from rag_server.core.rag_pipeline import RAGPipeline

router = APIRouter()

# task_type → 우선 참고 문서 유형 매핑 (adaptive_rag.py TASK_SOURCE_MAP과 동기화)
_TASK_SOURCE_MAP: dict[str, list[str]] = {
    "special_clause_analysis":       ["사례집", "법령", "판례", "서식"],
    "required_check_analysis":       ["사례집", "법령", "서식"],
    "report_generation":             ["사례집", "법령"],
    "legal_basis":                   ["법령", "판례", "사례집"],
    "legal_case_search":             ["판례", "사례집"],
    "legal_law_guide_search":        ["법령", "사례집"],
    "defense_simulation_evidence":   ["사례집", "법령", "판례"],
}


class RetrieveRequest(BaseModel):
    """RAG 검색 전용 요청 모델."""
    task_type: str = Field(..., description="작업 유형 (TASK_SOURCE_MAP 키)")
    query: str = Field(..., description="검색 쿼리 텍스트")
    top_k: int = Field(default=5, ge=1, le=20, description="반환할 최대 문서 수")
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="추가 메타데이터 필터 (예: {'doc_type': '판례'})",
    )
    session_id: str = Field(default="rag-retrieve", description="세션 ID (로깅용)")


class RetrieveResponse(BaseModel):
    """RAG 검색 전용 응답 모델."""
    task_type: str
    query: str
    references: list[dict[str, Any]]
    doc_types_searched: list[str]
    total_retrieved: int


def _get_pipeline(request: Request, settings: Settings = Depends(get_settings)) -> RAGPipeline:
    vs = getattr(request.app.state, "vector_store", None)
    gs = getattr(request.app.state, "graph_store", None)
    if vs is None:
        raise HTTPException(status_code=503, detail="VectorStore 초기화 중입니다.")
    return RAGPipeline(settings=settings, vector_store=vs, graph_store=gs)


@router.post(
    "/retrieve",
    response_model=RetrieveResponse,
    summary="task_type 기반 RAG 전용 검색 (LLM 답변 없음)",
    description=(
        "멀티에이전트 그래프 노드가 task_type에 맞는 문서 유형을 우선적으로 검색합니다. "
        "LLM 답변 생성 없이 벡터 검색 결과(references)만 반환합니다."
    ),
)
async def retrieve(body: RetrieveRequest, pipeline: RAGPipeline = Depends(_get_pipeline)) -> RetrieveResponse:
    try:
        doc_types = _TASK_SOURCE_MAP.get(body.task_type, [])

        # task_type에 맞는 검색 쿼리 구성
        search_query = _build_task_query(
            task_type=body.task_type,
            query=body.query,
            doc_types=doc_types,
            filters=body.filters,
        )

        # 검색 플랜 구성 (rag_pipeline의 내부 search plan 형식)
        search_plan = {
            "question_type": body.task_type.upper(),
            "query": search_query,
            "doc_types": doc_types if doc_types else ["사례집", "법령", "판례"],
        }

        raw_results = pipeline._search_with_plan(search_plan)
        references = pipeline._build_references(raw_results[: body.top_k])

        return RetrieveResponse(
            task_type=body.task_type,
            query=body.query,
            references=[ref.model_dump() if hasattr(ref, "model_dump") else dict(ref) for ref in references],
            doc_types_searched=doc_types,
            total_retrieved=len(references),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG 검색 오류: {e}") from e


def _build_task_query(
    task_type: str,
    query: str,
    doc_types: list[str],
    filters: dict[str, Any],
) -> str:
    """task_type 에 맞는 검색 쿼리 문자열을 생성합니다."""
    source_text = f"우선 참고 문서: {', '.join(doc_types)}" if doc_types else ""
    filter_text = ""
    if filters:
        public = {k: v for k, v in filters.items() if k != "session_id"}
        if public:
            filter_text = f" | 필터: {public}"

    prefix_map = {
        "special_clause_analysis":     "전세계약 특약 위험 분석",
        "required_check_analysis":     "전세계약 필수 확인 서류 및 위험 항목",
        "report_generation":           "전세계약 위험 진단 리포트 기준",
        "legal_basis":                 "전세계약 관련 법령·판례 근거",
        "legal_case_search":           "전세계약 판례 검색",
        "legal_law_guide_search":      "전세계약 법령·가이드 검색",
        "defense_simulation_evidence": "전세사기 예방 방어 훈련 근거",
    }
    prefix = prefix_map.get(task_type, "전세계약 위험 진단")
    return f"[{prefix}]{filter_text} {source_text}\n{query}"
