"""Chat routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from rag_server.config import Settings, get_settings
from rag_server.core.rag_pipeline import RAGPipeline
from rag_server.models.schemas import ChatRequest, ChatResponse
from rag_server.services.chat_agents import ChatAgentService
from rag_server.services.input_supervisor import UserInputSupervisor

router = APIRouter()


def get_chat_agent_service(request: Request, settings: Settings = Depends(get_settings)) -> ChatAgentService:
    vector_store = getattr(request.app.state, "vector_store", None)
    graph_store = getattr(request.app.state, "graph_store", None)
    if vector_store is None:
        raise HTTPException(status_code=503, detail="VectorStore is not ready.")
    rag = RAGPipeline(settings=settings, vector_store=vector_store, graph_store=graph_store)
    return ChatAgentService(settings=settings, rag_pipeline=rag)


@router.post("/query", response_model=ChatResponse, summary="전세 관련 질문 답변")
async def chat_query(body: ChatRequest, svc: ChatAgentService = Depends(get_chat_agent_service)):
    decision = UserInputSupervisor().classify(message=body.message)
    if decision.input_type != "question":
        raise HTTPException(status_code=400, detail="message is required.")
    try:
        return await svc.answer(
            session_id=body.session_id,
            message=body.message,
            history=[message.model_dump() for message in body.history],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"chat failed: {exc}") from exc
