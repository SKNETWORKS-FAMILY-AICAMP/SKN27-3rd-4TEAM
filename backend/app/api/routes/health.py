"""헬스체크 라우터"""

from fastapi import APIRouter, Request
from app.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="서버 상태 확인")
async def health_check(request: Request):
    """
    서버 및 연결된 서비스(ChromaDB, Neo4j) 상태를 반환합니다.
    """
    vector_store = getattr(request.app.state, "vector_store", None)
    graph_store  = getattr(request.app.state, "graph_store", None)

    services = {
        "chromadb": {
            "status": "ok" if (vector_store and vector_store.is_ready()) else "unavailable",
            "doc_count": vector_store.count() if vector_store else 0,
        },
        "neo4j": {
            "status": "ok" if (graph_store and graph_store.is_ready()) else "unavailable",
        },
    }

    return HealthResponse(
        status="ok",
        version="1.0.0",
        services=services,
    )
