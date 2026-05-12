"""전세계약 위험 진단 에이전트 - 진단 서비스"""

from __future__ import annotations
import psycopg2
from psycopg2.extras import Json

from rag_server.config import Settings
from rag_server.core.rag_pipeline import RAGPipeline
from rag_server.services.contract_parser import ContractParser
from rag_server.models.schemas import DiagnosisResponse, RiskFactor


class DiagnosisService:
    def __init__(self, settings: Settings, rag_pipeline: RAGPipeline):
        self._settings = settings
        self._rag = rag_pipeline

    async def diagnose_text(self, session_id: str, contract_text: str) -> DiagnosisResponse:
        contract_info = ContractParser.from_text(contract_text)
        risk_kws      = ContractParser.extract_risk_keywords(contract_text)
        summary_kws   = ContractParser.extract_summary_keywords(contract_info)
        all_kws       = list(dict.fromkeys(risk_kws + summary_kws))

        # ── RAG 텍스트 조합: 특약사항 → 계약서 본문 ──────────────────
        rag_text = contract_text
        if contract_info.special_terms:
            rag_text = f"[특약사항]\n{contract_info.special_terms}\n\n" + rag_text

        result = await self._rag.diagnose(
            session_id=session_id,
            contract_text=rag_text,
            contract_keywords=all_kws,
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
        self._save_log(response)
        return response

    async def diagnose_pdf(self, session_id: str, pdf_bytes: bytes) -> DiagnosisResponse:
        contract_info = ContractParser.from_pdf_bytes(pdf_bytes)
        return await self.diagnose_text(session_id, contract_info.raw_text or "")

    async def diagnose_docx(self, session_id: str, docx_bytes: bytes) -> DiagnosisResponse:
        contract_info = ContractParser.from_docx_bytes(docx_bytes)
        return await self.diagnose_text(session_id, contract_info.raw_text or "")

    def _save_log(self, response: DiagnosisResponse) -> None:
        try:
            conn = psycopg2.connect(
                host=self._settings.DB_HOST, port=self._settings.DB_PORT,
                database=self._settings.DB_NAME, user=self._settings.DB_USER,
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
                    (response.contract_info.raw_text or "")[:2000],
                    response.risk_score, response.risk_level,
                    Json([rf.model_dump() for rf in response.risk_factors]),
                    Json([ref.model_dump() for ref in response.references]),
                    response.summary[:2000],
                ),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[DiagnosisService] 로그 저장 실패: {e}")

    @staticmethod
    def recalculate_score(risk_factors: list[RiskFactor]) -> tuple[float, str]:
        weight = {"HIGH": 25.0, "MEDIUM": 10.0, "LOW": 3.0}
        score  = min(sum(weight.get(rf.severity, 5.0) for rf in risk_factors), 100.0)
        level  = "위험" if score >= 80 else ("주의" if score >= 60 else "안전")
        return round(score, 1), level
