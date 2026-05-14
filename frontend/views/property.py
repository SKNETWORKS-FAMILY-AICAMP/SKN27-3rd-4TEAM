"""매물 상세 화면 — 진단 기록에서 선택한 매물의 상세 정보."""

import streamlit as st

from utils.components import render_status_pill, risk_row, section_divider
from views.history import LEVEL_KO, _load_reports, _risk_to_level


def _selected_record():
    rec_id = st.session_state.get("selected_record_id", 1)
    records = _load_reports()
    for r in records:
        if r["id"] == rec_id:
            return r
    return records[0] if records else None


def render():
    rec = _selected_record()
    if not rec:
        st.warning("선택된 매물 정보가 없습니다.")
        if st.button("← 진단 기록으로"):
            st.session_state.current_view = "history"
            st.rerun()
        return

    report = rec.get("report_data", {})
    ui = report.get("user_info", {})
    level = rec["level"]
    level_ko = LEVEL_KO.get(level, "미상")

    st.markdown(
        f'<div style="font-size:12px;font-weight:700;color:var(--gray-500);'
        f'letter-spacing:.04em;margin-bottom:6px">진단 상세 · {rec["session_id"]}</div>',
        unsafe_allow_html=True,
    )

    title_col, status_col = st.columns([3, 1.2])
    with title_col:
        st.markdown(f"# {rec['addr']}")
        st.markdown(
            f'<p style="color:var(--gray-500);font-size:14px;margin-top:-8px">'
            f'{rec["date"]} 진단 · {rec["deposit"]}{" · " + rec["area"] if rec["area"] else ""}</p>',
            unsafe_allow_html=True,
        )
    with status_col:
        st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
        render_status_pill(level, rec["score"], f"{level_ko} 매물")

    section_divider()

    info_col, risk_col = st.columns([1, 1.15])

    with info_col:
        st.markdown("### 매물 정보")
        pred_deposit = ui.get("predicted_deposit_2027", "미상")
        pred_sale = ui.get("predicted_sale_2027", "미상")
        ratio = ui.get("jeonse_ratio", "미상")
        st.markdown(
            f"""
            <div class="tw-card">
              <div class="prop-detail-grid">
                <span>주소</span><b>{ui.get('address', '미상')}</b>
                <span>전세금</span><b>{ui.get('deposit', 0):,}만원</b>
                <span>전용면적</span><b>{ui.get('area_m2', '미상')}㎡</b>
                <span>계약기간</span><b>{ui.get('contract_period', '미상')}</b>
                <span>전세가율</span><b>{ratio}{'%' if isinstance(ratio, (int, float)) else ''}</b>
                <span>예측 전세금(2027)</span><b>{pred_deposit if pred_deposit == '미상' else f'{pred_deposit:,}만원'}</b>
                <span>예측 매매가(2027)</span><b>{pred_sale if pred_sale == '미상' else f'{pred_sale:,}만원'}</b>
                <span>위험 점수</span><b>{ui.get('risk_score', 0)}/100</b>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 가격 진단
        price_diag = report.get("price_diagnosis", "")
        if price_diag:
            st.markdown("### 가격 진단")
            st.markdown(
                f'<div class="tw-card"><p style="font-size:13px;line-height:1.7;color:var(--gray-700)">'
                f'{price_diag}</p></div>',
                unsafe_allow_html=True,
            )

    with risk_col:
        st.markdown("### 위험 분석")

        # 가격 위험
        if ui.get("jeonse_ratio"):
            r = ui["jeonse_ratio"]
            if r >= 90:
                risk_row(f"전세가율 {r:.0f}%", "치명", "danger")
            elif r >= 80:
                risk_row(f"전세가율 {r:.0f}%", "주의", "caution")
            else:
                risk_row(f"전세가율 {r:.0f}%", "안전", "safe")

        if ui.get("deposit_vs_avg") and ui["deposit_vs_avg"] > 110:
            v = ui["deposit_vs_avg"]
            risk_row(f"지역 평균 대비 {v:.0f}%", "주의" if v < 120 else "치명", "caution" if v < 120 else "danger")

        # 특약 위험
        terms = report.get("special_terms", [])
        if terms:
            st.markdown("#### 특약 분석")
            for t in terms:
                t_level = _risk_to_level(t.get("risk_level", "미상"))
                text = t.get("term_text", "")[:50]
                risk_row(text, t.get("risk_level", "미상"), t_level)
                if t.get("diagnosis"):
                    st.markdown(
                        f'<div style="padding-left:40px;margin-bottom:8px;font-size:12px;color:var(--gray-500)">'
                        f'{t["diagnosis"][:100]}</div>',
                        unsafe_allow_html=True,
                    )

        # 최종 리포트
        final = report.get("final_report", "")
        if final:
            st.markdown("#### 종합 소견")
            st.markdown(
                f'<div class="tw-card" style="border-left:3px solid var(--blue);margin-top:8px">'
                f'<p style="font-size:13px;line-height:1.7;color:var(--gray-700)">{final}</p></div>',
                unsafe_allow_html=True,
            )

    section_divider()

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("← 진단 기록", use_container_width=True):
            st.session_state.current_view = "history"
            st.rerun()
    with c2:
        if st.button("💬 이 매물로 상담", use_container_width=True, type="primary"):
            st.session_state.session_id = rec["session_id"]
            if "chat_session" in st.session_state:
                del st.session_state.chat_session
            st.session_state.diagnosis_done = True
            st.session_state.report = report
            st.session_state.current_view = "chat"
            st.rerun()
    with c3:
        if st.button("✅ 체크리스트", use_container_width=True):
            st.session_state.current_view = "checklist"
            st.rerun()
