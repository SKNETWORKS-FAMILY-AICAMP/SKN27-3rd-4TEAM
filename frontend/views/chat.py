"""상담 챗 (메인) — 진단 결과 + RAG 스타일 챗봇."""

import streamlit as st
from utils.components import (
    render_status_pill,
    law_banner,
    section_divider,
)


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
        "현재 매물(<b>종로구 명륜2가 35-12</b>)의 자료를 분석해 보면, "
        "<b>전세가율 91%</b>, <b>선순위 근저당 ₩2.1억 미말소</b>, <b>신탁등기 의심</b> 등 "
        "3가지 치명적인 위험 신호가 있습니다.<br/><br/>"
        "구체적으로 어떤 부분을 알려드릴까요? 아래 빠른 질문을 이용하시거나 자유롭게 물어보세요."
    ),
    "sources": ["📄 등기부등본", "📋 계약서 초안", "🏠 종로구 실거래가"],
}


LEVEL_KO = {"danger": "위험", "caution": "주의", "safe": "안전"}


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
                st.session_state.pop("messages", None)
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
                st.session_state.pop("messages", None)
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

        doc_l, doc_r = st.columns(2)
        with doc_l:
            st.file_uploader(
                "등기부등본 (.docx)",
                type=["docx"],
                help="등기소·정부24에서 발급한 등기부등본을 docx 파일로 첨부하세요.",
            )
        with doc_r:
            st.file_uploader(
                "임대차계약서 (.docx)",
                type=["docx"],
                help="특약 조항이 모두 포함된 임대차계약서를 docx 파일로 첨부하세요.",
            )

        st.markdown(
            """
            <div style="background:var(--green-soft);border:1px solid #b8ead9;border-radius:12px;
                        padding:12px 14px;margin-top:10px;font-size:13px;color:#005a3f">
              ✓ 분석 완료 · 자세한 진단 결과·유사 사례는 <b>진단 기록 → 자세히</b>에서 확인하세요
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

    # 세션 메시지 초기화 (모드 진입 시 이미 셋업됨)
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": DEFAULT_REPLY["answer"],
            "sources": DEFAULT_REPLY["sources"],
        }]

    # 빠른 질문 (모드별 동적)
    quick = st.columns(4)
    active_ctx = ctx_doc if mode == "doc" else (ctx_prop if mode == "property" else None)
    quick_qs = quick_questions_for(mode, active_ctx)

    for i, q in enumerate(quick_qs):
        with quick[i]:
            if st.button(q, key=f"q_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": q})
                reply = find_reply(q, ctx_doc=ctx_doc, ctx_prop=ctx_prop)
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply["answer"], "sources": reply["sources"]}
                )
                st.rerun()

    # 메시지 렌더링
    st.markdown('<div style="margin-top:16px"></div>', unsafe_allow_html=True)
    for m in st.session_state.messages:
        if m["role"] == "user":
            st.markdown(f'<div class="chat-q">{m["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-a">{m["content"]}</div>', unsafe_allow_html=True)
            if m.get("sources"):
                refs = "".join(f'<span class="ref">{s}</span>' for s in m["sources"])
                st.markdown(
                    f'<div class="rag-src"><b>근거 자료</b>{refs}</div>',
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
        reply = find_reply(
            prompt,
            ctx_doc=st.session_state.get("chat_context_doc"),
            ctx_prop=st.session_state.get("chat_context_property"),
        )
        st.session_state.messages.append(
            {"role": "assistant", "content": reply["answer"], "sources": reply["sources"]}
        )
        st.rerun()
