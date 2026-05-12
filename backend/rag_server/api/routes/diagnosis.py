"""계약서 진단 라우터 — /text, /upload, /logs"""

from __future__ import annotations
import uuid
import psycopg2
import psycopg2.extras

from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File, Form

from rag_server.config import get_settings, Settings
from rag_server.core.rag_pipeline import RAGPipeline
from rag_server.models.schemas import DiagnosisRequest, DiagnosisResponse
from rag_server.services.diagnosis_service import DiagnosisService

router = APIRouter()


def get_diagnosis_service(request: Request, settings: Settings = Depends(get_settings)) -> DiagnosisService:
    vs = getattr(request.app.state, "vector_store", None)
    gs = getattr(request.app.state, "graph_store", None)
    if vs is None:
        raise HTTPException(status_code=503, detail="VectorStore 초기화 중입니다.")
    rag = RAGPipeline(settings=settings, vector_store=vs, graph_store=gs)
    return DiagnosisService(settings=settings, rag_pipeline=rag)


@router.post("/text", response_model=DiagnosisResponse, summary="텍스트 계약서 위험 진단")
async def diagnose_text(body: DiagnosisRequest, svc: DiagnosisService = Depends(get_diagnosis_service)):
    if not body.contract_text:
        raise HTTPException(status_code=400, detail="contract_text 가 비어 있습니다.")
    try:
        return await svc.diagnose_text(session_id=body.session_id, contract_text=body.contract_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"진단 오류: {str(e)}")


_ALLOWED_EXTENSIONS = {".pdf", ".docx"}
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/upload", response_model=DiagnosisResponse, summary="계약서 업로드 후 위험 진단 (PDF / DOCX)")
async def diagnose_upload(
    file: UploadFile = File(...),
    session_id: str = Form(default_factory=lambda: str(uuid.uuid4())),
    svc: DiagnosisService = Depends(get_diagnosis_service),
):
    filename = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_EXTENSIONS if filename.endswith(e)), None)
    if ext is None:
        raise HTTPException(status_code=400, detail="PDF 또는 DOCX 파일만 업로드 가능합니다.")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기는 10MB 이하여야 합니다.")

    try:
        if ext == ".docx":
            return await svc.diagnose_docx(session_id=session_id, docx_bytes=file_bytes)
        else:
            return await svc.diagnose_pdf(session_id=session_id, pdf_bytes=file_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"계약서 진단 오류: {str(e)}")


@router.get("/logs", summary="진단 이력 조회")
async def get_diagnosis_logs(
    session_id: str | None = None,
    limit: int = 20,
    settings: Settings = Depends(get_settings),
):
    try:
        conn = psycopg2.connect(
            host=settings.DB_HOST, port=settings.DB_PORT,
            database=settings.DB_NAME, user=settings.DB_USER, password=settings.DB_PASSWORD,
        )
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if session_id:
            cur.execute(
                "SELECT id, session_id, risk_score, risk_level, result_summary, created_at "
                "FROM diagnosis_logs WHERE session_id = %s ORDER BY created_at DESC LIMIT %s",
                (session_id, limit),
            )
        else:
            cur.execute(
                "SELECT id, session_id, risk_score, risk_level, result_summary, created_at "
                "FROM diagnosis_logs ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"logs": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"로그 조회 오류: {str(e)}")
