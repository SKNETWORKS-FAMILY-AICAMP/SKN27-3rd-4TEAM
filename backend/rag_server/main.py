"""
전세계약 위험 진단 에이전트 - FastAPI 진입점
실행: cd backend && uvicorn rag_server.main:app --reload
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rag_server.config import get_settings
from rag_server.api.routes.health import router as health_router
from rag_server.api.routes.chat import router as chat_router
from rag_server.api.routes.diagnosis import router as diagnosis_router
from rag_server.api.routes.retrieve import router as retrieve_router

settings = get_settings()

# ── LangSmith 트레이싱 환경변수 설정 ─────────────────────
os.environ["LANGCHAIN_TRACING_V2"] = str(settings.LANGCHAIN_TRACING_V2).lower()
os.environ["LANGCHAIN_API_KEY"]    = settings.LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"]    = settings.LANGCHAIN_PROJECT
os.environ["LANGCHAIN_ENDPOINT"]   = settings.LANGCHAIN_ENDPOINT


@asynccontextmanager
async def lifespan(app: FastAPI):
    from rag_server.core.vector_store import VectorStore
    from rag_server.core.graph_store import GraphStore

    print("🚀 서버 시작 — VectorStore / GraphStore 초기화...")
    app.state.vector_store = VectorStore(settings)
    app.state.graph_store  = GraphStore(settings)
    print("✅ 초기화 완료")

    yield

    print("🛑 서버 종료 — 연결 정리...")
    app.state.graph_store.close()


app = FastAPI(
    title="전세계약 위험 진단 에이전트 API",
    description=(
        "전세계약서를 분석하여 전세사기 위험도를 진단하고 "
        "법령·판례·사례집 기반으로 방어 조언을 제공합니다."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router,    prefix="/api/v1",          tags=["헬스체크"])
app.include_router(chat_router,      prefix="/api/v1/chat",     tags=["채팅"])
app.include_router(diagnosis_router, prefix="/api/v1/diagnosis", tags=["계약서 진단"])
app.include_router(retrieve_router,  prefix="/api/v1/rag",      tags=["RAG 검색"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "rag_server.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=(settings.APP_ENV == "development"),
    )
