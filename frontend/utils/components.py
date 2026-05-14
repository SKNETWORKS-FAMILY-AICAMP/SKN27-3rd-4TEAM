"""재사용 위젯 — 위험도 뱃지, 매물 카드, 진단 결과 박스."""

import streamlit as st


def render_status_pill(level: str, score: int, label: str):
    """level: 'danger' | 'caution' | 'safe'."""
    color_map = {
        "danger": ("var(--red)", "var(--red-soft)", "#ffd5d5", "위험"),
        "caution": ("var(--amber)", "var(--amber-soft)", "#ffe4b8", "주의"),
        "safe": ("var(--green)", "var(--green-soft)", "#b8ead9", "안전"),
    }
    fg, bg, border, ko = color_map.get(level, color_map["caution"])
    icon = "!" if level == "danger" else ("?" if level == "caution" else "✓")
    st.markdown(
        f"""
        <div class="status-pill" style="background:{bg};border-color:{border}">
          <div class="icon-wrap" style="background:{fg}">{icon}</div>
          <div>
            <div class="level" style="color:{fg}">{ko}</div>
            <div class="score"><b>{score}점</b> · {label}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def risk_row(label: str, meta: str, level: str, law: str | None = None):
    icon = {"danger": "!", "caution": "?", "safe": "✓"}[level]
    law_html = ""
    if law:
        law_html = f'<div style="margin-top:8px;padding-left:40px"><span class="law-chip"><span class="lico">법</span>{law}</span></div>'
    st.markdown(
        f"""
        <div class="risk-row {level}">
          <span class="ic">{icon}</span>
          <span class="label">{label}</span>
          <span class="meta">{meta}</span>
        </div>
        {law_html}
        """,
        unsafe_allow_html=True,
    )


def case_row(year: str, region: str, body: str, result_label: str, result_kind: str):
    """result_kind: 'bad' | 'good' | 'partial'."""
    st.markdown(
        f"""
        <div class="case-row">
          <div class="yr"><div>{year}</div><small>{region}</small></div>
          <div>{body}</div>
          <div class="result {result_kind}">{result_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def emergency_widget():
    st.markdown(
        """
        <div class="emergency">
          <div class="ttl">긴급 신고 · 상담</div>
          <a href="tel:1357">
            <span>전세피해지원센터</span>
            <span class="num">☎ 1357</span>
          </a>
          <a href="tel:159900001">
            <span>HUG 사고접수</span>
            <span class="num">☎ 1599-0001</span>
          </a>
          <a href="tel:132">
            <span>대한법률구조공단</span>
            <span class="num">☎ 132</span>
          </a>
          <a href="https://www.molit.go.kr" target="_blank">
            <span>국토부 신고센터</span>
            <span style="color:#8b95a1">↗</span>
          </a>
          <a href="https://ecrm.police.go.kr" target="_blank">
            <span>경찰 사이버수사</span>
            <span style="color:#8b95a1">↗</span>
          </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def law_banner(text: str, pill: str = "법령 개정"):
    st.markdown(
        f"""
        <div class="law-banner">
          <span class="pill">{pill}</span>
          <span style="flex:1">{text}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_divider():
    st.markdown('<div class="sec-divider"></div>', unsafe_allow_html=True)
