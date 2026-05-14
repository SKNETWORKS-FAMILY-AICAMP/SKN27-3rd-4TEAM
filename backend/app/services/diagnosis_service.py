"""
전세계약 위험 진단 에이전트 - 진단 서비스
역할: 계약서 파서 + RAG 파이프라인을 연결하여 최종 진단 결과 생성
      + PostgreSQL diagnosis_logs 기록
"""

from __future__ import annotations
import json
import psycopg2
from psycopg2.extras import Json

from app.config import Settings
from app.core.rag_pipeline import RAGPipeline
from app.services.contract_parser import ContractParser
from app.models.schemas import (
    ContractInfo,
    DiagnosisRequest,
    DiagnosisResponse,
    RiskFactor,
    RagReference,
)


class DiagnosisService:
    """
    전세계약 위험 진단 비즈니스 로직.
    1. 계약서 파싱
    2. RAG 기반 위험 진단
    3. 결과 로그 저장
    """

    def __init__(self, settings: Settings, rag_pipeline: RAGPipeline):
        self._settings = settings
        self._rag = rag_pipeline

    # ── 텍스트 진단 ──────────────────────────────────────

    async def diagnose_text(
        self, session_id: str, contract_text: str
    ) -> DiagnosisResponse:
        """텍스트로 입력된 계약서 진단"""
        # 1. 파싱
        contract_info = ContractParser.from_text(contract_text)

        # 2. 키워드 추출
        risk_keywords = ContractParser.extract_risk_keywords(contract_text)
        summary_keywords = ContractParser.extract_summary_keywords(contract_info)
        all_keywords = list(dict.fromkeys(risk_keywords + summary_keywords))

        # 3. RAG 진단
        result = await self._rag.diagnose(
            session_id=session_id,
            contract_text=contract_text,
            contract_keywords=all_keywords,
        )

        response = DiagnosisResponse(
            session_id=session_id,
            contract_info=contract_info,
            risk_score=result["risk_score"],
            risk_level=result["risk_level"],
            risk_factors=result["risk_factors"],
            summary=result["summary"],
            references=result.get("references", []),
        )

        # 4. 로그 저장
        self._save_log(response)

        return response

    # ── PDF 진단 ─────────────────────────────────────────

    async def diagnose_pdf(
        self, session_id: str, pdf_bytes: bytes
    ) -> DiagnosisResponse:
        """업로드된 PDF 계약서 진단"""
        contract_info = ContractParser.from_pdf_bytes(pdf_bytes)
        raw_text = contract_info.raw_text or ""

        return await self.diagnose_text(session_id, raw_text)

    # ── DB 로그 저장 ──────────────────────────────────────

    def _save_log(self, response: DiagnosisResponse) -> None:
        """진단 결과를 diagnosis_logs 테이블에 저장"""
        try:
            conn = psycopg2.connect(
                host=self._settings.DB_HOST,
                port=self._settings.DB_PORT,
                database=self._settings.DB_NAME,
                user=self._settings.DB_USER,
                password=self._settings.DB_PASSWORD,
            )
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO diagnosis_logs
                (session_id, input_text, risk_score, risk_level, risk_factors, rag_references, result_summary)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    response.session_id,
                    response.contract_info.raw_text[:2000] if response.contract_info.raw_text else "",
                    response.risk_score,
                    response.risk_level,
                    Json([rf.model_dump() for rf in response.risk_factors]),
                    Json([ref.model_dump() for ref in response.references]),
                    response.summary[:2000],
                ),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            # 로그 저장 실패는 진단 응답에 영향 없음
            print(f"[DiagnosisService] 로그 저장 실패: {e}")

    # ── 위험 점수 규칙 기반 재계산 ────────────────────────

    @staticmethod
    def recalculate_score(risk_factors: list[RiskFactor]) -> tuple[float, str]:
        """
        위험 요소 목록으로 위험 점수/등급 재계산.
        LLM 결과 검증용.
        """
        score = 0.0
        weight = {"HIGH": 25.0, "MEDIUM": 10.0, "LOW": 3.0}

        for rf in risk_factors:
            score += weight.get(rf.severity, 5.0)

        score = min(score, 100.0)

        if score >= 80:
            level = "위험"
        elif score >= 60:
            level = "주의"
        else:
            level = "안전"

        return round(score, 1), level
