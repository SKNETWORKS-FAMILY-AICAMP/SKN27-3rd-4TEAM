"""Diagnosis history page with saved property cards and comparison."""

from __future__ import annotations

import streamlit as st


RECORDS = [
    {
        "id": 1,
        "addr": "종로구 명륜2가 35-12 한빛빌라 302호",
        "deposit": "₩2.5억",
        "area": "42m²",
        "year": "2018년식",
        "score": 78,
        "level": "danger",
        "date": "5/8",
        "fav": True,
        "tags": ["근저당", "신탁의심"],
        "ratio": "91%",
        "senior": "₩2.1억",
        "hug": "확인 필요",
    },
    {
        "id": 2,
        "addr": "종로구 익선동 OO빌라 201호",
        "deposit": "₩1.8억",
        "area": "36m²",
        "year": "2012년식",
        "score": 62,
        "level": "caution",
        "date": "5/4",
        "fav": False,
        "tags": ["다가구"],
        "ratio": "82%",
        "senior": "₩0.8억",
        "hug": "가능성 낮음",
    },
    {
        "id": 3,
        "addr": "종로구 혜화동 OO 빌라 5층",
        "deposit": "₩2.2억",
        "area": "50m²",
        "year": "2020년식",
        "score": 24,
        "level": "safe",
        "date": "4/29",
        "fav": True,
        "tags": ["HUG가능"],
        "ratio": "63%",
        "senior": "없음",
        "hug": "가능",
    },
    {
        "id": 4,
        "addr": "종로구 창신동 OO 오피스텔 1102호",
        "deposit": "₩1.6억",
        "area": "29m²",
        "year": "2016년식",
        "score": 88,
        "level": "danger",
        "date": "4/22",
        "fav": False,
        "tags": ["신탁등기"],
        "ratio": "96%",
        "senior": "₩1.5억",
        "hug": "거절 가능",
    },
    {
        "id": 5,
        "addr": "종로구 명륜1가 OO빌라 401호",
        "deposit": "₩2.0억",
        "area": "44m²",
        "year": "2014년식",
        "score": 41,
        "level": "caution",
        "date": "4/18",
        "fav": False,
        "tags": ["근저당소액"],
        "ratio": "74%",
        "senior": "₩0.3억",
        "hug": "가능성 있음",
    },
    {
        "id": 6,
        "addr": "종로구 누상동 OO 빌라 302호",
        "deposit": "₩1.9억",
        "area": "48m²",
        "year": "2021년식",
        "score": 19,
        "level": "safe",
        "date": "4/12",
        "fav": False,
        "tags": ["안전"],
        "ratio": "58%",
        "senior": "없음",
        "hug": "가능",
    },
]

LEVEL_KO = {"danger": "위험", "caution": "주의", "safe": "안전"}
LEVEL_COLOR = {"danger": "var(--red)", "caution": "var(--amber)", "safe": "var(--green)"}
LEVEL_BG = {"danger": "var(--red-soft)", "caution": "var(--amber-soft)", "safe": "var(--green-soft)"}


def _history_css() -> str:
    return """
    <style>
      .stApp { overflow-x: hidden; }
      .block-container {
        max-width: 1160px !important;
        padding-top: 2rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
      }
      header[data-testid="stHeader"] { background: transparent; }
      div[data-testid="stSidebarCollapsedControl"] { display: none !important; }
      .history-page-title {
        margin: 0;
        color: var(--gray-900);
        font-size: 32px;
        line-height: 1.22;
        font-weight: 900;
        letter-spacing: 0;
      }
      .history-page-copy {
        margin: 10px 0 20px;
        color: var(--gray-500);
        font-size: 14px;
        font-weight: 600;
      }
      .history-stat {
        min-height: 120px;
        padding: 24px;
        border: 1px solid var(--gray-200);
        border-radius: 16px;
        background: #fff;
        text-align: center;
      }
      .history-stat .label { font-size: 12px; font-weight: 900; }
      .history-stat .value {
        margin-top: 10px;
        font-size: 34px;
        line-height: 1;
        font-weight: 900;
      }
      .history-card {
        min-height: 200px;
        padding: 18px;
        border: 1px solid var(--gray-200);
        border-radius: 14px 14px 0 0;
        background: #fff;
      }
      .history-card-top {
        display: grid;
        grid-template-columns: 1fr 34px;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;
      }
      .history-left {
        display: flex;
        align-items: center;
        gap: 10px;
        min-width: 0;
      }
      .history-dot {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        display: inline-block;
        flex: 0 0 auto;
      }
      .history-date {
        color: var(--gray-500);
        font-size: 12px;
        font-weight: 900;
      }
      .history-star-link {
        width: 34px !important;
        height: 34px !important;
        display: grid !important;
        place-items: center !important;
        cursor: pointer !important;
        color: var(--gray-300) !important;
        font-size: 27px !important;
        line-height: 1 !important;
        font-weight: 900 !important;
        border-radius: 8px !important;
        text-decoration: none !important;
      }
      .history-star-link:hover {
        background: var(--amber-soft) !important;
        color: var(--amber) !important;
      }
      .history-star-link.is-fav {
        color: var(--amber) !important;
      }
      .history-addr {
        color: var(--gray-900);
        font-size: 15px;
        line-height: 1.4;
        font-weight: 900;
      }
      .history-meta {
        margin-top: 7px;
        color: var(--gray-500);
        font-size: 12px;
        font-weight: 700;
      }
      .history-score {
        margin-top: 20px;
        display: flex;
        align-items: baseline;
        gap: 4px;
      }
      .history-score b {
        font-size: 32px;
        line-height: 1;
        font-weight: 900;
      }
      .history-score span {
        color: var(--gray-500);
        font-size: 13px;
        font-weight: 900;
      }
      .history-tags {
        margin-top: 22px;
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
      .history-tag {
        padding: 4px 8px;
        border-radius: 999px;
        background: var(--gray-100);
        color: var(--gray-700);
        font-size: 11px;
        font-weight: 800;
      }
      .history-actions { margin-top: -1px; }
      .history-actions div.stButton > button {
        min-height: 41px;
        border-radius: 0 0 10px 10px;
        background: #fff;
      }
      .history-actions div.stButton > button[kind="primary"] {
        background: var(--blue);
        border-color: var(--blue);
        color: #fff;
      }
      .history-compare-bar {
        position: sticky;
        bottom: 0;
        z-index: 10;
        margin-top: 24px;
        padding: 14px 18px;
        border: 1px solid var(--gray-200);
        border-radius: 14px;
        background: #fff;
        box-shadow: 0 -4px 12px rgba(15, 23, 42, .08);
      }
      .history-compare-bar b { color: var(--gray-900); }
      .history-compare-bar span {
        margin-left: 8px;
        color: var(--gray-500);
        font-size: 13px;
        font-weight: 700;
      }
      @media (max-width: 900px) {
        .history-page-title { font-size: 26px; }
      }
    </style>
    """


def _init_state():
    if "compare_set" not in st.session_state:
        st.session_state.compare_set = set()
    if "history_favorites" not in st.session_state:
        st.session_state.history_favorites = {rec["id"] for rec in RECORDS if rec["fav"]}


def _go(view: str):
    st.session_state.current_view = view
    st.query_params.clear()
    st.rerun()


def _handle_favorite_query():
    fav_values = st.query_params.get_all("fav") if hasattr(st.query_params, "get_all") else []
    fav_id = fav_values[0] if fav_values else st.query_params.get("fav")
    if not fav_id:
        return
    try:
        rec_id = int(fav_id)
    except ValueError:
        st.query_params.clear()
        st.rerun()

    favorites = st.session_state.history_favorites
    if rec_id in favorites:
        favorites.remove(rec_id)
    else:
        favorites.add(rec_id)
    st.query_params.clear()
    st.rerun()


def _filtered_records():
    query = st.session_state.get("history_query", "").strip()
    level_filter = st.session_state.get("history_level", "전체")
    sort_key = st.session_state.get("history_sort", "최신순")
    favorites = st.session_state.history_favorites

    records = RECORDS
    if query:
        records = [rec for rec in records if query in rec["addr"]]
    if level_filter == "즐겨찾기만":
        records = [rec for rec in records if rec["id"] in favorites]
    elif level_filter != "전체":
        level_map = {"위험만": "danger", "주의만": "caution", "안전만": "safe"}
        records = [rec for rec in records if rec["level"] == level_map[level_filter]]

    if sort_key == "위험도 높은순":
        records = sorted(records, key=lambda rec: rec["score"], reverse=True)
    elif sort_key == "위험도 낮은순":
        records = sorted(records, key=lambda rec: rec["score"])
    elif sort_key == "보증금 높은순":
        records = sorted(records, key=lambda rec: rec["deposit"], reverse=True)

    return records


def _summary_card(label: str, value: str, tone: str):
    color = "var(--gray-900)" if tone == "gray" else LEVEL_COLOR[tone]
    bg = "#fff" if tone == "gray" else LEVEL_BG[tone]
    st.markdown(
        f"""
        <div class="history-stat" style="background:{bg}">
          <div class="label" style="color:{color}">{label}</div>
          <div class="value" style="color:{color}">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _record_card(rec):
    favorites = st.session_state.history_favorites
    is_fav = rec["id"] in favorites
    is_selected = rec["id"] in st.session_state.compare_set
    color = LEVEL_COLOR[rec["level"]]
    tags_html = "".join(f'<span class="history-tag">#{tag}</span>' for tag in rec["tags"])
    star_class = "history-star-link is-fav" if is_fav else "history-star-link"

    st.markdown(
        f"""
        <div class="history-card">
          <div class="history-card-top">
            <div class="history-left">
              <span class="history-dot" style="background:{color};box-shadow:0 0 0 5px {LEVEL_BG[rec['level']]}"></span>
              <span class="history-date">{rec['date']} 진단</span>
            </div>
            <a class="{star_class}" href="?view=history&fav={rec['id']}" target="_self" aria-label="즐겨찾기 토글">★</a>
          </div>
          <div class="history-addr">{rec['addr']}</div>
          <div class="history-meta">{rec['deposit']} · {rec['area']} · {rec['year']}</div>
          <div class="history-score">
            <b style="color:{color}">{rec['score']}</b>
            <span>/ 100 · {LEVEL_KO[rec['level']]}</span>
          </div>
          <div class="history-tags">{tags_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="history-actions">', unsafe_allow_html=True)
    detail_col, compare_col = st.columns(2)
    with detail_col:
        if st.button("자세히", key=f"open_{rec['id']}", use_container_width=True):
            st.session_state.selected_record_id = rec["id"]
            _go("property")
    with compare_col:
        cmp_label = "비교 해제" if is_selected else "비교 담기"
        if st.button(
            cmp_label,
            key=f"cmp_{rec['id']}",
            use_container_width=True,
            type="primary" if is_selected else "secondary",
        ):
            if is_selected:
                st.session_state.compare_set.remove(rec["id"])
            elif len(st.session_state.compare_set) >= 2:
                st.toast("비교는 최대 2개 매물까지 선택할 수 있어요.")
            else:
                st.session_state.compare_set.add(rec["id"])
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _compare_panel(selected):
    if len(selected) < 2:
        return

    st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)
    st.markdown("## 선택 매물 위험 요소 비교")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
        "비교 담기로 선택한 매물의 핵심 위험 요소를 나란히 확인합니다.</p>",
        unsafe_allow_html=True,
    )

    cols = st.columns(2)
    for col, rec in zip(cols, selected[:2]):
        with col:
            tags_html = "".join(
                f'<span style="background:var(--gray-100);padding:3px 8px;border-radius:999px;font-size:11px;color:var(--gray-700);margin-right:4px">#{tag}</span>'
                for tag in rec["tags"]
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
    _handle_favorite_query()
    st.markdown(_history_css(), unsafe_allow_html=True)
    st.markdown('<div class="history-page-title">진단 기록</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="history-page-copy">즐겨찾기와 비교 담기로 안전한 매물을 골라보세요.</div>',
        unsafe_allow_html=True,
    )

    q_col, level_col, sort_col, add_col = st.columns([1.55, 1.15, 1.15, 0.75])
    with q_col:
        st.text_input("주소 검색", placeholder="동 이름 또는 주소", key="history_query", label_visibility="collapsed")
    with level_col:
        st.selectbox(
            "위험도",
            ["전체", "즐겨찾기만", "위험만", "주의만", "안전만"],
            key="history_level",
            label_visibility="collapsed",
        )
    with sort_col:
        st.selectbox(
            "정렬",
            ["최신순", "위험도 높은순", "위험도 낮은순", "보증금 높은순"],
            key="history_sort",
            label_visibility="collapsed",
        )
    with add_col:
        if st.button("+ 새 진단", type="primary", use_container_width=True):
            _go("chat")

    st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)

    summary_cols = st.columns(4)
    summary = [
        ("총 진단", f"{len(RECORDS)}건", "gray"),
        ("위험", f"{sum(1 for rec in RECORDS if rec['level'] == 'danger')}건", "danger"),
        ("주의", f"{sum(1 for rec in RECORDS if rec['level'] == 'caution')}건", "caution"),
        ("안전", f"{sum(1 for rec in RECORDS if rec['level'] == 'safe')}건", "safe"),
    ]
    for col, (label, value, tone) in zip(summary_cols, summary):
        with col:
            _summary_card(label, value, tone)

    st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)

    records = _filtered_records()
    if not records:
        st.info("조건에 맞는 진단 기록이 없습니다.")
        return

    for row_start in range(0, len(records), 3):
        cols = st.columns(3)
        for col, rec in zip(cols, records[row_start:row_start + 3]):
            with col:
                _record_card(rec)
        st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)

    selected = [rec for rec in RECORDS if rec["id"] in st.session_state.compare_set]
    if selected:
        names = " · ".join(rec["addr"].split()[1] for rec in selected)
        st.markdown(
            f"""
            <div class="history-compare-bar">
              <b>비교 담은 매물 {len(selected)}건</b>
              <span>{names}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if len(selected) == 2:
            _compare_panel(selected)
        else:
            st.info("비교할 매물을 하나 더 담으면 아래에 나란히 비교 화면이 표시됩니다.")
