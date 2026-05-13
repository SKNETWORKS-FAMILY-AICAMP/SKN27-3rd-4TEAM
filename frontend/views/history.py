"""진단 기록 — 필터 / 정렬 / 즐겨찾기 / 비교."""

import streamlit as st


RECORDS = [
    {"id": 1, "addr": "종로구 명륜2가 35-12 한빛빌라 302호", "deposit": "₩2.5억", "area": "42㎡", "year": "2018년식", "score": 78, "level": "danger", "date": "5/8", "fav": True, "tags": ["근저당", "신탁의심"], "ratio": "91%", "senior": "₩2.1억", "hug": "확인 필요"},
    {"id": 2, "addr": "종로구 익선동 ○○빌라 201호", "deposit": "₩1.8억", "area": "36㎡", "year": "2012년식", "score": 62, "level": "caution", "date": "5/4", "fav": False, "tags": ["다가구"], "ratio": "82%", "senior": "₩0.8억", "hug": "가능성 낮음"},
    {"id": 3, "addr": "종로구 혜화동 ○○ 빌라 5층", "deposit": "₩2.2억", "area": "50㎡", "year": "2020년식", "score": 24, "level": "safe", "date": "4/29", "fav": True, "tags": ["HUG가능"], "ratio": "63%", "senior": "없음", "hug": "가능"},
    {"id": 4, "addr": "종로구 창신동 ○○ 오피스텔 1102호", "deposit": "₩1.6억", "area": "29㎡", "year": "2016년식", "score": 88, "level": "danger", "date": "4/22", "fav": False, "tags": ["신탁등기"], "ratio": "96%", "senior": "₩1.5억", "hug": "거절 가능"},
    {"id": 5, "addr": "종로구 명륜1가 ○○빌라 401호", "deposit": "₩2.0억", "area": "44㎡", "year": "2014년식", "score": 41, "level": "caution", "date": "4/18", "fav": False, "tags": ["근저당소액"], "ratio": "74%", "senior": "₩0.3억", "hug": "가능성 있음"},
    {"id": 6, "addr": "종로구 누상동 ○○ 빌라 302호", "deposit": "₩1.9억", "area": "48㎡", "year": "2021년식", "score": 19, "level": "safe", "date": "4/12", "fav": False, "tags": ["안전"], "ratio": "58%", "senior": "없음", "hug": "가능"},
]

LEVEL_KO = {"danger": "위험", "caution": "주의", "safe": "안전"}


def _init_state():
    if "compare_set" not in st.session_state:
        st.session_state.compare_set = set()
    if "favorites" not in st.session_state:
        st.session_state.favorites = {rec["id"] for rec in RECORDS if rec["fav"]}


def _record_card(rec):
    is_fav = rec["id"] in st.session_state.favorites
    is_selected = rec["id"] in st.session_state.compare_set
    star = "★" if is_fav else "☆"
    star_color = "var(--amber)" if is_fav else "var(--gray-300)"
    tags_html = "".join(
        f'<span style="background:var(--gray-100);padding:3px 8px;border-radius:999px;font-size:11px;color:var(--gray-700);margin-right:4px">#{t}</span>'
        for t in rec["tags"]
    )

    st.markdown(
        f"""
        <div class="hist-card {'selected' if is_selected else ''}">
          <div class="top">
            <span class="dot {rec['level']}"></span>
            <span style="color:var(--gray-500);font-size:12px;font-weight:800">{rec['date']} 진단</span>
          </div>
          <div style="display:flex;gap:10px;justify-content:space-between;align-items:flex-start">
            <div class="addr" style="padding-right:8px">{rec['addr']}</div>
            <span style="color:{star_color};font-size:22px;line-height:1">{star}</span>
          </div>
          <div class="meta">{rec['deposit']} · {rec['area']} · {rec['year']}</div>
          <div class="score-row">
            <b class="{rec['level']}">{rec['score']}</b>
            <small>/ 100 · {LEVEL_KO[rec['level']]}</small>
          </div>
          <div style="margin-top:10px">{tags_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    a1, a2, a3 = st.columns([0.9, 1, 1])
    with a1:
        if st.button(star, key=f"fav_{rec['id']}", use_container_width=True, help="즐겨찾기"):
            if is_fav:
                st.session_state.favorites.remove(rec["id"])
            else:
                st.session_state.favorites.add(rec["id"])
            st.rerun()
    with a2:
        if st.button("자세히", key=f"open_{rec['id']}", use_container_width=True):
            st.session_state.selected_record_id = rec["id"]
            st.session_state.current_view = "property"
            st.query_params.clear()
            st.rerun()
    with a3:
        cmp_label = "비교 해제" if is_selected else "비교 담기"
        if st.button(cmp_label, key=f"cmp_{rec['id']}", use_container_width=True, type="primary" if is_selected else "secondary"):
            if is_selected:
                st.session_state.compare_set.remove(rec["id"])
            else:
                if len(st.session_state.compare_set) >= 2:
                    st.toast("비교는 두 매물까지 선택할 수 있어요.")
                else:
                    st.session_state.compare_set.add(rec["id"])
            st.rerun()


def _compare_panel(selected):
    if len(selected) < 2:
        return
    st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)
    st.markdown("## 선택 매물 나란히 비교")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">비교 담기한 두 매물의 핵심 위험 요소를 양옆으로 확인합니다.</p>',
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for col, rec in zip(cols, selected[:2]):
        with col:
            tags_html = "".join(
                f'<span style="background:var(--gray-100);padding:3px 8px;border-radius:999px;font-size:11px;color:var(--gray-700);margin-right:4px">#{t}</span>'
                for t in rec["tags"]
            )
            st.markdown(
                f"""
                <div class="compare-card">
                  <div class="top"><span class="dot {rec['level']}"></span><b>{LEVEL_KO[rec['level']]}</b></div>
                  <h3>{rec['addr']}</h3>
                  <div class="compare-score {rec['level']}">{rec['score']}점</div>
                  <div class="compare-row"><span>보증금</span><b>{rec['deposit']}</b></div>
                  <div class="compare-row"><span>면적</span><b>{rec['area']}</b></div>
                  <div class="compare-row"><span>준공</span><b>{rec['year']}</b></div>
                  <div class="compare-row"><span>전세가율</span><b>{rec['ratio']}</b></div>
                  <div class="compare-row"><span>선순위 권리</span><b>{rec['senior']}</b></div>
                  <div class="compare-row"><span>보증보험</span><b>{rec['hug']}</b></div>
                  <div style="margin-top:12px">{tags_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render():
    _init_state()
    st.markdown(
        '<div style="font-size:12px;font-weight:700;color:var(--gray-500);'
        'letter-spacing:.04em;margin-bottom:6px">진단 기록 · 6건 저장됨</div>',
        unsafe_allow_html=True,
    )
    st.markdown("# 검토한 매물 한눈에 비교")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:14px">'
        "즐겨찾기와 비교 담기로 안전한 매물을 골라보세요.</p>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 1])
    with c1:
        st.text_input("주소 검색", placeholder="동 이름 또는 주소", label_visibility="collapsed")
    with c2:
        st.selectbox("위험도", ["전체", "위험만", "주의만", "안전만", "즐겨찾기만"], label_visibility="collapsed")
    with c3:
        st.selectbox("정렬", ["최신순", "위험도 높은순", "위험도 낮은순", "보증금 높은순"], label_visibility="collapsed")
    with c4:
        st.button("+ 새 진단", type="primary", use_container_width=True)

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    s1, s2, s3, s4 = st.columns(4)
    summary = [("총 진단", "6건", "gray"), ("위험", "2건", "red"), ("주의", "2건", "amber"), ("안전", "2건", "green")]
    for col, (label, value, tone) in zip((s1, s2, s3, s4), summary):
        color = f"var(--{tone})" if tone != "gray" else "var(--gray-900)"
        bg = "#fff" if tone == "gray" else f"var(--{tone}-soft)"
        with col:
            st.markdown(
                f'<div class="tw-card" style="text-align:center;background:{bg}">'
                f'<div style="font-size:11px;color:{color};font-weight:700;letter-spacing:.06em">{label}</div>'
                f'<div style="font-size:32px;font-weight:800;margin-top:6px;color:{color}">{value}</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)

    for row_start in range(0, len(RECORDS), 3):
        cols = st.columns(3)
        for i, rec in enumerate(RECORDS[row_start:row_start + 3]):
            with cols[i]:
                _record_card(rec)
        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)

    selected = [r for r in RECORDS if r["id"] in st.session_state.compare_set]
    if selected:
        st.markdown(
            f"""
            <div style="position:sticky;bottom:0;background:#fff;border:1px solid var(--gray-200);
                        border-radius:14px;padding:14px 18px;box-shadow:0 -4px 12px rgba(0,0,0,.06);
                        margin-top:24px;display:flex;align-items:center;gap:12px;justify-content:space-between;z-index:10">
              <div>
                <b>비교 담은 매물 {len(selected)}건</b>
                <span style="color:var(--gray-500);font-size:13px;margin-left:8px">
                  {' · '.join([r['addr'].split()[1] for r in selected])}
                </span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if len(selected) == 2:
            _compare_panel(selected)
        else:
            st.info("비교할 매물을 하나 더 담으면 아래에 양옆 비교 화면이 나타납니다.")


