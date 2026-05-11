"""
계약서 진단 라우터
POST /api/v1/diagnosis/text   - 텍스트 직접 입력
POST /api/v1/diagnosis/upload - PDF 파일 업로드
GET  /api/v1/diagnosis/logs   - 진단 이력 조회
"""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.config import get_settings, Settings
from app.core.rag_pipeline import RAGPipeline
from app.models.schemas import DiagnosisRequest, DiagnosisResponse
from app.services.diagnosis_service import DiagnosisService

router = APIRouter()

# ── 의존성 주입 ───────────────────────────────────────────

def get_diagnosis_service(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> DiagnosisService:
    vector_store = getattr(request.app.state, "vector_store", None)
    graph_store  = getattr(request.app.state, "graph_store", None)

    if vector_store is None:
        raise HTTPException(status_code=503, detail="VectorStore 초기화 중입니다.")

    rag = RAGPipeline(
        settings=settings,
        vector_store=vector_store,
        graph_store=graph_store,
    )
    return DiagnosisService(settings=settings, rag_pipeline=rag)


# ── 엔드포인트 ────────────────────────────────────────────

@router.post(
    "/text",
    response_model=DiagnosisResponse,
    summary="텍스트 계약서 위험 진단",
)
async def diagnose_text(
    body: DiagnosisRequest,
    svc: DiagnosisService = Depends(get_diagnosis_service),
):
    """
    텍스트로 붙여넣은 전세계약서 내용을 분석하여 위험도를 진단합니다.

    - **session_id**: 세션 ID
    - **contract_text**: 계약서 전문 텍스트
    """
    if not body.contract_text:
        raise HTTPException(status_code=400, detail="contract_text 가 비어 있습니다.")

    try:
        return await svc.diagnose_text(
            session_id=body.session_id,
            contract_text=body.contract_text,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"진단 오류: {str(e)}")


@router.post(
    "/upload",
    response_model=DiagnosisResponse,
    summary="PDF 계약서 파일 업로드 후 위험 진단",
)
async def diagnose_upload(
    file: UploadFile = File(..., description="전세계약서 PDF 파일"),
    session_id: str = Form(default_factory=lambda: str(uuid.uuid4())),
    svc: DiagnosisService = Depends(get_diagnosis_service),
):
    """
    PDF 파일을 업로드하여 전세계약서 위험도를 진단합니다.

    - **file**: PDF 파일 (multipart/form-data)
    - **session_id**: 세션 ID (없으면 자동 생성)
    """
    # 파일 형식 검증
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    # 파일 크기 제한 (10MB)
    MAX_SIZE = 10 * 1024 * 1024
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="파일 크기는 10MB 이하여야 합니다.")

    try:
        return await svc.diagnose_pdf(
            session_id=session_id,
            pdf_bytes=pdf_bytes,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 진단 오류: {str(e)}")


@router.get(
    "/logs",
    summary="진단 이력 조회",
)
async def get_diagnosis_logs(
    session_id: str | None = None,
    limit: int = 20,
    settings: Settings = Depends(get_settings),
):
    """
    과거 진단 이력을 조회합니다.

    - **session_id**: 특정 세션 필터 (선택)
    - **limit**: 최대 반환 건수 (기본 20)
    """
    import psycopg2
    import psycopg2.extras

    try:
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            database=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
        )
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if session_id:
            cur.execute(
                """
                SELECT id, session_id, risk_score, risk_level, result_summary, created_at
                FROM diagnosis_logs
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (session_id, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, session_id, risk_score, risk_level, result_summary, created_at
                FROM diagnosis_logs
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )

        rows = cur.fetchall()
        cur.close()
        conn.close()

        return {"logs": [dict(r) for r in rows], "total": len(rows)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"로그 조회 오류: {str(e)}")
