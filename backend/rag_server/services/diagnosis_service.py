"""Diagnosis service for contract text/files."""

from __future__ import annotations

import psycopg2
from psycopg2.extras import Json

from rag_server.config import Settings
from rag_server.models.schemas import DiagnosisResponse, RiskFactor
from rag_server.services.contract_parser import ContractParser
from rag_server.services.graph_agents import DiagnosisState, build_contract_diagnosis_graph


class DiagnosisService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._graph = build_contract_diagnosis_graph(settings)

    async def diagnose_text(self, session_id: str, contract_text: str) -> DiagnosisResponse:
        contract_info = ContractParser.from_text(contract_text)
        return await self._diagnose_contract_info(session_id, contract_info)

    async def diagnose_pdf(self, session_id: str, pdf_bytes: bytes) -> DiagnosisResponse:
        contract_info = ContractParser.from_pdf_bytes(pdf_bytes)
        return await self._diagnose_contract_info(session_id, contract_info)

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
        return await self._diagnose_contract_info(session_id, contract_info)

    async def _diagnose_contract_info(self, session_id: str, contract_info) -> DiagnosisResponse:
        initial_state: DiagnosisState = {
            "session_id":    session_id,
            "contract_info": contract_info,
        }
        final_state = await self._graph.ainvoke(initial_state)
        response: DiagnosisResponse = final_state["response"]
        if _is_successful_diagnosis(response):
            self._save_log(response)
        return response

    def _save_log(self, response: DiagnosisResponse) -> None:
        INSERT_SQL = (
            "INSERT INTO diagnosis_logs "
            "(session_id, input_text, risk_score, risk_level, risk_factors, "
            " rag_references, result_summary, "
            " estimated_sale_price, jeonse_ratio, contract_info) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING"
        )
        try:
            conn = psycopg2.connect(
                host=self._settings.DB_HOST,
                port=self._settings.DB_PORT,
                database=self._settings.DB_NAME,
                user=self._settings.DB_USER,
                password=self._settings.DB_PASSWORD,
            )
            cur = conn.cursor()
            ci = response.contract_info
            contract_info_json = Json(ci.model_dump()) if ci else Json({})
            jeonse_ratio = (
                round(float(ci.jeonse_ratio), 2)
                if ci and ci.jeonse_ratio is not None
                else None
            )
            cur.execute(
                INSERT_SQL,
                (
                    response.session_id,
                    (ci.raw_text or "")[:10000] if ci else "",
                    response.risk_score,
                    response.risk_level,
                    Json([rf.model_dump() for rf in response.risk_factors]),
                    Json([ref.model_dump() for ref in response.references]),
                    response.summary[:2000],
                    ci.estimated_sale_price if ci else None,
                    jeonse_ratio,
                    contract_info_json,
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
        elif score >= 50:
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


def _is_successful_diagnosis(response: DiagnosisResponse) -> bool:
    if response.risk_level == "재업로드 필요":
        return False
    if any(trace == "contract_supervisor:missing_basic_info" for trace in response.agent_trace):
        return False
    return not any(rf.factor_id == "SUPERVISOR-MISSING-BASIC" for rf in response.risk_factors)
