"""LangGraph 기반 에이전트 그래프.

다이어그램 시퀀스를 두 개의 StateGraph로 구현합니다:

  ContractDiagnosisGraph (왼쪽 경로):
    contract_supervisor → model_agent → special_terms_agent → report_writer

  ChatGraph (오른쪽 경로):
    chat_supervisor → [diagnosis_json_reader →] legal_agent | general_agent → answer_writer

각 빌더 함수는 컴파일된 LangGraph를 반환하며,
diagnosis_service.py 및 chat_agents.py에서 ainvoke() 로 사용됩니다.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from rag_server.config import Settings
from rag_server.core.rag_pipeline import RAGPipeline
from rag_server.models.schemas import ContractInfo, DiagnosisResponse, RiskFactor
from rag_server.services.diagnosis_agents import (
    ContractSupervisor,
    ModelAgent,
    ReportWriter,
    SpecialTermsAgent,
    SupervisorDecision,
)
from rag_server.services.chat_agents import (
    AnswerWriter,
    ChatSupervisor,
    DiagnosisJsonReader,
    GeneralAgent,
    LegalAgent,
)
from rag_server.services.market_price_service import MarketPriceService


# ── 계약서 진단 State ──────────────────────────────────────────────────

class DiagnosisState(TypedDict, total=False):
    session_id: str
    contract_info: ContractInfo
    supervisor_decision: SupervisorDecision
    model_risks: list[RiskFactor]
    terms_risks: list[RiskFactor]
    response: DiagnosisResponse


# ── 채팅 State ─────────────────────────────────────────────────────────

class ChatState(TypedDict, total=False):
    session_id: str
    message: str
    history: list[dict[str, Any]]
    question_type: str                    # "legal" | "general"
    needs_diagnosis_context: bool
    diagnosis_context: dict[str, Any]
    rag_result: dict[str, Any]
    response: dict[str, Any]             # ChatResponse.model_dump()


# ── 계약서 진단 그래프 ─────────────────────────────────────────────────

def build_contract_diagnosis_graph(settings: Settings):
    """
    ContractSupervisor → ModelAgent → SpecialTermsAgent → ReportWriter

    조건 분기:
      supervisor.can_diagnose=True  → model_agent → special_terms_agent → report_writer
      supervisor.can_diagnose=False → report_writer (즉시 재업로드 필요 응답)
    """
    try:
        market_service: MarketPriceService | None = MarketPriceService(settings)
    except Exception:
        market_service = None

    # ── 노드 ───────────────────────────────────────────────────────────

    def contract_supervisor_node(state: DiagnosisState) -> dict:
        decision = ContractSupervisor().inspect(state["contract_info"])
        return {"supervisor_decision": decision}

    def model_agent_node(state: DiagnosisState) -> dict:
        risks = ModelAgent(market_service).analyze(state["contract_info"])
        return {"model_risks": risks}

    def special_terms_agent_node(state: DiagnosisState) -> dict:
        risks = SpecialTermsAgent().analyze(state["contract_info"])
        return {"terms_risks": risks}

    def report_writer_node(state: DiagnosisState) -> dict:
        response = ReportWriter().build(
            session_id=state["session_id"],
            contract_info=state["contract_info"],
            supervisor=state["supervisor_decision"],
            model_risks=state.get("model_risks") or [],
            terms_risks=state.get("terms_risks") or [],
        )
        return {"response": response}

    # ── 라우팅 ─────────────────────────────────────────────────────────

    def route_after_supervisor(state: DiagnosisState) -> str:
        decision: SupervisorDecision = state["supervisor_decision"]
        return "model_agent" if decision.can_diagnose else "report_writer"

    # ── 그래프 조립 ────────────────────────────────────────────────────

    workflow = StateGraph(DiagnosisState)
    workflow.add_node("contract_supervisor",  contract_supervisor_node)
    workflow.add_node("model_agent",          model_agent_node)
    workflow.add_node("special_terms_agent",  special_terms_agent_node)
    workflow.add_node("report_writer",        report_writer_node)

    workflow.set_entry_point("contract_supervisor")
    workflow.add_conditional_edges(
        "contract_supervisor",
        route_after_supervisor,
        {
            "model_agent":   "model_agent",
            "report_writer": "report_writer",
        },
    )
    workflow.add_edge("model_agent",         "special_terms_agent")
    workflow.add_edge("special_terms_agent", "report_writer")
    workflow.add_edge("report_writer",       END)

    return workflow.compile()


# ── 채팅 그래프 ────────────────────────────────────────────────────────

def build_chat_graph(settings: Settings, rag_pipeline: RAGPipeline):
    """
    ChatSupervisor → DiagnosisJsonReader(필요 시) → LegalAgent | GeneralAgent → AnswerWriter

    조건 분기:
      question_type=legal   → [diagnosis_json_reader →] legal_agent → answer_writer
      question_type=general → general_agent → answer_writer
    """

    reader        = DiagnosisJsonReader(settings)
    legal_agent   = LegalAgent(rag_pipeline)
    general_agent = GeneralAgent()
    writer        = AnswerWriter()
    supervisor    = ChatSupervisor()

    # ── 노드 ───────────────────────────────────────────────────────────

    def chat_supervisor_node(state: ChatState) -> dict:
        """입력 타입 판단 + 진단 컨텍스트 로드."""
        diagnosis_context = reader.read_latest(state["session_id"])
        decision = supervisor.classify(
            message=state["message"],
            has_diagnosis_context=diagnosis_context is not None,
        )
        return {
            "question_type":            decision.question_type,
            "needs_diagnosis_context":  decision.needs_diagnosis_context,
            "diagnosis_context":        diagnosis_context,
        }

    async def legal_agent_node(state: ChatState) -> dict:
        """법률·계약 질문 — RAG + GraphDB 검색."""
        context = state.get("diagnosis_context") if state.get("needs_diagnosis_context") else None
        result = await legal_agent.answer(
            session_id=state["session_id"],
            message=state["message"],
            history=state.get("history") or [],
            diagnosis_context=context,
        )
        return {"rag_result": result}

    def general_agent_node(state: ChatState) -> dict:
        """일반 안내 질문 — RAG 없이 고정 답변."""
        answer = general_agent.answer(state["message"])
        return {"rag_result": {"answer": answer, "references": [], "graph_context": []}}

    def answer_writer_node(state: ChatState) -> dict:
        """최종 ChatResponse 조립."""
        rag    = state.get("rag_result") or {}
        qt     = state.get("question_type", "general")

        trace = ["supervisor:question", f"chat_supervisor:{qt}"]
        if state.get("needs_diagnosis_context") and state.get("diagnosis_context"):
            trace.append("diagnosis_json_reader")
        trace.append("legal_agent" if qt == "legal" else "general_agent")
        if qt == "legal":
            trace.append("rag_vector_graph")
        trace.append("answer_writer")

        response = writer.build(
            session_id=state["session_id"],
            answer=rag.get("answer", ""),
            references=rag.get("references") or [],
            graph_context=rag.get("graph_context") or [],
            agent_trace=trace,
        )
        return {"response": response.model_dump()}

    # ── 라우팅 ─────────────────────────────────────────────────────────

    def route_after_supervisor(state: ChatState) -> str:
        return "legal_agent" if state.get("question_type") == "legal" else "general_agent"

    # ── 그래프 조립 ────────────────────────────────────────────────────

    workflow = StateGraph(ChatState)
    workflow.add_node("chat_supervisor",  chat_supervisor_node)
    workflow.add_node("legal_agent",      legal_agent_node)
    workflow.add_node("general_agent",    general_agent_node)
    workflow.add_node("answer_writer",    answer_writer_node)

    workflow.set_entry_point("chat_supervisor")
    workflow.add_conditional_edges(
        "chat_supervisor",
        route_after_supervisor,
        {
            "legal_agent":   "legal_agent",
            "general_agent": "general_agent",
        },
    )
    workflow.add_edge("legal_agent",    "answer_writer")
    workflow.add_edge("general_agent",  "answer_writer")
    workflow.add_edge("answer_writer",  END)

    return workflow.compile()
