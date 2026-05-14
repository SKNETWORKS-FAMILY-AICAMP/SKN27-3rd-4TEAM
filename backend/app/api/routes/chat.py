"""
채팅 라우터 - 일반 RAG 질의응답
POST /api/v1/chat/query
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from app.models.schemas import ChatRequest, ChatResponse
from app.config import get_settings, Settings
from app.core.rag_pipeline import RAGPipeline

router = APIRouter()


def get_rag_pipeline(request: Request, settings: Settings = Depends(get_settings)) -> RAGPipeline:
    """RAGPipeline 의존성 주입 (app.state에서 가져옴)"""
    vector_store = getattr(request.app.state, "vector_store", None)
    graph_store  = getattr(request.app.state, "graph_store", None)

    if vector_store is None:
        raise HTTPException(status_code=503, detail="VectorStore 초기화 중입니다.")

    return RAGPipeline(
        settings=settings,
        vector_store=vector_store,
        graph_store=graph_store,
    )


@router.post("/query", response_model=ChatResponse, summary="전세 관련 질문 답변")
async def chat_query(
    body: ChatRequest,
    rag: RAGPipeline = Depends(get_rag_pipeline),
):
    """
    전세계약, 법령, 판례, 사기 예방 등에 관한 질문에
    RAG 기반으로 답변합니다.

    - **session_id**: 대화 세션 ID (클라이언트가 생성)
    - **message**: 사용자 질문
    - **history**: 이전 대화 이력 (선택)
    """
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
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG 처리 오류: {str(e)}")
