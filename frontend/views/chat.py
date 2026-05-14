"""상담 챗 (메인) — 진단 결과 + RAG 스타일 챗봇."""

import os
from html import escape

import requests
import streamlit as st
import streamlit.components.v1 as components
from utils.components import (
    render_status_pill,
    law_banner,
    section_divider,
)

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")


def upload_contract_to_backend(uploaded_file) -> dict:
    """임대차계약서 파일을 백엔드 텍스트 추출 API로 전송한다."""
    response = requests.post(
        f"{BACKEND_BASE_URL}/api/v1/contracts/upload",
        files={
            "file": (
                uploaded_file.name,
                uploaded_file.getvalue(),
                uploaded_file.type or "application/octet-stream",
            )
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def query_rag_backend(question: str) -> dict | None:
    """FastAPI RAG 챗봇 API에 질문을 보내고 실패하면 None을 반환한다."""
    session_id = st.session_state.setdefault("chat_session_id", "streamlit-session")
    history = [
        {"role": message["role"], "content": message["content"]}
        for message in st.session_state.get("messages", [])
        if message.get("role") in {"user", "assistant"}
    ][-8:]
    try:
        response = requests.post(
            f"{BACKEND_BASE_URL}/api/v1/chat/query",
            json={"session_id": session_id, "message": question, "history": history},
            timeout=8,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    payload = response.json()
    references = payload.get("references", [])
    sources = [
        reference.get("title") or reference.get("source_id") or "RAG 검색 결과"
        for reference in references
        if isinstance(reference, dict)
    ]
    return {"answer": payload.get("answer", ""), "sources": sources}


def build_contract_doc_context(result: dict) -> dict:
    """업로드 API 응답을 챗봇 문서 컨텍스트 형태로 변환한다."""
    fields = result.get("parsed_fields", {})
    summary_items = []
    if fields.get("address"):
        summary_items.append(f"주소: {fields['address']}")
    if fields.get("deposit_amount") is not None:
        summary_items.append(f"보증금: {fields['deposit_amount']:,}만원")
    if fields.get("monthly_rent") is not None:
        summary_items.append(f"월세: {fields['monthly_rent']:,}만원")
    if fields.get("contract_start") or fields.get("contract_end"):
        summary_items.append(f"계약기간: {fields.get('contract_start') or '?'} ~ {fields.get('contract_end') or '?'}")
    if fields.get("special_terms"):
        summary_items.append("특약사항 추출됨")

    summary = " · ".join(summary_items) if summary_items else "계약서 텍스트 추출은 완료됐지만 핵심 필드는 추가 확인이 필요합니다."
    keywords = [value for value in fields.values() if isinstance(value, str) and value][:5]
    return {
        "title": result.get("filename", "임대차계약서"),
        "kind": "임대차계약서",
        "summary": summary,
        "keywords": keywords,
        "contract_id": result.get("contract_id"),
        "extracted_text": result.get("extracted_text", ""),
        "parsed_fields": fields,
    }


# ─── 데모 RAG 응답 ──────────────────────────────────────
DEMO_REPLIES = [
    {
        "q_match": ["근저당", "담보", "대출"],
        "answer": (
            "<b>네, 가장 큰 위험 요소입니다.</b><br/><br/>"
            "현재 매물 등기부등본상 <b>근저당권 ₩2.1억 (○○저축은행, 2022.11 설정)</b>이 잡혀 있고, "
            "보증금 ₩2.5억과 합산하면 <b>총 부담률 184%</b>로 매매가를 초과합니다. "
            "경매 시 선순위 채권이 우선 변제되어 임차인이 회수할 잔여분이 거의 없을 가능성이 높습니다.<br/><br/>"
            "<b>대안:</b> 잔금일까지 근저당 말소 특약을 반드시 명시하고, 미말소 시 계약을 무효로 한다는 조항을 추가하세요. "
            "유사 종로구 47건 분석 결과 이 특약을 포함했을 때 회수율이 76%까지 상승했습니다."
        ),
        "sources": [
            "📄 등기부등본 p.3",
            "⚖️ 주택임대차보호법 제3조의2",
            "⚖️ 대법원 2022다48327",
            "📝 종로 명륜동 '23년 사례",
        ],
    },
    {
        "q_match": ["전세가율", "시세", "위험"],
        "answer": (
            "<b>전세가율 91%로 깡통전세 임계치를 초과했습니다.</b><br/><br/>"
            "이 매물의 보증금은 ₩2.5억이고, 종로구 명륜2가 동일 면적(42㎡) 매물의 평균 매매가는 ₩2.75억입니다. "
            "전세가율이 80%를 넘으면 일반적으로 위험, 90%를 넘으면 사실상 깡통전세로 분류됩니다.<br/><br/>"
            "<b>HUG 전세보증보험은 전세가율 90% 초과 시 가입이 거절될 수 있습니다.</b> "
            "보증보험 가입이 안 된다면 이 매물은 피하시는 것을 권합니다."
        ),
        "sources": [
            "🏠 국토부 실거래가 2025",
            "⚖️ HUG 전세보증보험 약관 제10조",
            "📊 종로구 평균 전세가율 통계",
        ],
    },
    {
        "q_match": ["특약", "계약서"],
        "answer": (
            "<b>다음 3가지 특약을 반드시 추가하세요:</b><br/><br/>"
            "① <b>근저당 말소 조건부 무효 특약</b> — 잔금일까지 등기부상 근저당(₩2.1억) 말소 미이행 시 본 계약은 무효로 하며, "
            "임대인은 즉시 보증금을 반환한다.<br/>"
            "② <b>권리변동 통지 의무</b> — 계약 후 등기부에 새로운 권리(근저당·가압류·신탁 등)가 추가되는 경우 임대인은 즉시 통지하고 "
            "임차인은 계약을 해지할 권리를 갖는다.<br/>"
            "③ <b>전입신고·확정일자 보장</b> — 임대인은 임차인의 전입신고와 확정일자 취득에 협조하며, 이를 방해하는 일체의 행위를 하지 않는다."
        ),
        "sources": [
            "📋 주택임대차표준계약서",
            "⚖️ 주택임대차보호법 제10조",
            "📝 변호사 권장 특약 가이드",
        ],
    },
]

DEFAULT_REPLY = {
    "answer": (
        "죄송합니다. 아직 답변하기 어려운 질문입니다.<br/><br/>"
        "구체적으로 어떤 부분을 알려드릴까요? 위 빠른 질문을 이용하시거나 다시 질문해 주세요."
    ),
    "sources": [],
}


LEVEL_KO = {"danger": "위험", "caution": "주의", "safe": "안전"}


def reset_chat_state() -> None:
    """상담 기준 자료가 바뀔 때 기존 메시지를 초기화한다."""
    st.session_state.pop("messages", None)


def render_chat_messages(messages: list[dict]) -> None:
    """채팅 메시지를 한 화면 안의 넓은 로그 패널로 렌더링한다."""
    rendered_messages = []
    for message in messages:
        if message["role"] == "user":
            rendered_messages.append(f'<div class="chat-q"><b>나</b><span>{escape(message["content"])}</span></div>')
            continue

        refs = ""
        if message.get("sources"):
            chips = "".join(f'<span class="ref">{escape(source)}</span>' for source in message["sources"])
            refs = f'<div class="rag-src"><b>근거 자료</b>{chips}</div>'
        rendered_messages.append(f'<div class="chat-a">{message["content"]}{refs}</div>')

    st.markdown(
        f"""
        <div class="chat-log-panel">
          {''.join(rendered_messages)}
          <div id="chat-bottom-anchor"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    components.html(
        """
        <script>
          const anchor = window.parent.document.getElementById("chat-bottom-anchor");
          if (anchor) {
            const panel = anchor.closest(".chat-log-panel");
            if (panel) {
              panel.scrollTop = panel.scrollHeight;
            }
            anchor.scrollIntoView({ behavior: "smooth", block: "end" });
          }
        </script>
        """,
        height=0,
    )


def quick_questions_for(mode: str, ctx: dict | None) -> list[str]:
    """모드(default/doc/property)에 맞는 빠른 질문 4개 생성."""
    if mode == "doc" and ctx:
        kind = ctx.get("kind", "")
        keywords = ctx.get("keywords", [])
        kw1 = keywords[0] if len(keywords) > 0 else "핵심 주제"
        if kind == "판례":
            return [
                "핵심 판시 사항 요약해줘",
                f"{kw1} 관련 법리가 뭐야?",
                "내 매물에 어떻게 적용되나요?",
                "유사한 다른 판례가 있나요?",
            ]
        if kind == "피해 사례":
            return [
                "주요 위험 신호 알려줘",
                f"{kw1} 예방 체크리스트는?",
                "내 매물과 비교해줘",
                "관련 구제 절차는?",
            ]
        if kind == "특약":
            return [
                "이 특약을 그대로 써도 되나요?",
                "법적 효력 근거가 뭔가요?",
                "내 계약서 어디에 넣나요?",
                "위반 시 보호받는 절차는?",
            ]
        return [
            "핵심 요지를 알려줘",
            f"{kw1}에 대해 더 자세히",
            "내 매물에 어떻게 적용되나요?",
            "인용할 만한 조항 있나요?",
        ]

    if mode == "property" and ctx:
        level = ctx.get("level", "")
        first_risk = ctx["risks"][0][0] if ctx.get("risks") else "위험 신호"
        if level == "danger":
            return [
                f"{first_risk} — 왜 위험한가요?",
                "이 매물 계약을 포기해야 할까요?",
                "보증보험 가입 가능한가요?",
                "어떤 특약을 추가해야 안전한가요?",
            ]
        if level == "caution":
            return [
                f"{first_risk} 자세히 알려줘",
                "어떤 특약이 필요한가요?",
                "안전 신호도 있나요?",
                "계약 진행해도 될까요?",
            ]
        return [
            "이 매물 정말 안전한가요?",
            "추가로 확인할 항목은?",
            "계약 시 주의사항은?",
            "보증보험 가입 조건 알려줘",
        ]

    # default
    return [
        "근저당이 왜 문제인가요?",
        "특약 문구 예시 보여줘",
        "HUG 가입 조건 알려줘",
        "경매 절차 더 설명해줘",
    ]


def _badge(text: str) -> str:
    return (
        "<div style='background:var(--blue-soft);border-radius:8px;"
        "padding:8px 12px;margin-bottom:10px;font-size:12px;color:var(--blue);font-weight:700'>"
        f"{text}</div>"
    )


def find_reply(
    question: str,
    ctx_doc: dict | None = None,
    ctx_prop: dict | None = None,
) -> dict:
    """질문에 대한 응답 생성. ctx_doc / ctx_prop 우선순위로 근거 자료를 주입."""
    # 1) 데모 키워드 매칭
    base = None
    for r in DEMO_REPLIES:
        if any(kw in question for kw in r["q_match"]):
            base = r
            break

    # 2) 문서 컨텍스트 우선
    if ctx_doc:
        title = ctx_doc.get("title", "")
        kind = ctx_doc.get("kind", "")
        summary = ctx_doc.get("summary", "")
        keywords = ctx_doc.get("keywords", [])
        source_chip = f"📄 {title}"
        badge = _badge(f"📎 {title} ({kind}) 문서 기반 답변")
        if base:
            return {
                "answer": badge + base["answer"],
                "sources": [source_chip] + base["sources"],
            }
        kw_text = ", ".join(keywords[:5]) if keywords else "이 문서의 핵심 주제"
        return {
            "answer": (
                badge
                + f"질문하신 내용을 <b>{title}</b> 문서를 근거로 살펴보겠습니다.<br/><br/>"
                + f"이 문서는 <b>{kw_text}</b> 를 다루고 있으며, 주요 내용은 다음과 같습니다:<br/><br/>"
                + f"<i>{summary}</i><br/><br/>"
                + "더 구체적인 부분이 궁금하시면 다음과 같이 질문해 주세요:<br/>"
                + "• 이 문서의 핵심 조항/판시 사항이 뭔가요?<br/>"
                + "• 내 매물에 어떻게 적용되나요?<br/>"
                + "• 계약서·특약에 인용할 수 있는 문구는?"
            ),
            "sources": (
                [source_chip, f"🔖 키워드: {', '.join(keywords[:4])}"]
                if keywords else [source_chip]
            ),
        }

    # 3) 매물 컨텍스트
    if ctx_prop:
        addr = ctx_prop.get("addr", "")
        score = ctx_prop.get("score", 0)
        level = ctx_prop.get("level", "")
        ratio = ctx_prop.get("ratio", "")
        hug = ctx_prop.get("hug", "")
        risks = ctx_prop.get("risks", [])
        source_chip = f"📋 매물 진단 #{ctx_prop.get('id', 0):03d}"
        badge = _badge(f"🏠 {addr} · 위험도 {score}점 ({LEVEL_KO.get(level, '')})")
        if base:
            return {
                "answer": badge + base["answer"],
                "sources": [source_chip] + base["sources"],
            }
        risk_list_html = "".join(
            f"<li><b>{r[0]}</b> ({r[1]}) — {r[3] if len(r) > 3 else ''}</li>"
            for r in risks[:5]
        )
        return {
            "answer": (
                badge
                + f"이 매물 <b>{addr}</b>은(는) 다음과 같은 진단 결과가 있습니다:<br/><br/>"
                + f"• 위험도: <b>{score}점</b> ({LEVEL_KO.get(level, '')})<br/>"
                + f"• 전세가율: <b>{ratio}</b><br/>"
                + f"• 선순위 권리: <b>{ctx_prop.get('senior', '')}</b><br/>"
                + f"• 보증보험: <b>{hug}</b><br/><br/>"
                + (f"<b>주요 위험 신호</b><ul>{risk_list_html}</ul>" if risk_list_html else "")
                + "구체적으로 어떤 위험 항목이나 대응 방법이 궁금하신가요?"
            ),
            "sources": [source_chip, f"⚠️ 위험 신호 {len(risks)}건"],
        }

    # 4) 컨텍스트 없음 — 기본
    return base or DEFAULT_REPLY


def answer_from_contract(question: str, ctx_doc: dict) -> dict:
    """업로드된 계약서 추출 결과를 기반으로 프론트에서 1차 답변을 만든다."""
    fields = ctx_doc.get("parsed_fields", {})
    special_terms = fields.get("special_terms") or "추출된 특약사항이 없습니다."
    extracted_text = ctx_doc.get("extracted_text", "")
    question_text = question.lower()

    if any(keyword in question_text for keyword in ["특약", "조항", "문구", "위험"]):
        answer = (
            "<b>업로드한 임대차계약서 기준으로 보면, 우선 특약사항을 집중 확인해야 합니다.</b><br/><br/>"
            "추출된 특약사항은 다음과 같습니다.<br/>"
            f"<div style='margin-top:8px;padding:12px;border-radius:10px;background:var(--gray-100)'>{escape(str(special_terms))}</div><br/>"
            "특약에 근저당 말소, 보증보험 가입, 권리변동 금지, 전입신고·확정일자 보장 같은 문구가 없으면 "
            "임차인 방어력이 약해질 수 있습니다. 특히 임대인에게 일방적으로 유리한 원상복구, 위약금, 보증금 반환 유예 조항은 다시 확인하는 게 좋습니다."
        )
    elif any(keyword in question_text for keyword in ["보증금", "전세금", "월세", "금액"]):
        answer = (
            "<b>계약서에서 추출된 금액 정보입니다.</b><br/><br/>"
            f"보증금: <b>{fields.get('deposit_amount', '추출 필요')}</b>만원<br/>"
            f"월세: <b>{fields.get('monthly_rent', '추출 필요')}</b>만원<br/><br/>"
            "이 금액은 다음 단계에서 주변 매매가/전세가와 비교해서 전세가율 위험 판단에 사용하면 됩니다."
        )
    elif any(keyword in question_text for keyword in ["기간", "계약기간", "시작", "종료"]):
        answer = (
            "<b>계약 기간 추출 결과입니다.</b><br/><br/>"
            f"시작일: <b>{fields.get('contract_start') or '추출 필요'}</b><br/>"
            f"종료일: <b>{fields.get('contract_end') or '추출 필요'}</b><br/><br/>"
            "계약기간이 비어 있거나 실제 합의 내용과 다르면 계약서 원문에서 다시 확인해야 합니다."
        )
    else:
        preview = escape(extracted_text[:500]) if extracted_text else "추출된 원문 미리보기가 없습니다."
        answer = (
            f"<b>{escape(ctx_doc.get('title', '임대차계약서'))}</b>를 기준으로 답변할게요.<br/><br/>"
            f"{escape(ctx_doc.get('summary', '계약서 핵심 정보가 일부 추출되었습니다.'))}<br/><br/>"
            f"<details><summary>추출 원문 일부 보기</summary><div style='margin-top:8px'>{preview}</div></details><br/>"
            "궁금한 항목을 특약, 보증금, 계약기간, 권리관계처럼 조금 더 구체적으로 물어보면 더 정확히 나눠서 설명할 수 있어요."
        )

    return {"answer": answer, "sources": [ctx_doc.get("title", "업로드 계약서")]}


def generate_chat_reply(question: str, mode: str, ctx_doc: dict | None, ctx_prop: dict | None) -> dict:
    """현재 상담 모드에 맞춰 백엔드 RAG 또는 로컬 컨텍스트 답변을 생성한다."""
    if mode == "doc" and ctx_doc:
        return answer_from_contract(question, ctx_doc)

    backend_reply = query_rag_backend(question)
    if backend_reply and backend_reply.get("answer"):
        return backend_reply

    return find_reply(question, ctx_doc=ctx_doc, ctx_prop=ctx_prop)


# ─── 화면 ──────────────────────────────────────────────
def render():
    # ─── 모드 결정 ───
    ctx_doc = st.session_state.get("chat_context_doc")
    ctx_prop = st.session_state.get("chat_context_property")
    if ctx_doc:
        mode = "doc"
    elif ctx_prop:
        mode = "property"
    else:
        mode = "default"

    # ─── 컨텍스트 배너 ───
    if mode == "doc":
        head_l, head_r = st.columns([5, 1])
        with head_l:
            st.markdown(
                f"""
                <div style="background:var(--blue-soft);border:1px solid #cfe1ff;border-radius:12px;
                            padding:12px 16px;margin-bottom:12px;font-size:13px;color:var(--gray-900)">
                  📎 <b>{ctx_doc['title']}</b>
                  <span style="background:var(--blue);color:#fff;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:800;margin-left:8px">{ctx_doc['kind']}</span>
                  <div style="color:var(--gray-700);font-size:12px;margin-top:4px;line-height:1.5">{ctx_doc['summary']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with head_r:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            if st.button("× 자료 해제", key="clear_ctx_doc", use_container_width=True):
                del st.session_state.chat_context_doc
                reset_chat_state()
                st.rerun()
    elif mode == "property":
        level_color = {"danger": "var(--red)", "caution": "var(--amber)", "safe": "var(--green)"}.get(ctx_prop["level"], "var(--gray-500)")
        level_bg = {"danger": "var(--red-soft)", "caution": "var(--amber-soft)", "safe": "var(--green-soft)"}.get(ctx_prop["level"], "var(--gray-100)")
        head_l, head_r = st.columns([5, 1])
        with head_l:
            st.markdown(
                f"""
                <div style="background:{level_bg};border:1px solid {level_color};border-radius:12px;
                            padding:12px 16px;margin-bottom:12px;font-size:13px;color:var(--gray-900)">
                  🏠 <b>{ctx_prop['addr']}</b>
                  <span style="background:{level_color};color:#fff;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:800;margin-left:8px">
                    {ctx_prop['score']}점 · {LEVEL_KO.get(ctx_prop['level'], '')}
                  </span>
                  <div style="color:var(--gray-700);font-size:12px;margin-top:6px;line-height:1.5">
                    전세 {ctx_prop['deposit']} · {ctx_prop['area']} · {ctx_prop['year']} ·
                    전세가율 <b>{ctx_prop['ratio']}</b> · 보증보험 <b>{ctx_prop['hug']}</b>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with head_r:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            if st.button("× 매물 해제", key="clear_ctx_prop", use_container_width=True):
                del st.session_state.chat_context_property
                reset_chat_state()
                st.rerun()

    # 상단 법령 개정 알림
    law_banner(
        "<b>2026.3.1 주택임대차보호법 제8조 개정</b> · 소액임차인 우선변제 한도가 "
        "₩1억 → <b>₩1.5억</b>으로 상향",
        pill="법령 개정",
    )

    # ─── 헤더 (모드별 제목/서브) ───
    if mode == "doc":
        eyebrow = f"상담 챗 · {ctx_doc['kind']} 자료 기반"
        title = "선택한 자료 기반 AI 상담"
        head_sub = (
            f"<b>{ctx_doc['title']}</b> 문서를 근거로 질문에 답합니다. "
            "모든 답변은 출처를 함께 보여드립니다."
        )
    elif mode == "property":
        eyebrow = f"상담 챗 · {ctx_prop['addr']} · 분석 #{ctx_prop['id']:03d}"
        title = "내 매물 기반 AI 상담"
        head_sub = (
            f"진단된 매물(<b>{ctx_prop['addr']}</b>)의 위험 항목·계약 정보를 근거로 답변합니다."
        )
    else:
        eyebrow = "상담 챗 · 종로구 명륜2가 35-12 · 분석 #A1F-203"
        title = "내 자료 기반 AI 상담"
        head_sub = "업로드한 등기부등본·계약서를 근거로 질문에 답합니다. 모든 답변은 출처를 함께 보여드립니다."

    col_h1, col_h2 = st.columns([3, 1.4])
    with col_h1:
        st.markdown(
            f'<div style="font-size:12px;font-weight:700;color:var(--gray-500);'
            f'letter-spacing:.04em;margin-bottom:6px">{eyebrow}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"# {title}")
        st.markdown(
            f'<p style="color:var(--gray-500);font-size:14px;margin-top:-8px">{head_sub}</p>',
            unsafe_allow_html=True,
        )
    with col_h2:
        st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
        if mode == "property":
            render_status_pill(ctx_prop["level"], ctx_prop["score"], f"{LEVEL_KO[ctx_prop['level']]} 매물")
        elif mode == "default":
            render_status_pill("danger", 78, "깡통전세 위험")
        # doc 모드는 상태 핀 생략 (배너로 이미 표시)

    section_divider()

    # ─── 자료 업로드 (default 모드만) ───
    if mode == "default":
        st.markdown("### 📎 내 자료")
        st.markdown(
            '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
            "업로드한 자료를 기반으로 챗봇이 답변합니다.</p>",
            unsafe_allow_html=True,
        )

        info_l, info_r = st.columns([2, 1])
        with info_l:
            st.text_input(
                "주소",
                value="서울 종로구 명륜2가 35-12 한빛빌라 302호",
            )
        with info_r:
            st.number_input("보증금 (만원)", value=25000, step=500, format="%d")

        pdf_l, pdf_r = st.columns(2)
        with pdf_l:
            st.file_uploader(
                "등기부등본 PDF",
                type=["pdf"],
                help="등기소·정부24에서 발급한 PDF를 첨부하세요.",
            )
        with pdf_r:
            lease_contract_file = st.file_uploader(
                "임대차계약서 PDF",
                type=["pdf", "docx", "txt"],
                help="특약 조항이 모두 포함된 임대차계약서를 업로드해 주세요.",
            )

        if lease_contract_file and st.button("임대차계약서 텍스트 추출", type="primary", use_container_width=True):
            try:
                with st.spinner("임대차계약서 내용을 추출하는 중입니다..."):
                    upload_result = upload_contract_to_backend(lease_contract_file)
                st.session_state.chat_context_doc = build_contract_doc_context(upload_result)
                reset_chat_state()
                st.success("계약서 텍스트 추출이 완료되었습니다. 이제 이 계약서를 기준으로 질문할 수 있어요.")
                st.rerun()
            except requests.exceptions.ConnectionError:
                st.error("백엔드 서버에 연결할 수 없습니다. FastAPI 서버를 먼저 실행해 주세요.")
                st.code("cd backend\n..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --reload", language="powershell")
            except requests.exceptions.HTTPError as exc:
                detail = exc.response.text if exc.response is not None else str(exc)
                st.error(f"업로드 API 오류: {detail}")
            except Exception as exc:
                st.error(f"계약서 처리 중 오류가 발생했습니다: {exc}")

        if st.session_state.get("chat_context_doc"):
            st.markdown(
                f"""
                <div style="background:var(--green-soft);border:1px solid #b8ead9;border-radius:12px;
                            padding:12px 14px;margin-top:10px;font-size:13px;color:#005a3f">
                  ✓ 계약서 업로드 완료 · <b>{st.session_state.chat_context_doc['title']}</b> 기준으로 AI 상담을 진행합니다.
                </div>
                """,
                unsafe_allow_html=True,
            )

        section_divider()

    # ─── 챗봇 섹션 (모드별 서브타이틀/빠른질문) ───
    st.markdown("### 💬 궁금한 점을 물어보세요")
    if mode == "doc":
        sub = f"<b>{ctx_doc['title']}</b> ({ctx_doc['kind']}) 자료를 근거로 답변합니다."
    elif mode == "property":
        sub = f"이 매물 <b>{ctx_prop['addr']}</b>의 진단 결과·위험 신호를 근거로 답변합니다."
    else:
        sub = "내 자료(등기부·계약서·종로구 실거래가)를 근거로 답변합니다."
    st.markdown(
        f'<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">{sub}</p>',
        unsafe_allow_html=True,
    )

    # 세션 메시지 초기화. 실제 질문 전에는 입력창만 보이게 비워 둔다.
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 빠른 질문 (모드별 동적)
    quick = st.columns(4)
    active_ctx = ctx_doc if mode == "doc" else (ctx_prop if mode == "property" else None)
    quick_qs = quick_questions_for(mode, active_ctx)

    for i, q in enumerate(quick_qs):
        with quick[i]:
            if st.button(q, key=f"q_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": q})
                reply = generate_chat_reply(q, mode, ctx_doc, ctx_prop)
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply["answer"], "sources": reply["sources"]}
                )
                st.rerun()

    # 메시지 렌더링
    if st.session_state.messages:
        st.markdown('<div style="margin-top:16px"></div>', unsafe_allow_html=True)
        render_chat_messages(st.session_state.messages)

    if mode == "default":
        st.markdown(
            """
            <div style="background:var(--gray-50);border:1px solid var(--gray-200);border-radius:12px;padding:16px;margin-top:16px;margin-bottom:16px;font-size:14px;color:var(--gray-900)">
              현재 매물(<b>종로구 명륜2가 35-12</b>)의 자료를 분석해 보면, <b>전세가율 91%</b>, <b>선순위 근저당 ₩2.1억 미말소</b>, <b>신탁등기 의심</b> 등 3가지 치명적인 위험 신호가 있습니다.<br/><br/>
              구체적으로 어떤 부분을 알려드릴까요? 위의 빠른 질문을 이용하시거나 자유롭게 물어보세요.
              <div style="margin-top:12px;display:flex;gap:6px;align-items:center;">
                <b style="font-size:12px;color:var(--gray-600);margin-right:4px;">근거 자료</b>
                <span class="ref" style="background:#fff;border:1px solid var(--gray-200);padding:4px 8px;border-radius:6px;font-size:12px;">📄 등기부등본</span>
                <span class="ref" style="background:#fff;border:1px solid var(--gray-200);padding:4px 8px;border-radius:6px;font-size:12px;">📋 계약서 초안</span>
                <span class="ref" style="background:#fff;border:1px solid var(--gray-200);padding:4px 8px;border-radius:6px;font-size:12px;">🏠 종로구 실거래가</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 입력
    placeholder = {
        "doc": "예: 이 문서의 핵심 판시 사항이 뭔가요?",
        "property": "예: 근저당 ₩2.1억은 어떻게 대응해야 하나요?",
        "default": "예: 이 특약이 왜 위험한가요?",
    }[mode]
    if prompt := st.chat_input(placeholder):
        st.session_state.messages.append({"role": "user", "content": prompt})
        reply = generate_chat_reply(
            prompt,
            mode,
            st.session_state.get("chat_context_doc"),
            st.session_state.get("chat_context_property"),
        )
        st.session_state.messages.append(
            {"role": "assistant", "content": reply["answer"], "sources": reply["sources"]}
        )
        st.rerun()
