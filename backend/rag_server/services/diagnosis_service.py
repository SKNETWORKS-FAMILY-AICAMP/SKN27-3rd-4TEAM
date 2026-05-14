"""Diagnosis service for contract text/files."""

from __future__ import annotations

import psycopg2
from psycopg2.extras import Json

from rag_server.config import Settings
from rag_server.core.rag_pipeline import RAGPipeline
from rag_server.models.schemas import DiagnosisResponse, RiskFactor
from rag_server.services.contract_parser import ContractParser


class DiagnosisService:
    def __init__(self, settings: Settings, rag_pipeline: RAGPipeline):
        self._settings = settings
        self._rag = rag_pipeline

    async def diagnose_text(self, session_id: str, contract_text: str) -> DiagnosisResponse:
        contract_info = ContractParser.from_text(contract_text)
        risk_keywords = ContractParser.extract_risk_keywords(contract_text)
        summary_keywords = ContractParser.extract_summary_keywords(contract_info)
        keywords = list(dict.fromkeys(risk_keywords + summary_keywords))

        result = await self._rag.diagnose(
            session_id=session_id,
            contract_text=contract_text,
            contract_keywords=keywords,
        )

        response = DiagnosisResponse(
            session_id=session_id,
            contract_info=contract_info,
            risk_score=result["risk_score"],
            risk_level=result["risk_level"],
            risk_factors=result["risk_factors"],
            summary=result["summary"],
            references=result.get("references", []),
            graph_context=result.get("graph_context", []),
        )
        self._save_log(response)
        return response

    async def diagnose_pdf(self, session_id: str, pdf_bytes: bytes) -> DiagnosisResponse:
        contract_info = ContractParser.from_pdf_bytes(pdf_bytes)
        return await self.diagnose_text(session_id, contract_info.raw_text or "")

    async def diagnose_file(self, session_id: str, filename: str, file_bytes: bytes) -> DiagnosisResponse:
        lower = filename.lower()
        if lower.endswith(".pdf"):
            contract_info = ContractParser.from_pdf_bytes(file_bytes)
        elif lower.endswith(".docx"):
            contract_info = ContractParser.from_docx_bytes(file_bytes)
        elif lower.endswith(".txt"):
            contract_info = ContractParser.from_text(_decode_text(file_bytes))
        else:
            raise ValueError("unsupported contract file type")
        return await self.diagnose_text(session_id, contract_info.raw_text or "")

    def _save_log(self, response: DiagnosisResponse) -> None:
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
                    (response.contract_info.raw_text or "")[:2000],
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
        except Exception as exc:
            print(f"[DiagnosisService] failed to save log: {exc}")

    @staticmethod
    def recalculate_score(risk_factors: list[RiskFactor]) -> tuple[float, str]:
        weight = {"HIGH": 25.0, "MEDIUM": 10.0, "LOW": 3.0}
        score = min(sum(weight.get(rf.severity, 5.0) for rf in risk_factors), 100.0)
        if score >= 80:
            level = "위험"
        elif score >= 60:
            level = "주의"
        else:
            level = "안전"
        return round(score, 1), level


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
