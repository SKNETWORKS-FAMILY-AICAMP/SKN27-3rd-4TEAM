"""Contract diagnosis routes."""

from __future__ import annotations

import uuid
import re

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from rag_server.config import Settings, get_settings
from rag_server.models.schemas import DiagnosisRequest, DiagnosisResponse
from rag_server.services.diagnosis_service import DiagnosisService
from rag_server.services.contract_parser import ContractParser
from rag_server.services.input_supervisor import UserInputSupervisor

router = APIRouter()


def get_diagnosis_service(settings: Settings = Depends(get_settings)) -> DiagnosisService:
    return DiagnosisService(settings=settings)


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
    decision = UserInputSupervisor().classify(filename=file.filename)
    if decision.input_type != "document":
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

        # contract_info, estimated_sale_price, jeonse_ratio 컬럼 직접 조회
        # (컬럼이 없는 구버전 DB는 fallback 처리)
        select_cols = (
            "id, session_id, input_text, risk_score, risk_level, risk_factors, "
            "rag_references, result_summary, created_at, "
            "estimated_sale_price, jeonse_ratio, contract_info"
        )
        if session_id:
            cur.execute(
                f"SELECT {select_cols} FROM diagnosis_logs "
                "WHERE session_id = %s ORDER BY created_at DESC LIMIT %s",
                (session_id, limit),
            )
        else:
            cur.execute(
                f"SELECT {select_cols} FROM diagnosis_logs "
                "ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        logs = []
        for row in rows:
            item = dict(row)
            # contract_info 컬럼(JSONB)이 있으면 그대로, 없으면 raw_text 재파싱
            ci = item.pop("contract_info", None)
            if ci and isinstance(ci, dict) and ci.get("address"):
                # 신버전: DB에 저장된 contract_info JSON 사용
                # estimated_sale_price/jeonse_ratio는 최상위 컬럼 값으로 덮어쓰기
                if item.get("estimated_sale_price") is not None:
                    ci["estimated_sale_price"] = item["estimated_sale_price"]
                if item.get("jeonse_ratio") is not None:
                    ci["jeonse_ratio"] = float(item["jeonse_ratio"])
                item["contract_info"] = ci
            else:
                # 구버전 레코드: raw_text 재파싱 후 risk_factors description에서 시세 복원
                contract_text = str(item.get("input_text") or "")
                if contract_text:
                    contract_obj = ContractParser.from_text(contract_text)
                    # estimated_sale_price: DB 컬럼 우선, 없으면 risk_factors description 파싱
                    if item.get("estimated_sale_price") is not None:
                        contract_obj.estimated_sale_price = item["estimated_sale_price"]
                        contract_obj.jeonse_ratio = (
                            float(item["jeonse_ratio"]) if item.get("jeonse_ratio") is not None else None
                        )
                    else:
                        _apply_market_fields_from_risks(contract_obj, item.get("risk_factors") or [])
                    item["contract_info"] = contract_obj.model_dump()
            # 불필요한 중복 키 제거
            item.pop("estimated_sale_price", None)
            item.pop("jeonse_ratio", None)
            logs.append(item)
        return {"logs": logs, "total": len(logs)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to load diagnosis logs: {exc}") from exc


def _apply_market_fields_from_risks(contract_info, risk_factors: list[dict]) -> None:
    """구버전 레코드 호환: MODEL-JEONSE-RATIO description에서 시세 역파싱."""
    for risk in risk_factors:
        if risk.get("factor_id") != "MODEL-JEONSE-RATIO":
            continue
        description = str(risk.get("description") or "")
        sale_match = re.search(r"예상 매매가\s*([0-9,]+)\s*만원", description)
        ratio_match = re.search(r"전세가율은\s*([0-9.]+)%", description)
        if sale_match:
            contract_info.estimated_sale_price = int(sale_match.group(1).replace(",", ""))
        if ratio_match:
            contract_info.jeonse_ratio = float(ratio_match.group(1))
        return
