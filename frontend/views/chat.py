"""상담 챗 (메인) — 계약서 업로드 → 진단 → 챗봇 상담."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from utils.components import (
    render_status_pill,
    risk_row,
    section_divider,
)


def _get_risk_level_key(level: str) -> str:
    return {"위험": "danger", "주의": "caution", "안전": "safe"}.get(level, "caution")


def _run_diagnosis(file_bytes=None, filename=None,
                   address=None, deposit=None, area_m2=None):
    from backend.workflow import run_diagnosis
    return run_diagnosis(
        file_bytes=file_bytes, filename=filename,
        address=address, deposit=deposit, area_m2=area_m2,
    )


def _chat_response(question: str) -> tuple[str, list[dict]]:
    from backend.agents.chatbot import chat, create_session

    if "chat_session" not in st.session_state:
        sid = st.session_state.get("session_id", "")
        st.session_state.chat_session = create_session(sid)

    return chat(question, st.session_state.chat_session)


# ── 메인 렌더 ────────────────────────────────────────────

def render():
    # 헤더
    col_h1, col_h2 = st.columns([3, 1.4])
    with col_h1:
        st.markdown(
            '<div style="font-size:12px;font-weight:700;color:var(--gray-500);'
            'letter-spacing:.04em;margin-bottom:6px">전세계약 위험 진단</div>',
            unsafe_allow_html=True,
        )
        st.markdown("# 계약서 분석 & AI 상담")
        st.markdown(
            '<p style="color:var(--gray-500);font-size:14px;margin-top:-8px">'
            "계약서를 올리거나 정보를 입력하면, AI가 종로구 실거래가와 판례를 근거로 위험을 진단합니다.</p>",
            unsafe_allow_html=True,
        )
    with col_h2:
        if st.session_state.get("diagnosis_done"):
            report = st.session_state.get("report")
            if report:
                ui = report.get("user_info", {})
                level = ui.get("risk_level", "미상")
                score = ui.get("risk_score", 0)
                render_status_pill(_get_risk_level_key(level), score, level)

    section_divider()

    # ── 입력 + 진단 ──────────────────────────────────────
    upload_col, diag_col = st.columns([1.1, 1])

    with upload_col:
        st.markdown("### 📎 계약서 업로드 또는 직접 입력")

        input_mode = st.radio(
            "입력 방식", ["파일 업로드", "직접 입력"],
            horizontal=True, label_visibility="collapsed",
        )

        if input_mode == "파일 업로드":
            uploaded = st.file_uploader(
                "임대차계약서 (DOCX / PDF)",
                type=["docx", "pdf"],
                help="특약 조항이 포함된 전체 계약서를 올려 주세요.",
            )
            if st.button("🔍 진단 시작", type="primary", use_container_width=True,
                         disabled=uploaded is None):
                if uploaded:
                    with st.spinner("계약서 분석 중... (약 30초 소요)"):
                        result = _run_diagnosis(
                            file_bytes=uploaded.getvalue(),
                            filename=uploaded.name,
                        )
                    _handle_result(result)
        else:
            addr = st.text_input("주소", placeholder="예: 서울 종로구 명륜2가 35-12")
            c1, c2 = st.columns(2)
            with c1:
                dep = st.number_input("전세금 (만원)", min_value=0, step=500, format="%d")
            with c2:
                area = st.number_input("전용면적 (㎡)", min_value=0.0, step=1.0, format="%.1f")

            if st.button("🔍 진단 시작", type="primary", use_container_width=True,
                         disabled=not addr or dep <= 0):
                with st.spinner("분석 중... (약 20초 소요)"):
                    result = _run_diagnosis(
                        address=addr, deposit=int(dep),
                        area_m2=area if area > 0 else None,
                    )
                _handle_result(result)

    with diag_col:
        if st.session_state.get("diagnosis_done"):
            _render_diagnosis(st.session_state.get("report", {}))
        else:
            st.markdown("### ⚠️ 진단 결과")
            st.markdown(
                '<div style="background:var(--gray-100);border-radius:14px;padding:24px;text-align:center">'
                '<p style="color:var(--gray-500);font-size:14px;margin:0">'
                '계약서를 업로드하거나 정보를 입력하면<br/>여기에 진단 결과가 표시됩니다.</p></div>',
                unsafe_allow_html=True,
            )

    section_divider()

    # ── 챗봇 ─────────────────────────────────────────────
    st.markdown("### 💬 안전이에게 물어보세요")
    if st.session_state.get("diagnosis_done"):
        st.markdown(
            '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
            "진단 결과와 판례를 근거로 답변합니다. 법률 질문도 가능해요!</p>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
            "전세 관련 궁금한 점을 자유롭게 물어보세요. 진단을 먼저 하면 맞춤 답변을 받을 수 있어요.</p>",
            unsafe_allow_html=True,
        )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 빠른 질문
    qcols = st.columns(4)
    quick_qs = [
        "전세가율이 높으면 왜 위험해요?",
        "꼭 넣어야 할 특약이 있나요?",
        "전세보증보험 가입 조건은?",
        "보증금 못 돌려받으면 어떡해요?",
    ]
    for i, q in enumerate(quick_qs):
        with qcols[i]:
            if st.button(q, key=f"q_{i}", use_container_width=True):
                _send_message(q)

    # 메시지 렌더링
    st.markdown('<div style="margin-top:16px"></div>', unsafe_allow_html=True)
    for m in st.session_state.messages:
        if m["role"] == "user":
            st.markdown(
                f'<div class="chat-q">{m["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="chat-a">{m["content"]}</div>',
                unsafe_allow_html=True,
            )
            if m.get("sources"):
                refs_html = "".join(
                    f'<span class="ref">{s["text"]}</span>' for s in m["sources"]
                )
                st.markdown(
                    f'<div class="rag-src"><b>근거 자료</b>{refs_html}</div>',
                    unsafe_allow_html=True,
                )

    # 입력
    if prompt := st.chat_input("예: 이 특약이 왜 위험한가요?"):
        _send_message(prompt)


# ── 헬퍼 ─────────────────────────────────────────────────

def _handle_result(result: dict):
    if not result.get("success"):
        st.error(result.get("error", "분석 중 오류가 발생했습니다."))
        return

    st.session_state.diagnosis_done = True
    report_obj = result.get("report")
    if report_obj:
        st.session_state.report = (
            report_obj.model_dump() if hasattr(report_obj, "model_dump") else report_obj
        )
        st.session_state.session_id = (
            report_obj.session_id if hasattr(report_obj, "session_id") else ""
        )
    st.session_state.final_report = result.get("final_report", "")

    st.session_state.messages = [
        {
            "role": "assistant",
            "content": result.get("final_report", "진단이 완료되었습니다. 궁금한 점을 물어보세요!"),
            "sources": [],
        }
    ]

    if "chat_session" in st.session_state:
        del st.session_state.chat_session

    st.rerun()


def _render_diagnosis(report: dict):
    st.markdown("### ⚠️ 진단 결과")
    ui = report.get("user_info", {})
    st.markdown(
        f'<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
        f'{ui.get("address", "")} · 전세금 {ui.get("deposit", 0):,}만원</p>',
        unsafe_allow_html=True,
    )

    # 가격 위험도
    level = ui.get("risk_level", "미상")
    level_key = _get_risk_level_key(level)

    jeonse_ratio = ui.get("jeonse_ratio")
    if jeonse_ratio:
        risk_row(f"전세가율 {jeonse_ratio}%", level, level_key)

    deposit_vs = ui.get("deposit_vs_avg")
    if deposit_vs and deposit_vs > 110:
        risk_row(
            f"지역 평균 대비 {deposit_vs}%",
            "주의" if deposit_vs < 120 else "치명",
            "caution" if deposit_vs < 120 else "danger",
        )

    # 특약 위험
    for t in report.get("special_terms", []):
        t_level = t.get("risk_level", "미상")
        text = t.get("term_text", "")[:40]
        risk_row(text, t_level, _get_risk_level_key(t_level))

    # 진단 요약
    price_diag = report.get("price_diagnosis", "")
    if price_diag:
        st.markdown(
            f'<div style="background:var(--gray-100);border-radius:12px;'
            f'padding:14px;margin-top:12px;font-size:13px;color:var(--gray-700)">'
            f'{price_diag}</div>',
            unsafe_allow_html=True,
        )


def _send_message(question: str):
    st.session_state.messages.append({"role": "user", "content": question})
    try:
        with st.spinner("안전이가 답변을 준비하고 있어요..."):
            answer, sources = _chat_response(question)
    except Exception as e:
        answer = f"죄송합니다, 응답 생성 중 오류가 발생했습니다: {str(e)}"
        sources = []

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
    })
    st.rerun()
