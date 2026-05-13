"""대시보드형 홈 화면 — 사이드바 홈 버튼에서 진입."""

import streamlit as st


def _go(view: str):
    st.session_state.current_view = view
    st.query_params.clear()
    st.rerun()


def render():
    st.markdown(
        """
        <div class="home-hero">
          <div>
            <div class="eyebrow">안전한 부동산 거래를 위한 AI 분석</div>
            <h1>내 전세 계약, 위험 신호부터 주변 시세까지 한 번에 확인하세요</h1>
            <p>현재 매물의 위험도와 주변 보증금 흐름, 계약 전 체크리스트를 대시보드에서 이어서 점검합니다.</p>
          </div>
          <div class="home-hero-card">
            <span>현재 분석 매물</span>
            <b>명륜2가 한빛빌라 302호</b>
            <small>전세 ₩2.5억 · 전세가율 91% · 위험 78점</small>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    metrics = [
        ("총 거래 건수", "3,245건", "전월 대비 +12.4%", "blue"),
        ("평균 전세 보증금", "2.68억원", "전월 대비 +5.7%", "green"),
        ("평균 면적", "57.3㎡", "전월 대비 -1.3%", "violet"),
        ("거래 연도", "2025년 5월", "데이터 기준", "orange"),
    ]
    for col, (label, value, delta, tone) in zip((c1, c2, c3, c4), metrics):
        with col:
            st.markdown(
                f"""
                <div class="dash-metric {tone}">
                  <span>{label}</span>
                  <b>{value}</b>
                  <small>{delta}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)

    map_col, side_col = st.columns([1.75, 1])
    with map_col:
        st.markdown(
            """
            <div class="dash-panel">
              <div class="panel-head"><b>종로구 동별 평당 보증금 지도</b><span>최근 거래 기준</span></div>
              <div class="price-map">
                <div class="map-title-chip">종로구 주요 동 평당 보증금</div>
                <div class="map-price-pin cool" style="left:14%;top:31%">
                  <div class="dot"></div><div class="label"><b>부암동</b><span>1,480만원/평</span></div>
                </div>
                <div class="map-price-pin cool" style="left:30%;top:53%">
                  <div class="dot"></div><div class="label"><b>무악동</b><span>1,655만원/평</span></div>
                </div>
                <div class="map-price-pin warm" style="left:45%;top:38%">
                  <div class="dot"></div><div class="label"><b>교남동</b><span>1,725만원/평</span></div>
                </div>
                <div class="map-price-pin hot active" style="left:60%;top:27%">
                  <div class="dot"></div><div class="label"><b>평창동</b><span>1,950만원/평</span></div>
                </div>
                <div class="map-price-pin warm" style="left:61%;top:60%">
                  <div class="dot"></div><div class="label"><b>삼청동</b><span>1,785만원/평</span></div>
                </div>
                <div class="map-price-pin cool" style="left:78%;top:46%">
                  <div class="dot"></div><div class="label"><b>혜화동</b><span>1,670만원/평</span></div>
                </div>
                <div class="current-property-pin">현재 매물</div>
                <div class="map-watermark">JONGNO PRICE MAP</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with side_col:
        st.markdown(
            """
            <div class="dash-panel selected-region">
              <div class="panel-head"><b>평창동</b><span>선택 지역</span></div>
              <div class="mini-stat"><span>평균 평당 보증금</span><b class="red">1,950만원</b></div>
              <div class="mini-stat"><span>거래 건수</span><b>318건</b></div>
              <div class="mini-stat"><span>평균 면적</span><b>60.2㎡</b></div>
              <div class="mini-stat"><span>주요 매물 유형</span><b>아파트·연립</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)

    q1, q2, q3 = st.columns(3)
    with q1:
        if st.button("🗺️ 지역별 시세", use_container_width=True, type="primary"):
            _go("market")
    with q2:
        if st.button("🤖 챗봇", use_container_width=True):
            _go("chat")
    with q3:
        if st.button("📋 계약 체크리스트", use_container_width=True):
            _go("checklist")

    st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)

    b1, b2, b3 = st.columns([1.2, 1, 1])
    with b1:
        st.markdown(
            """
            <div class="dash-panel">
              <div class="panel-head"><b>확인 우선순위</b><span>계약 전</span></div>
              <div class="rank-row"><b>1</b><span>근저당 말소 특약 확인</span><em>치명</em></div>
              <div class="rank-row"><b>2</b><span>HUG 가입 가능 여부 조회</span><em>높음</em></div>
              <div class="rank-row"><b>3</b><span>주변 동일 면적 시세 비교</span><em>필수</em></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with b2:
        st.markdown(
            """
            <div class="dash-panel">
              <div class="panel-head"><b>동별 평당 보증금 TOP 5</b><span>만원/평</span></div>
              <div class="bar-row"><span>평창동</span><i style="width:92%"></i><b>1,950</b></div>
              <div class="bar-row"><span>이화동</span><i style="width:83%"></i><b>1,835</b></div>
              <div class="bar-row"><span>삼청동</span><i style="width:77%"></i><b>1,785</b></div>
              <div class="bar-row"><span>가회동</span><i style="width:68%"></i><b>1,720</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with b3:
        st.markdown(
            """
            <div class="dash-panel">
              <div class="panel-head"><b>주요 매물 유형</b><span>전체</span></div>
              <div class="donut"></div>
              <div class="legend-row"><span style="background:#3182f6"></span>아파트 48.6%</div>
              <div class="legend-row"><span style="background:#20c7bd"></span>연립·다세대 26.7%</div>
              <div class="legend-row"><span style="background:#ff9f43"></span>오피스텔 15.3%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
