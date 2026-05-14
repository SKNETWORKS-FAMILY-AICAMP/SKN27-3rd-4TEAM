"""Contract diagnosis routes."""

from __future__ import annotations

import uuid

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from rag_server.config import Settings, get_settings
from rag_server.core.rag_pipeline import RAGPipeline
from rag_server.models.schemas import DiagnosisRequest, DiagnosisResponse
from rag_server.services.diagnosis_service import DiagnosisService

router = APIRouter()


def get_diagnosis_service(request: Request, settings: Settings = Depends(get_settings)) -> DiagnosisService:
    vector_store = getattr(request.app.state, "vector_store", None)
    graph_store = getattr(request.app.state, "graph_store", None)
    if vector_store is None:
        raise HTTPException(status_code=503, detail="VectorStore is not ready.")
    rag = RAGPipeline(settings=settings, vector_store=vector_store, graph_store=graph_store)
    return DiagnosisService(settings=settings, rag_pipeline=rag)


@router.post("/text", response_model=DiagnosisResponse, summary="Diagnose contract text")
async def diagnose_text(body: DiagnosisRequest, svc: DiagnosisService = Depends(get_diagnosis_service)):
    if not body.contract_text:
        raise HTTPException(status_code=400, detail="contract_text is required.")
    try:
        return await svc.diagnose_text(session_id=body.session_id, contract_text=body.contract_text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"diagnosis failed: {exc}") from exc


@router.post("/upload", response_model=DiagnosisResponse, summary="Upload and diagnose a contract file")
async def diagnose_upload(
    file: UploadFile = File(...),
    session_id: str = Form(default_factory=lambda: str(uuid.uuid4())),
    svc: DiagnosisService = Depends(get_diagnosis_service),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required.")
    lower = file.filename.lower()
    if not lower.endswith((".pdf", ".docx", ".txt")):
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files are supported.")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File must be 10MB or smaller.")
    try:
        return await svc.diagnose_file(session_id=session_id, filename=file.filename, file_bytes=file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"file diagnosis failed: {exc}") from exc


@router.get("/logs", summary="List diagnosis logs")
async def get_diagnosis_logs(
    session_id: str | None = None,
    limit: int = 20,
    settings: Settings = Depends(get_settings),
):
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
        return {"logs": [dict(row) for row in rows], "total": len(rows)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to load diagnosis logs: {exc}") from exc
