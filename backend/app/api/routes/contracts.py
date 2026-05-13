"""계약서 파일 업로드와 텍스트 추출 API 라우터."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

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
