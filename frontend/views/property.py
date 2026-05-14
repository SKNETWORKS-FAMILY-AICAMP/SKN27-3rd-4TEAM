"""최근 확인 매물 상세 화면."""

import streamlit as st

from utils.components import render_status_pill, risk_row, case_row, section_divider
from views.history import LEVEL_KO, RECORDS


DETAILS = {
    1: {"building": "한빛빌라 302호", "sale": "₩2.75억", "risks": [("전세가율 91%", "치명", "danger", "HUG 전세보증보험 약관 제10조 · 90% 초과 시 가입 거절"), ("선순위 근저당 ₩2.1억 미말소", "치명", "danger", "대법원 2022다48327 · 선순위 우선 변제"), ("신탁등기 의심", "주의", "caution", "신탁법 제22조 · 수탁자 동의 없이 임대 불가")]},
    2: {"building": "익선동 ○○빌라 201호", "sale": "₩2.2억", "risks": [("다가구 선순위 임차인 확인 필요", "주의", "caution", "주택임대차보호법 · 우선변제권 확인"), ("전세가율 82%", "주의", "caution", "보증보험 심사 기준 확인 필요")]},
    3: {"building": "혜화동 ○○ 빌라 5층", "sale": "₩3.5억", "risks": [("전세가율 63%", "안전", "safe", "시세 대비 보증금이 낮은 편"), ("HUG 가입 가능", "안전", "safe", "보증보험 가입 가능성 높음")]},
    4: {"building": "창신동 ○○ 오피스텔 1102호", "sale": "₩1.67억", "risks": [("신탁등기 확인 필요", "치명", "danger", "신탁원부와 수탁자 동의서 확인 필요"), ("전세가율 96%", "치명", "danger", "깡통전세 위험 구간")]},
    5: {"building": "명륜1가 ○○빌라 401호", "sale": "₩2.7억", "risks": [("근저당 소액 존재", "주의", "caution", "말소 조건 특약 권장"), ("전세가율 74%", "주의", "caution", "추가 권리관계 확인 필요")]},
    6: {"building": "누상동 ○○ 빌라 302호", "sale": "₩3.3억", "risks": [("전세가율 58%", "안전", "safe", "시세 대비 안정 구간"), ("선순위 권리 없음", "안전", "safe", "최근 등기부 기준 위험 권리 없음")]},
}


def _selected_record():
    rec_id = st.session_state.get("selected_record_id", 1)
    return next((r for r in RECORDS if r["id"] == rec_id), RECORDS[0])


def render():
    rec = _selected_record()
    detail = DETAILS.get(rec["id"], DETAILS[1])
    status_type = {"danger": "danger", "caution": "caution", "safe": "safe"}[rec["level"]]

    st.markdown(
        f'<div style="font-size:12px;font-weight:700;color:var(--gray-500);letter-spacing:.04em;margin-bottom:6px">최근 확인 매물 · 분석 #{rec["id"]:03d}</div>',
        unsafe_allow_html=True,
    )

    title_col, status_col = st.columns([3, 1.2])
    with title_col:
        st.markdown(f"# {rec['addr']}")
        st.markdown(
            '<p style="color:var(--gray-500);font-size:14px;margin-top:-8px">전세 계약 전 확인해야 할 핵심 정보와 위험 신호를 한 화면에서 확인하세요.</p>',
            unsafe_allow_html=True,
        )
    with status_col:
        st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
        render_status_pill(status_type, rec["score"], f"{LEVEL_KO[rec['level']]} 매물")

    section_divider()

    # ───── 분석 완료 배너 (AI 안심 상담에서 업로드된 자료 기반) ─────
    st.markdown(
        f"""
        <div style="background:var(--green-soft);border:1px solid #b8ead9;border-radius:12px;
                    padding:12px 14px;margin-top:4px;font-size:13px;color:#005a3f">
          ✓ 분석 완료 · <b>{len(detail['risks'])}건 위험 신호</b> 탐지됨 — 아래 진단 결과를 확인하세요
        </div>
        """,
        unsafe_allow_html=True,
    )

    section_divider()

    info_col, risk_col = st.columns([1, 1.15])

    with info_col:
        st.markdown("### 매물 정보")
        st.markdown(
            f"""
            <div class="tw-card">
              <div class="prop-detail-grid">
                <span>주소</span><b>{rec['addr']}</b>
                <span>건물명</span><b>{detail['building']}</b>
                <span>보증금</span><b>{rec['deposit']}</b>
                <span>면적</span><b>{rec['area']}</b>
                <span>준공</span><b>{rec['year']}</b>
                <span>예상 매매가</span><b>{detail['sale']}</b>
                <span>전세가율</span><b>{rec['ratio']}</b>
                <span>보증보험</span><b>{rec['hug']}</b>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
        st.markdown("### 계약 진행 상태")
        st.markdown(
            """
            <div class="tw-card">
              <div class="timeline-row done"><span></span><div><b>자료 분석 완료</b><small>등기부등본 · 계약서 초안 · 시세 데이터 확인</small></div></div>
              <div class="timeline-row now"><span></span><div><b>위험 검토 필요</b><small>아래 위험 항목 해소 후 계약 진행 권장</small></div></div>
              <div class="timeline-row"><span></span><div><b>체크리스트 확인</b><small>계약 전 필수 항목을 완료하세요</small></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with risk_col:
        st.markdown("### 핵심 위험 신호")
        for title, meta, tone, law in detail["risks"]:
            risk_row(title, meta, tone, law=law)

        st.markdown(
            """
            <div class="tw-card" style="margin-top:12px">
              <div style="font-size:11px;font-weight:800;color:var(--gray-500);letter-spacing:.06em;margin-bottom:10px">권장 조치</div>
              <div class="action-row"><b>1</b><span>등기부등본을 계약 직전 다시 발급해 권리 변동을 확인</span></div>
              <div class="action-row"><b>2</b><span>반환보증 가입 가능 여부를 먼저 조회</span></div>
              <div class="action-row"><b>3</b><span>위험 권리는 말소 조건 특약으로 계약서에 명시</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    section_divider()

    # ───── 나와 비슷한 사례 ─────
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

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("← 진단 기록", use_container_width=True):
            st.session_state.current_view = "history"
            st.rerun()
    with c2:
        if st.button("💬 챗봇에서 질문", use_container_width=True, type="primary"):
            # 매물 컨텍스트 설정 (문서 컨텍스트는 해제 — 상호 배타)
            st.session_state.chat_context_property = {
                "id": rec["id"],
                "addr": rec["addr"],
                "deposit": rec["deposit"],
                "area": rec["area"],
                "year": rec["year"],
                "score": rec["score"],
                "level": rec["level"],
                "ratio": rec["ratio"],
                "senior": rec["senior"],
                "hug": rec["hug"],
                "tags": rec["tags"],
                "risks": [list(r) for r in detail["risks"]],
                "building": detail["building"],
                "sale": detail["sale"],
            }
            st.session_state.pop("chat_context_doc", None)
            # 매물 기반 인삿말로 메시지 초기화
            risk_titles = " · ".join(r[0] for r in detail["risks"][:3])
            st.session_state.messages = [{
                "role": "assistant",
                "content": (
                    f"🏠 <b>{rec['addr']}</b> 매물에 대한 상담을 시작합니다.<br/><br/>"
                    f"진단 결과: <b>위험도 {rec['score']}점 ({LEVEL_KO[rec['level']]})</b> · "
                    f"전세가율 <b>{rec['ratio']}</b> · 보증보험 <b>{rec['hug']}</b><br/><br/>"
                    f"주요 위험 신호: {risk_titles}<br/><br/>"
                    "이 매물에 대해 무엇을 알고 싶으신가요?"
                ),
                "sources": [f"📋 매물 진단 #{rec['id']:03d}", f"⚠️ 위험 신호 {len(detail['risks'])}건"],
            }]
            st.session_state.current_view = "chat"
            st.rerun()
    with c3:
        if st.button("✅ 체크리스트", use_container_width=True):
            st.session_state.current_view = "checklist"
            st.rerun()
