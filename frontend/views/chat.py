"""상담 챗 (메인) — 진단 결과 + RAG 스타일 챗봇."""

import streamlit as st
from utils.components import (
    render_status_pill,
    risk_row,
    case_row,
    law_banner,
    section_divider,
)
from utils.data import load_jongno, dong_stats, won_to_eok


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


def find_reply(question: str) -> dict:
    for r in DEMO_REPLIES:
        if any(kw in question for kw in r["q_match"]):
            return r
    return DEFAULT_REPLY


# ─── 화면 ──────────────────────────────────────────────
def render():
    # 상단 법령 개정 알림
    law_banner(
        "<b>2026.3.1 주택임대차보호법 제8조 개정</b> · 소액임차인 우선변제 한도가 "
        "₩1억 → <b>₩1.5억</b>으로 상향 — 당신 매물에 적용됩니다.",
        pill="법령 개정",
    )

    # 헤더 + 상태 핀
    col_h1, col_h2 = st.columns([3, 1.4])
    with col_h1:
        st.markdown(
            '<div style="font-size:12px;font-weight:700;color:var(--gray-500);'
            'letter-spacing:.04em;margin-bottom:6px">상담 챗 · 종로구 명륜2가 35-12 · 분석 #A1F-203</div>',
            unsafe_allow_html=True,
        )
        st.markdown("# 내 자료 기반 AI 상담")
        st.markdown(
            '<p style="color:var(--gray-500);font-size:14px;margin-top:-8px">'
            "업로드한 등기부등본·계약서를 근거로 질문에 답합니다. 모든 답변은 출처를 함께 보여드립니다.</p>",
            unsafe_allow_html=True,
        )
    with col_h2:
        st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
        render_status_pill("danger", 78, "깡통전세 위험")

    section_divider()

    # 자료 업로드 + 진단
    upload_col, diag_col = st.columns([1.1, 1])

    with upload_col:
        st.markdown("### 📎 내 자료 (RAG 학습됨)")
        st.markdown(
            '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
            "업로드한 자료를 기반으로 챗봇이 답변합니다.</p>",
            unsafe_allow_html=True,
        )

        st.text_input(
            "주소",
            value="서울 종로구 명륜2가 35-12 한빛빌라 302호",
            label_visibility="visible",
        )

        c1, c2 = st.columns(2)
        with c1:
            st.number_input("보증금 (만원)", value=25000, step=500, format="%d")
        with c2:
            st.number_input("월세 (만원)", value=0, step=10, format="%d")

        st.file_uploader(
            "등기부등본 PDF",
            type=["pdf"],
            help="등기소·정부24에서 발급한 PDF를 첨부하세요.",
        )
        st.file_uploader(
            "임대차계약서 PDF",
            type=["pdf", "jpg", "png"],
            help="특약 조항이 모두 포함된 전체 페이지를 업로드해 주세요.",
        )

        with st.container():
            st.markdown(
                """
                <div style="background:var(--green-soft);border:1px solid #b8ead9;border-radius:12px;
                            padding:12px 14px;margin-top:8px;font-size:13px;color:#005a3f">
                  ✓ 분석 완료 · <b>3건 위험 · 2건 주의</b> 탐지됨
                </div>
                """,
                unsafe_allow_html=True,
            )

    with diag_col:
        st.markdown("### ⚠️ 진단 결과")
        st.markdown(
            '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
            "위험 항목을 클릭하면 챗봇에게 추가 질문할 수 있어요.</p>",
            unsafe_allow_html=True,
        )

        risk_row(
            "전세가율 91%",
            "치명",
            "danger",
            law="HUG 전세보증보험 약관 제10조 · 90% 초과 시 가입 거절",
        )
        risk_row(
            "선순위 근저당 ₩2.1억 미말소",
            "치명",
            "danger",
            law="대법원 2022다48327 · 선순위 우선 변제",
        )
        risk_row(
            "신탁등기 의심",
            "주의",
            "caution",
            law="신탁법 제22조 · 수탁자 동의 없이 임대 불가",
        )
        risk_row(
            "임대인 다수 매물 보유",
            "주의",
            "caution",
        )

    section_divider()

    # 유사 사례 매칭
    st.markdown("### 🎯 나와 비슷한 사례 — 종로구 자동 매칭")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
        "다세대 · 전세가율 90%+ · 근저당 있음 조건의 실제 피해/구제 사례입니다.</p>",
        unsafe_allow_html=True,
    )

    case_row(
        "'23",
        "종로",
        "<b>명륜동 다세대 · 근저당 2.4억</b><br/>"
        '<span style="color:var(--gray-500);font-size:12px">'
        "경매 낙찰 1.92억 · 임차인 회수 실패 · HUG 보장 미가입</span>",
        "회수 0%",
        "bad",
    )
    case_row(
        "'24",
        "종로",
        "<b>혜화동 빌라 · HUG 가입 상태</b><br/>"
        '<span style="color:var(--gray-500);font-size:12px">'
        "임대인 파산 · HUG가 보증금 전액 대위변제 · 평균 소요 4.2개월</span>",
        "회수 100%",
        "good",
    )
    case_row(
        "'24",
        "종로",
        "<b>익선동 오피스텔 · 임차권등기</b><br/>"
        '<span style="color:var(--gray-500);font-size:12px">'
        "동일 패턴 · 임차권등기 + 단독 경매 신청으로 68% 회수 (14개월)</span>",
        "회수 68%",
        "partial",
    )

    st.markdown(
        """
        <div style="background:var(--gray-100);border-radius:14px;padding:16px;margin-top:8px">
          <div style="font-size:11px;font-weight:800;color:var(--gray-500);letter-spacing:.06em;margin-bottom:10px">
            동일 조건 47건 판례 평균
          </div>
          <div class="stat-row"><span>평균 회수율</span><b>43%</b></div>
          <div class="stat-row"><span>평균 소요 기간</span><b>13.8개월</b></div>
          <div class="stat-row"><span>HUG 가입 시 회수율</span><b style="color:var(--green)">100%<span class="delta">+57%p</span></b></div>
          <div class="stat-row"><span>임차권등기 시 회수율</span><b style="color:var(--green)">81%<span class="delta">+38%p</span></b></div>
          <div style="font-size:11px;color:var(--gray-500);margin-top:8px">
            근거: 대법원 판결문 + HUG 대위변제 공개 데이터 (2022–2025)
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    section_divider()

    # 챗봇
    st.markdown("### 💬 궁금한 점을 물어보세요")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
        "내 자료(등기부·계약서·종로구 실거래가)를 근거로 답변합니다.</p>",
        unsafe_allow_html=True,
    )

    # 세션 상태
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": DEFAULT_REPLY["answer"],
                "sources": DEFAULT_REPLY["sources"],
            }
        ]

    # 빠른 질문 버튼
    quick = st.columns(4)
    quick_qs = [
        "근저당이 왜 문제인가요?",
        "특약 문구 예시 보여줘",
        "HUG 가입 조건 알려줘",
        "경매 절차 더 설명해줘",
    ]
    for i, q in enumerate(quick_qs):
        with quick[i]:
            if st.button(q, key=f"q_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": q})
                reply = find_reply(q)
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
    if prompt := st.chat_input("예: 이 특약이 왜 위험한가요?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        reply = find_reply(prompt)
        st.session_state.messages.append(
            {"role": "assistant", "content": reply["answer"], "sources": reply["sources"]}
        )
        st.rerun()
