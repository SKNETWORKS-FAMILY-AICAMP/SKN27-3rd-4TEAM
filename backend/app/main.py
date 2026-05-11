"""
전세계약 위험 진단 에이전트 - FastAPI 진입점
담당: 라우팅 / 미들웨어 / 라이프사이클
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.routes.health import router as health_router
from app.api.routes.chat import router as chat_router
from app.api.routes.diagnosis import router as diagnosis_router

settings = get_settings()


# ── LangSmith 트레이싱 환경변수 설정 ──────────────────────
os.environ["LANGCHAIN_TRACING_V2"] = str(settings.LANGCHAIN_TRACING_V2).lower()
os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT


# ── 앱 라이프사이클 ───────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """시작/종료 시 리소스 초기화 & 정리"""
    # 시작 시: DB 연결 풀, VectorStore, GraphStore 준비
    from app.core.vector_store import VectorStore
    from app.core.graph_store import GraphStore

    print("🚀 서버 시작 - VectorStore / GraphStore 초기화...")
    app.state.vector_store = VectorStore(settings)
    app.state.graph_store = GraphStore(settings)
    print("✅ 초기화 완료")

    yield

    # 종료 시: 연결 닫기
    print("🛑 서버 종료 - 연결 정리...")
    app.state.graph_store.close()


# ── FastAPI 앱 생성 ───────────────────────────────────────
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

# ── CORS 미들웨어 ─────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 프론트엔드 도메인으로 제한 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 라우터 등록 ───────────────────────────────────────────
app.include_router(health_router,    prefix="/api/v1",         tags=["헬스체크"])
app.include_router(chat_router,      prefix="/api/v1/chat",    tags=["채팅"])
app.include_router(diagnosis_router, prefix="/api/v1/diagnosis", tags=["계약서 진단"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=(settings.APP_ENV == "development"),
    )
