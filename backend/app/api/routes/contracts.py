"""계약서/등기부등본 파일 업로드와 진단 기록 저장 API 라우터."""

from __future__ import annotations

import uuid

import psycopg2
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from psycopg2.extras import Json

from app.config import Settings, get_settings
from app.services.document_extractor import DocumentExtractor

router = APIRouter()


class ContractUploadResponse(BaseModel):
    """계약서 업로드 후 프론트에 반환할 1차 추출 응답."""

    contract_id: str
    filename: str
    content_type: str | None = None
    extracted_text: str
    text_length: int = Field(..., ge=0)
    parsed_fields: dict[str, str | int | None]


class DiagnosisRegisterResponse(BaseModel):
    """문서 업로드 후 diagnosis_logs에 저장된 결과 응답."""

    session_id: str
    risk_score: float
    risk_level: str
    summary: str
    risk_factors: list[dict] = Field(default_factory=list)
    parsed_fields: dict[str, str | int | None] = Field(default_factory=dict)
    saved: bool = True


@router.post("/upload", response_model=ContractUploadResponse, summary="계약서 업로드 및 텍스트 추출")
async def upload_contract(file: UploadFile = File(...)):
    """PDF/DOCX/TXT 계약서를 받아 텍스트와 기본 계약 필드를 추출한다."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명이 비어 있습니다.")

    try:
        content = await file.read()
        extracted = DocumentExtractor.extract(
            filename=file.filename,
            content=content,
            content_type=file.content_type,
        )
        return ContractUploadResponse(
            contract_id=extracted.contract_id,
            filename=extracted.filename,
            content_type=extracted.content_type,
            extracted_text=extracted.extracted_text,
            text_length=len(extracted.extracted_text),
            parsed_fields=extracted.parsed_fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"문서 텍스트 추출 중 오류가 발생했습니다: {exc}") from exc


@router.post("/register-diagnosis", response_model=DiagnosisRegisterResponse, summary="업로드 문서 진단 기록 저장")
async def register_uploaded_documents(
    registry_document: UploadFile = File(...),
    lease_contract: UploadFile = File(...),
    address: str = Form(""),
    deposit_amount: int | None = Form(None),
    settings: Settings = Depends(get_settings),
):
    """등기부등본과 임대차계약서를 받아 diagnosis_logs에 1차 진단 기록을 저장한다."""
    try:
        registry = DocumentExtractor.extract(
            filename=registry_document.filename or "registry_document",
            content=await registry_document.read(),
            content_type=registry_document.content_type,
        )
        contract = DocumentExtractor.extract(
            filename=lease_contract.filename or "lease_contract",
            content=await lease_contract.read(),
            content_type=lease_contract.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"문서 추출 중 오류가 발생했습니다: {exc}") from exc

    session_id = f"upload-{uuid.uuid4().hex[:12]}"
    submitted_fields = _merge_submitted_fields(
        contract.parsed_fields,
        address=address,
        deposit_amount=deposit_amount,
    )
    combined_text = (
        f"[사용자 입력 매물]\n주소: {submitted_fields.get('address') or '미입력'}\n"
        f"보증금(만원): {submitted_fields.get('deposit_amount') or '미입력'}\n\n"
        f"[등기부등본: {registry.filename}]\n{registry.extracted_text}\n\n"
        f"[임대차계약서: {contract.filename}]\n{contract.extracted_text}"
    )
    risk_factors = _build_upload_risk_factors(registry.extracted_text, contract.extracted_text)
    risk_score, risk_level = _score_upload_risks(risk_factors)
    summary = _build_upload_summary(submitted_fields, registry.filename, contract.filename, risk_factors)

    try:
        _insert_diagnosis_log(
            settings=settings,
            session_id=session_id,
            input_text=combined_text,
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=risk_factors,
            summary=summary,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"진단 기록 저장 중 오류가 발생했습니다: {exc}") from exc

    return DiagnosisRegisterResponse(
        session_id=session_id,
        risk_score=risk_score,
        risk_level=risk_level,
        summary=summary,
        risk_factors=risk_factors,
        parsed_fields=submitted_fields,
    )


def _merge_submitted_fields(
    parsed_fields: dict[str, str | int | None],
    address: str,
    deposit_amount: int | None,
) -> dict[str, str | int | None]:
    """사용자가 등록한 매물 입력값을 문서 추출값보다 우선 적용한다."""
    merged = dict(parsed_fields)
    clean_address = address.strip()
    if clean_address:
        merged["address"] = clean_address
    if isinstance(deposit_amount, int) and deposit_amount > 0:
        merged["deposit_amount"] = deposit_amount
    return merged


def _build_upload_risk_factors(registry_text: str, contract_text: str) -> list[dict]:
    """업로드 문서 원문에서 기본 위험 신호를 규칙 기반으로 찾는다."""
    joined_text = f"{registry_text}\n{contract_text}"
    checks = [
        ("MORTGAGE", "근저당 권리 확인 필요", "HIGH", ["근저당", "채권최고액", "저당권"]),
        ("TRUST", "신탁등기 여부 확인 필요", "HIGH", ["신탁", "수탁자"]),
        ("SEIZURE", "압류/가압류 권리 확인 필요", "HIGH", ["압류", "가압류", "가처분"]),
        ("SPECIAL_TERMS", "특약사항 세부 검토 필요", "MEDIUM", ["특약", "원상복구", "위약금"]),
        ("INSURANCE", "보증보험 가입 가능 여부 확인 필요", "MEDIUM", ["보증보험", "HUG", "SGI"]),
    ]
    findings: list[dict] = []
    for code, title, severity, keywords in checks:
        matched = [keyword for keyword in keywords if keyword in joined_text]
        if not matched:
            continue
        findings.append(
            {
                "factor_id": code,
                "category": "문서 업로드 진단",
                "description": f"{title}: {', '.join(matched)} 키워드가 발견되었습니다.",
                "severity": severity,
                "advice": "등기부등본 원문과 계약서 특약을 함께 확인하고 필요하면 말소/보완 특약을 추가하세요.",
            }
        )
    if not findings:
        findings.append(
            {
                "factor_id": "BASIC_REVIEW",
                "category": "문서 업로드 진단",
                "description": "치명 키워드는 바로 발견되지 않았지만 원문 기반 추가 검토가 필요합니다.",
                "severity": "LOW",
                "advice": "주소, 임대인, 보증금, 계약기간, 특약사항을 원문과 대조하세요.",
            }
        )
    return findings


def _score_upload_risks(risk_factors: list[dict]) -> tuple[float, str]:
    """위험 신호 목록을 점수와 등급으로 변환한다."""
    weight = {"HIGH": 25, "MEDIUM": 12, "LOW": 5}
    score = min(100, sum(weight.get(str(item.get("severity")), 5) for item in risk_factors))
    if score >= 70:
        return float(score), "위험"
    if score >= 35:
        return float(score), "주의"
    return float(score), "안전"


def _build_upload_summary(
    parsed_fields: dict[str, str | int | None],
    registry_filename: str,
    contract_filename: str,
    risk_factors: list[dict],
) -> str:
    """진단 기록 카드에 표시할 요약문을 만든다."""
    address = parsed_fields.get("address") or "주소 추출 필요"
    deposit = parsed_fields.get("deposit_amount")
    deposit_text = f", 보증금 {deposit:,}만원" if isinstance(deposit, int) else ""
    top_findings = ", ".join(str(item.get("description", "")).split(":")[0] for item in risk_factors[:3])
    return (
        f"{address}{deposit_text} 기준으로 등기부등본({registry_filename})과 "
        f"임대차계약서({contract_filename})를 업로드 진단했습니다. 주요 확인 항목: {top_findings}."
    )


def _insert_diagnosis_log(
    settings: Settings,
    session_id: str,
    input_text: str,
    risk_score: float,
    risk_level: str,
    risk_factors: list[dict],
    summary: str,
) -> None:
    """diagnosis_logs 테이블에 업로드 진단 결과를 저장한다."""
    conn = psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
    )
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO diagnosis_logs
                    (session_id, input_text, risk_score, risk_level, risk_factors, rag_references, result_summary)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        input_text[:4000],
                        risk_score,
                        risk_level,
                        Json(risk_factors),
                        Json([]),
                        summary[:2000],
                    ),
                )
    finally:
        conn.close()
