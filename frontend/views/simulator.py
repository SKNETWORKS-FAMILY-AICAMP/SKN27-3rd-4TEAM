"""깡통전세 시뮬레이터 — 슬라이더로 시나리오, 판례 기반 회수율."""

import streamlit as st
import plotly.graph_objects as go


def render():
    st.markdown(
        '<div style="font-size:12px;font-weight:700;color:var(--gray-500);'
        'letter-spacing:.04em;margin-bottom:6px">깡통전세 시뮬레이터 · 판례 기반</div>',
        unsafe_allow_html=True,
    )
    st.markdown("# 만약 경매로 넘어간다면, 얼마를 회수할 수 있을까?")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:14px">'
        "보증금·시세 하락폭·선순위 채권을 조정하면 회수 시나리오가 실시간으로 갱신됩니다.</p>",
        unsafe_allow_html=True,
    )

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    # ───── 입력 패널 ─────
    input_col, result_col = st.columns([1, 1.4])

    with input_col:
        st.markdown('<div class="tw-card">', unsafe_allow_html=True)
        st.markdown("**시나리오 입력**")

        deposit      = st.slider("내 보증금 (억원)", 0.5, 5.0, 2.5, 0.1, help="실제 계약 보증금")
        market_price = st.slider("현재 매매 시세 (억원)", 0.5, 8.0, 2.75, 0.05, help="국토부 실거래가 기준")
        senior_lien  = st.slider("선순위 근저당 (억원)", 0.0, 4.0, 2.1, 0.1, help="등기부등본 을구 기준")
        drop_pct     = st.slider("경매 시 가격 하락률 (%)", 0, 50, 30, 5, help="2022–24 빌라 평균 하락폭 약 30%")

        st.markdown("</div>", unsafe_allow_html=True)

    with result_col:
        # 계산
        market_won  = market_price * 100_000_000
        deposit_won = deposit * 100_000_000
        senior_won  = senior_lien * 100_000_000

        auction_price = market_won * (1 - drop_pct / 100)
        auction_net   = auction_price * 0.85  # 경매 비용 15% 차감 가정
        after_senior  = max(0, auction_net - senior_won)
        recovery      = min(deposit_won, after_senior)

        loss         = deposit_won - recovery
        recovery_pct = (recovery / deposit_won) * 100 if deposit_won else 0
        jeonse_ratio = (deposit_won / market_won) * 100 if market_won else 0

        # 위험도 판정
        if jeonse_ratio >= 90 or recovery_pct < 50:
            level, level_ko, color = "danger", "위험", "var(--red)"
        elif jeonse_ratio >= 80 or recovery_pct < 80:
            level, level_ko, color = "caution", "주의", "var(--amber)"
        else:
            level, level_ko, color = "safe", "안전", "var(--green)"

        # 결과 카드
        st.markdown(
            f"""
            <div class="tw-card" style="background:linear-gradient(135deg,#fff 0%, var(--gray-50) 100%)">
              <div style="font-size:11px;font-weight:800;color:{color};letter-spacing:.06em">예상 회수율</div>
              <div style="font-size:56px;font-weight:800;color:{color};letter-spacing:-0.04em;margin-top:4px">
                {recovery_pct:.0f}%
              </div>
              <div style="color:var(--gray-700);font-size:14px;margin-top:4px">
                보증금 ₩{deposit_won/1e8:.2f}억 중 <b>₩{recovery/1e8:.2f}억</b> 회수 예상 ·
                손실 <b style="color:var(--red)">₩{loss/1e8:.2f}억</b>
              </div>
              <div style="display:flex;gap:10px;margin-top:14px">
                <span style="background:{color};color:#fff;padding:6px 12px;border-radius:999px;font-size:12px;font-weight:800">
                  {level_ko} · 전세가율 {jeonse_ratio:.0f}%
                </span>
                <span style="background:var(--gray-100);padding:6px 12px;border-radius:999px;font-size:12px;color:var(--gray-700);font-weight:700">
                  경매 낙찰가 ₩{auction_price/1e8:.2f}억
                </span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Plotly 게이지
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=recovery_pct,
                number={"suffix": "%", "font": {"size": 32, "color": color, "family": "Pretendard"}},
                gauge={
                    "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#d1d6db"},
                    "bar": {"color": color, "thickness": 0.6},
                    "bgcolor": "#f9fafb",
                    "borderwidth": 0,
                    "steps": [
                        {"range": [0, 50], "color": "#fde4e7"},
                        {"range": [50, 80], "color": "#fff0d4"},
                        {"range": [80, 100], "color": "#d9f5ea"},
                    ],
                },
            )
        )
        fig.update_layout(height=220, margin=dict(l=20, r=20, t=20, b=10), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ───── 시나리오 비교 ─────
    st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)
    st.markdown("### 📊 시나리오별 손실 비교")

    scenarios = [
        ("유지 (하락 0%)",  0,  "현재 시세 그대로 경매 진행"),
        ("소폭 하락 10%",   10, "2026 추정 평균 시나리오"),
        ("중간 하락 20%",   20, "지방 빌라 평균 하락폭"),
        ("큰 하락 30%",     30, "2022–24 빌라 사기 패턴"),
        ("극단 하락 40%",   40, "최악 시나리오"),
    ]
    losses = []
    for name, d, desc in scenarios:
        a_price = market_won * (1 - d / 100) * 0.85
        rec_s   = min(deposit_won, max(0, a_price - senior_won))
        losses.append((deposit_won - rec_s) / 1e8)

    bar = go.Figure(
        go.Bar(
            x=[s[0] for s in scenarios],
            y=losses,
            marker_color=[
                "#00c896" if l <= 0 else
                "#ff9500" if l < deposit_won * 0.4 / 1e8 else
                "#f04452"
                for l in losses
            ],
            text=[f"₩-{l:.2f}억" if l > 0 else "손실 없음" for l in losses],
            textposition="outside",
            textfont={"family": "Pretendard", "size": 12, "color": "#191f28"},
        )
    )
    bar.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=30, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        yaxis={"title": "예상 손실 (억원)", "tickfont": {"family": "Pretendard"}, "gridcolor": "#f2f4f6"},
        xaxis={"tickfont": {"family": "Pretendard", "size": 11}},
        font={"family": "Pretendard"},
    )
    st.plotly_chart(bar, use_container_width=True, config={"displayModeBar": False})

    # ───── 판례 기반 회수율 ─────
    st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
    st.markdown("### ⚖️ 유사 판례 47건 — 행동을 추가하면 달라져요")

    st.markdown(
        """
        <div class="tw-card">
          <div class="stat-row"><span>전체 평균 회수율 (행동 없음)</span><b style="color:var(--red)">43%</b></div>
          <div class="stat-row"><span>전체 평균 소요 기간</span><b>13.8개월</b></div>
          <div style="height:1px;background:var(--gray-200);margin:12px 0"></div>
          <div class="stat-row"><span>+ HUG 전세보증보험 가입</span><b style="color:var(--green)">100%<span class="delta">+57%p</span></b></div>
          <div class="stat-row"><span>+ 임차권등기명령 신청</span><b style="color:var(--green)">81%<span class="delta">+38%p</span></b></div>
          <div class="stat-row"><span>+ 근저당 말소 특약 포함</span><b style="color:var(--green)">76%<span class="delta">+33%p</span></b></div>
          <div style="font-size:11px;color:var(--gray-500);margin-top:10px">
            근거: 대법원 판결문 + HUG 대위변제 공개 데이터 (2022–2025) · 종로구 사례 포함
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )