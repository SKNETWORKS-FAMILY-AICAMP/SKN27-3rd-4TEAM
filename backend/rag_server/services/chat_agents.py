"""Chat agents for legal/general questions.

This module follows the question side of the sequence diagram:

supervisor -> chat_supervisor -> diagnosis_json_reader -> legal_agent/general_agent
-> answer_writer
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg2
import psycopg2.extras

from rag_server.config import Settings
from rag_server.core.rag_pipeline import RAGPipeline
from rag_server.models.schemas import ChatResponse
from rag_server.services.contract_parser import ContractParser


LEGAL_KEYWORDS = [
    "전세",
    "월세",
    "임대차",
    "계약",
    "보증금",
    "근저당",
    "등기",
    "특약",
    "보증보험",
    "전입신고",
    "확정일자",
    "대항력",
    "우선변제",
    "법",
    "조항",
    "판례",
    "위험",
]

CONTRACT_CONTEXT_KEYWORDS = [
    "이 계약",
    "내 계약",
    "업로드",
    "방금",
    "진단",
    "위험한",
    "문제",
    "특약",
    "근저당",
    "보증금",
    "이 문서",
]


@dataclass
class ChatDecision:
    question_type: str
    needs_diagnosis_context: bool


class ChatSupervisor:
    """Routes the user question to legal or general chat handling."""

    def classify(self, message: str, has_diagnosis_context: bool) -> ChatDecision:
        stripped = message.strip()
        wants_context = has_diagnosis_context and any(token in stripped for token in CONTRACT_CONTEXT_KEYWORDS)
        is_legal = wants_context or any(token in stripped for token in LEGAL_KEYWORDS)
        return ChatDecision(
            question_type="legal" if is_legal else "general",
            needs_diagnosis_context=wants_context,
        )


class DiagnosisJsonReader:
    """Reads the latest saved diagnosis JSON for the current session."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def read_latest(self, session_id: str) -> dict[str, Any] | None:
        try:
            conn = psycopg2.connect(
                host=self._settings.DB_HOST,
                port=self._settings.DB_PORT,
                database=self._settings.DB_NAME,
                user=self._settings.DB_USER,
                password=self._settings.DB_PASSWORD,
            )
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT id, session_id, input_text, risk_score, risk_level, risk_factors,
                       rag_references, result_summary, created_at
                FROM diagnosis_logs
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id,),
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
        except Exception as exc:
            print(f"[DiagnosisJsonReader] failed to load diagnosis context: {exc}")
            return None

        if not row:
            return None
        item = dict(row)
        input_text = str(item.get("input_text") or "")
        item["contract_info"] = ContractParser.from_text(input_text).model_dump() if input_text else {}
        return item


class LegalAgent:
    """Answers legal and contract-related questions through RAG."""

    def __init__(self, rag_pipeline: RAGPipeline):
        self._rag = rag_pipeline

    async def answer(
        self,
        session_id: str,
        message: str,
        history: list[dict[str, Any]],
        diagnosis_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        question = self._build_question(message, diagnosis_context)
        return await self._rag.chat(
            session_id=session_id,
            question=question,
            history=history,
        )

    def _build_question(self, message: str, diagnosis_context: dict[str, Any] | None) -> str:
        if not diagnosis_context:
            return message

        info = diagnosis_context.get("contract_info") or {}
        risks = diagnosis_context.get("risk_factors") or []
        risk_lines = [
            f"- {risk.get('category', '위험')}: {risk.get('description', '')}"
            for risk in risks[:6]
        ]
        context = "\n".join(
            [
                "[저장된 계약서 진단 결과]",
                f"주소: {info.get('address') or '-'}",
                f"보증금: {info.get('deposit_amount') or '-'}만원",
                f"위험도: {diagnosis_context.get('risk_score')}점 / {diagnosis_context.get('risk_level')}",
                f"요약: {diagnosis_context.get('result_summary') or '-'}",
                "위험요소:",
                *risk_lines,
            ]
        )
        return f"{context}\n\n[사용자 질문]\n{message}"


class GeneralAgent:
    """Handles non-legal general chat without RAG."""

    def answer(self, message: str) -> str:
        return (
            "계약서 업로드, 전세 위험 진단, 법률/보증보험/근저당 관련 질문을 도와드릴 수 있습니다. "
            "계약서 파일을 올리거나 궁금한 내용을 구체적으로 입력해 주세요."
        )


class AnswerWriter:
    """Builds the final ChatResponse."""

    def build(
        self,
        session_id: str,
        answer: str,
        references: list[Any] | None = None,
        graph_context: list[Any] | None = None,
        agent_trace: list[str] | None = None,
    ) -> ChatResponse:
        return ChatResponse(
            session_id=session_id,
            answer=answer,
            references=references or [],
            graph_context=graph_context or [],
            agent_trace=agent_trace or [],
        )


class ChatAgentService:
    """Orchestrates chat via LangGraph ChatGraph.

    그래프 흐름:
      chat_supervisor → legal_agent | general_agent → answer_writer
    """

    def __init__(self, settings: Settings, rag_pipeline: RAGPipeline):
        self._settings = settings
        self._rag = rag_pipeline
        # LangGraph: ChatGraph 를 서비스 생성 시 한 번만 컴파일
        from rag_server.services.graph_agents import ChatState, build_chat_graph
        self._graph = build_chat_graph(settings, rag_pipeline)
        self._ChatState = ChatState

    async def answer(
        self,
        session_id: str,
        message: str,
        history: list[dict[str, Any]],
    ) -> ChatResponse:
        # LangGraph ChatGraph 실행
        # chat_supervisor → [legal_agent | general_agent] → answer_writer
        initial_state: dict[str, Any] = {
            "session_id": session_id,
            "message":    message,
            "history":    history,
        }
        final_state = await self._graph.ainvoke(initial_state)
        response_dict: dict[str, Any] = final_state.get("response") or {}
        return ChatResponse(**response_dict)
