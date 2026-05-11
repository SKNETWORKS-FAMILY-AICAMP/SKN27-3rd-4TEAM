"""헬스체크 라우터"""

from fastapi import APIRouter, Request
from rag_server.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="서버 상태 확인")
async def health_check(request: Request):
    vs = getattr(request.app.state, "vector_store", None)
    gs = getattr(request.app.state, "graph_store", None)
    return HealthResponse(
        status="ok",
        version="1.0.0",
        services={
            "pgvector": {"status": "ok" if (vs and vs.is_ready()) else "unavailable",
                         "doc_count": vs.count() if vs else 0},
            "neo4j":    {"status": "ok" if (gs and gs.is_ready()) else "unavailable"},
        },
    )
