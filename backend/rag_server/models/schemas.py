"""전세계약 위험 진단 에이전트 - Pydantic 스키마 (API 요청/응답 모델)"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ChatMessage(BaseModel):
    role: str = Field(..., description="user | assistant")
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: list[ChatMessage] = Field(default_factory=list)


class RagReference(BaseModel):
    doc_type: str
    title: str
    chunk_text: str
    relevance_score: float


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    references: list[RagReference] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ContractInfo(BaseModel):
    lessor_name: Optional[str] = None
    lessee_name: Optional[str] = None
    address: Optional[str] = None
    deposit_amount: Optional[int] = None
    monthly_rent: Optional[int] = None
    contract_start: Optional[str] = None
    contract_end: Optional[str] = None
    special_terms: Optional[str] = None
    raw_text: Optional[str] = Field(default=None, exclude=True)  # 내부 처리용, API 응답에 미포함


class RiskFactor(BaseModel):
    factor_id: str
    category: str
    description: str
    severity: str                       # HIGH / MEDIUM / LOW
    legal_basis: Optional[str] = None
    advice: str


class DiagnosisRequest(BaseModel):
    session_id: str
    contract_text: Optional[str] = None


class DiagnosisResponse(BaseModel):
    session_id: str
    contract_info: ContractInfo
    risk_score: float = Field(..., ge=0, le=100)
    risk_level: str                     # 안전 / 주의 / 위험
    risk_factors: list[RiskFactor]
    summary: str
    references: list[RagReference] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict[str, Any]
