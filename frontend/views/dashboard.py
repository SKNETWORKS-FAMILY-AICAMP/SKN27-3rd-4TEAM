"""Dashboard view for the latest real diagnosis."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st


def _latest() -> dict[str, Any] | None:
    latest = st.session_state.get("latest_diagnosis") or st.session_state.get("diagnosis_context")
    if latest:
        return latest
    records = st.session_state.get("history_records") or []
    return records[0] if records else None


def _title(item: dict[str, Any]) -> str:
    info = item.get("contract_info") or {}
    return (
        info.get("address")
        or item.get("addr")
        or item.get("summary")
        or "최근 계약서 진단"
    )


def _score(item: dict[str, Any]) -> Any:
    return item.get("risk_score", item.get("score", "-"))


def _level(item: dict[str, Any]) -> str:
    return str(item.get("risk_level", item.get("level", "진단")))


def render() -> None:
    item = _latest()
    title = _title(item) if item else "진단한 계약서 없음"
    score = _score(item) if item else "-"
    level = _level(item) if item else "대기"
    summary = str((item or {}).get("summary") or "AI 안심 상담에서 계약서 파일을 업로드하면 이곳에 최근 진단 결과가 표시됩니다.")
    factors = (item or {}).get("risk_factors") or []

    st.markdown(
        f"""
        <div class="home-hero">
          <div>
            <div class="eyebrow">안전한 부동산 거래를 위한 AI 분석</div>
            <h1>전세 계약 위험 신호와 진단 기록을 한 화면에서 확인하세요</h1>
            <p>업로드한 계약서 진단 결과를 기준으로 위험도, 상담, 체크리스트를 이어서 확인할 수 있습니다.</p>
          </div>
          <div class="home-hero-card">
            <span>현재 분석 계약서</span>
            <b>{html.escape(str(title))}</b>
            <small>{html.escape(str(level))} · {html.escape(str(score))}점</small>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("위험 점수", f"{score}점")
    with c2:
        st.metric("위험 등급", level)
    with c3:
        st.metric("탐지 위험 신호", f"{len(factors)}건")

    st.markdown("### 최근 진단 요약")
    st.markdown(
        f"""
        <div class="tw-card">
          <div style="color:var(--gray-700);line-height:1.65">{html.escape(summary)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 다음 작업")
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("AI 상담으로 이동", use_container_width=True, type="primary"):
            st.session_state.current_view = "chat"
            st.rerun()
    with b2:
        if st.button("진단 기록 보기", use_container_width=True):
            st.session_state.current_view = "history"
            st.rerun()
    with b3:
        if st.button("체크리스트 확인", use_container_width=True):
            st.session_state.current_view = "checklist"
            st.rerun()
