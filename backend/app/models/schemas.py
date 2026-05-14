"""
전세계약 위험 진단 에이전트 - Pydantic 스키마
API 요청/응답 모델 정의
"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ══════════════════════════════════════════════════
# 채팅 (일반 RAG 질의)
# ══════════════════════════════════════════════════

class ChatMessage(BaseModel):
    role: str = Field(..., description="user | assistant")
    content: str


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="세션 ID (프론트에서 생성)")
    message: str = Field(..., description="사용자 질문")
    history: list[ChatMessage] = Field(default_factory=list, description="이전 대화 이력")


class RagReference(BaseModel):
    source_id: Optional[str] = None
    doc_type: str           # 법령 / 판례 / 사례집 / 서식
    title: str
    chunk_text: str
    relevance_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    references: list[RagReference] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ══════════════════════════════════════════════════
# 계약서 진단
# ══════════════════════════════════════════════════

class ContractInfo(BaseModel):
    """파싱된 계약서 핵심 정보"""
    lessor_name: Optional[str] = None        # 임대인 이름
    lessee_name: Optional[str] = None        # 임차인 이름
    address: Optional[str] = None            # 물건지 주소
    deposit_amount: Optional[int] = None     # 보증금 (만원)
    monthly_rent: Optional[int] = None       # 월세 (만원, 순전세=0)
    contract_start: Optional[str] = None     # 계약 시작일
    contract_end: Optional[str] = None       # 계약 종료일
    special_terms: Optional[str] = None      # 특약사항 원문
    raw_text: Optional[str] = None           # 원본 텍스트


class RiskFactor(BaseModel):
    """개별 위험 요소"""
    factor_id: str                           # 고유 ID (예: RF001)
    category: str                            # 전세가율 / 권리관계 / 특약 / 절차
    description: str                         # 위험 설명
    severity: str                            # HIGH / MEDIUM / LOW
    legal_basis: Optional[str] = None        # 관련 법령/판례
    advice: str                              # 대응 조언


class DiagnosisRequest(BaseModel):
    session_id: str
    contract_text: Optional[str] = None      # 텍스트로 직접 입력 (파일 없을 때)
    # 파일 업로드는 multipart form 별도 endpoint 사용


class DiagnosisResponse(BaseModel):
    session_id: str
    contract_info: ContractInfo
    risk_score: float = Field(..., ge=0, le=100, description="위험 점수 0~100")
    risk_level: str = Field(..., description="안전 / 주의 / 위험")
    risk_factors: list[RiskFactor]
    summary: str                             # 종합 진단 요약
    references: list[RagReference] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ══════════════════════════════════════════════════
# 헬스체크
# ══════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict[str, Any]
