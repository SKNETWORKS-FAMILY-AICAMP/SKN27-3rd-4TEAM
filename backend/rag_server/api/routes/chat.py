"""채팅 라우터 — POST /api/v1/chat/query"""

from fastapi import APIRouter, Request, HTTPException, Depends
from rag_server.models.schemas import ChatRequest, ChatResponse
from rag_server.config import get_settings, Settings
from rag_server.core.rag_pipeline import RAGPipeline

router = APIRouter()


def get_rag_pipeline(request: Request, settings: Settings = Depends(get_settings)) -> RAGPipeline:
    vs = getattr(request.app.state, "vector_store", None)
    gs = getattr(request.app.state, "graph_store", None)
    if vs is None:
        raise HTTPException(status_code=503, detail="VectorStore 초기화 중입니다.")
    return RAGPipeline(settings=settings, vector_store=vs, graph_store=gs)


@router.post("/query", response_model=ChatResponse, summary="전세 관련 질문 답변")
async def chat_query(body: ChatRequest, rag: RAGPipeline = Depends(get_rag_pipeline)):
    try:
        result = await rag.chat(
            session_id=body.session_id,
            question=body.message,
            history=[m.model_dump() for m in body.history],
        )
        return ChatResponse(
            session_id=body.session_id,
            answer=result["answer"],
            references=result.get("references", []),
            graph_context=result.get("graph_context", []),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG 처리 오류: {str(e)}")
