"""
chatbot — 전세계약 상담 페르소나 챗봇

역할:
  - 진단 결과 기반 후속 상담 (진단 데이터가 있을 때)
  - 일반 전세 관련 질문 상담 (진단 없이도 가능)
  - 법률 질문 감지 시 legal_agent 호출하여 판례 근거 포함

페르소나: 친근하고 전문적인 전세 상담사
"""

import json
import os
import glob
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from backend.config import get_llm
from backend.agents.legal_agent import consult as legal_consult, extract_issues


REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatSession(BaseModel):
    session_id: str = ""
    diagnosis_data: dict = Field(default_factory=dict)
    messages: list[ChatMessage] = Field(default_factory=list)


# ── 진단 JSON 로드 ──────────────────────────────────────

def load_latest_report() -> dict | None:
    pattern = os.path.join(REPORT_DIR, "report_*.json")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        return None
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


def load_report_by_session(session_id: str) -> dict | None:
    filepath = os.path.join(REPORT_DIR, f"report_{session_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 법률 질문 감지 ──────────────────────────────────────

CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """사용자 질문이 법률 상담(판례, 법조문, 법적 권리, 소송 등)을 필요로 하는지 판단하세요.
"legal" 또는 "general" 중 하나만 응답하세요.

legal: 판례, 법조문, 법적 권리/의무, 소송/경매 절차, 보증금 반환 소송 등
general: 일반 전세 상식, 진단 결과 설명, 계약 팁, 체크리스트 등"""),
    ("human", "{question}")
])


def classify_question(question: str) -> str:
    llm = get_llm(temperature=0.0)
    chain = CLASSIFY_PROMPT | llm
    response = chain.invoke({"question": question})
    result = response.content.strip().lower()
    return "legal" if "legal" in result else "general"


# ── 일반 상담 프롬프트 ──────────────────────────────────

GENERAL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 '안전계약' 전세 상담 AI입니다.
친근하지만 전문적인 어조로 전세 관련 상담을 제공합니다.

페르소나 규칙:
- 이름: 안전이
- 존댓말을 사용하되 딱딱하지 않게
- 임차인 보호 관점에서 실질적 조언을 제공
- 어려운 법률 용어는 쉽게 풀어서 설명
- 확실하지 않은 내용은 솔직히 "정확한 확인을 위해 전문가 상담을 권합니다"라고 안내
- 3~5문장으로 간결하게 답변
- 본 서비스는 법률 자문이 아닌 정보 제공 목적임을 필요시 안내

{diagnosis_context}"""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{question}")
])

LEGAL_ENHANCED_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 '안전계약' 전세 상담 AI입니다.
판례와 법조문 근거를 바탕으로 법률 정보를 제공합니다.

페르소나 규칙:
- 이름: 안전이
- 판례 인용 시 사건번호를 명시
- 관련 법조문을 함께 안내
- 임차인이 취할 수 있는 구체적 행동을 권고
- 4~6문장으로 답변
- "법률 자문이 아닌 참고 정보"임을 마지막에 안내

{diagnosis_context}"""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", """사용자 질문: {question}

관련 판례 검색 결과:
{legal_references}""")
])


# ── 진단 컨텍스트 포맷 ──────────────────────────────────

def format_diagnosis(data: dict) -> str:
    if not data:
        return "현재 진단 데이터가 없습니다. 일반 전세 상담으로 답변합니다."

    ui = data.get("user_info", {})
    lines = [
        "=== 현재 진단 결과 ===",
        f"주소: {ui.get('address', '미상')}",
        f"전세금: {ui.get('deposit', '미상')}만원",
        f"위험등급: {ui.get('risk_level', '미상')} ({ui.get('risk_score', 0)}점)",
    ]

    if ui.get("jeonse_ratio"):
        lines.append(f"전세가율: {ui['jeonse_ratio']}%")
    if ui.get("predicted_deposit_2027"):
        lines.append(f"2027 예측 전세금: {ui['predicted_deposit_2027']}만원")

    price_diag = data.get("price_diagnosis", "")
    if price_diag:
        lines.append(f"가격 진단: {price_diag[:150]}")

    terms = data.get("special_terms", [])
    if terms:
        lines.append(f"\n특약 {len(terms)}건:")
        for i, t in enumerate(terms, 1):
            lines.append(f"  {i}. [{t.get('risk_level', '')}] {t.get('term_text', '')[:50]}")

    final = data.get("final_report", "")
    if final:
        lines.append(f"\n최종 리포트: {final[:200]}")

    return "\n".join(lines)


# ── 챗봇 응답 ───────────────────────────────────────────

def chat(question: str, session: ChatSession) -> tuple[str, list[dict]]:
    """
    챗봇 응답 생성.
    Returns: (answer_text, sources_list)
    sources_list: [{"type": "case"|"law", "text": "..."}]
    """
    diagnosis_ctx = format_diagnosis(session.diagnosis_data)

    # 대화 이력
    chat_history = []
    for msg in session.messages[-10:]:
        if msg.role == "user":
            chat_history.append(HumanMessage(content=msg.content))
        else:
            chat_history.append(AIMessage(content=msg.content))

    # 질문 분류
    q_type = classify_question(question)
    sources = []

    if q_type == "legal":
        # 법률 질문 → legal_agent로 판례 검색
        legal_resp = legal_consult(question)

        # 판례 근거 포맷
        ref_lines = []
        for ref in legal_resp.references:
            ref_lines.append(
                f"■ {ref.court} {ref.case_id} ({ref.date})\n"
                f"  {ref.summary}\n"
                f"  법조문: {', '.join(ref.laws) if ref.laws else '없음'}"
            )
            sources.append({"type": "case", "text": f"⚖️ {ref.court} {ref.case_id}"})
            for law in ref.laws:
                if law:
                    sources.append({"type": "law", "text": f"📜 {law}"})

        legal_refs = "\n\n".join(ref_lines) if ref_lines else "관련 판례 없음"

        llm = get_llm(temperature=0.3)
        chain = LEGAL_ENHANCED_PROMPT | llm
        response = chain.invoke({
            "diagnosis_context": diagnosis_ctx,
            "chat_history": chat_history,
            "question": question,
            "legal_references": legal_refs,
        })
    else:
        # 일반 질문
        llm = get_llm(temperature=0.4)
        chain = GENERAL_PROMPT | llm
        response = chain.invoke({
            "diagnosis_context": diagnosis_ctx,
            "chat_history": chat_history,
            "question": question,
        })

    answer = response.content.strip()

    # 대화 이력 저장
    session.messages.append(ChatMessage(role="user", content=question))
    session.messages.append(ChatMessage(role="assistant", content=answer))

    return answer, sources


def create_session(session_id: str = None) -> ChatSession:
    if session_id:
        data = load_report_by_session(session_id)
    else:
        data = load_latest_report()

    return ChatSession(
        session_id=session_id or "",
        diagnosis_data=data or {},
    )
