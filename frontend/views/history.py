"""Diagnosis history page with saved property cards and comparison."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import requests
import streamlit as st


BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")


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


def fetch_diagnosis_logs(limit: int = 30) -> list[dict[str, Any]]:
    """백엔드 진단 기록 API에서 최근 진단 로그를 가져온다."""
    response = requests.get(
        f"{BACKEND_BASE_URL}/api/v1/diagnosis/logs",
        params={"limit": limit},
        timeout=5,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("logs", [])


def delete_diagnosis_log(log_id: int) -> None:
    """백엔드 진단 기록 API에서 특정 로그를 삭제한다."""
    response = requests.delete(
        f"{BACKEND_BASE_URL}/api/v1/diagnosis/logs/{log_id}",
        timeout=5,
    )
    response.raise_for_status()


def normalize_backend_record(row: dict[str, Any]) -> dict[str, Any]:
    """백엔드 diagnosis_logs 행을 기존 진단 기록 카드 형식으로 변환한다."""
    score = int(float(row.get("risk_score") or 0))
    level = _normalize_level(row.get("risk_level"), score)
    created_at = _format_created_at(row.get("created_at"))
    summary = str(row.get("result_summary") or "").strip()
    session_id = str(row.get("session_id") or "")

    return {
        "id": row.get("id") or session_id or f"log-{created_at}",
        "addr": _summary_title(summary, session_id),
        "deposit": "-",
        "area": "-",
        "year": "-",
        "score": score,
        "level": level,
        "date": created_at,
        "fav": False,
        "tags": _tags_from_summary(summary, level),
        "ratio": "-",
        "senior": "-",
        "hug": "-",
        "summary": summary,
        "session_id": session_id,
    }


def _normalize_level(value: Any, score: int) -> str:
    """백엔드 위험 등급 표현을 화면용 danger/caution/safe로 정규화한다."""
    text = str(value or "").upper()
    if text in {"위험", "DANGER", "HIGH", "CRITICAL"}:
        return "danger"
    if text in {"주의", "CAUTION", "MEDIUM"}:
        return "caution"
    if text in {"안전", "SAFE", "LOW"}:
        return "safe"
    if score >= 70:
        return "danger"
    if score >= 40:
        return "caution"
    return "safe"


def _format_created_at(value: Any) -> str:
    """created_at 값을 카드 날짜 문자열로 표시한다."""
    if not value:
        return "-"
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return f"{parsed.month}/{parsed.day}"
    except ValueError:
        return text[:10]


def _summary_title(summary: str, session_id: str) -> str:
    """요약문에서 카드 제목으로 쓸 첫 문장을 만든다."""
    if summary:
        first_line = summary.splitlines()[0].strip()
        return first_line[:42] + ("..." if len(first_line) > 42 else "")
    return f"진단 기록 {session_id[:8]}" if session_id else "진단 기록"


def _tags_from_summary(summary: str, level: str) -> list[str]:
    """요약문과 위험 등급을 기반으로 간단한 태그를 만든다."""
    tags: list[str] = [LEVEL_KO.get(level, "진단")]
    keyword_map = {
        "근저당": "근저당",
        "신탁": "신탁등기",
        "특약": "특약",
        "전세가": "전세가율",
        "보증보험": "보증보험",
    }
    for keyword, label in keyword_map.items():
        if keyword in summary and label not in tags:
            tags.append(label)
    return tags[:3]


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
    if "history_records" not in st.session_state:
        st.session_state.history_records = RECORDS
    if "history_source" not in st.session_state:
        st.session_state.history_source = "demo"
    if "history_api_error" not in st.session_state:
        st.session_state.history_api_error = None
    if "compare_set" not in st.session_state:
        st.session_state.compare_set = set()
    if "history_favorites" not in st.session_state:
        st.session_state.history_favorites = {rec["id"] for rec in st.session_state.history_records if rec["fav"]}


def _load_backend_records() -> None:
    """백엔드 진단 기록을 세션 상태에 적재하고 실패 시 데모 데이터를 유지한다."""
    try:
        logs = fetch_diagnosis_logs()
        if logs:
            st.session_state.history_records = [normalize_backend_record(row) for row in logs]
            st.session_state.history_source = "backend"
            st.session_state.history_api_error = None
        else:
            st.session_state.history_records = []
            st.session_state.history_source = "backend"
            st.session_state.history_api_error = None
    except requests.RequestException as exc:
        st.session_state.history_records = RECORDS
        st.session_state.history_source = "demo"
        st.session_state.history_api_error = str(exc)


def _delete_record(rec: dict[str, Any]) -> None:
    """진단 기록 카드 삭제 버튼 처리."""
    rec_id = rec["id"]
    if st.session_state.history_source == "backend":
        try:
            delete_diagnosis_log(int(rec_id))
            _load_backend_records()
            st.session_state.compare_set.discard(rec_id)
            st.session_state.history_favorites.discard(rec_id)
            st.toast("진단 기록을 삭제했습니다.")
        except requests.exceptions.HTTPError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            st.error(f"진단 기록 삭제 실패: {detail}")
        except Exception as exc:
            st.error(f"진단 기록 삭제 중 오류가 발생했습니다: {exc}")
        return

    st.session_state.history_records = [item for item in st.session_state.history_records if item["id"] != rec_id]
    st.session_state.compare_set.discard(rec_id)
    st.session_state.history_favorites.discard(rec_id)
    st.toast("데모 진단 기록을 화면에서 삭제했습니다.")


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

    records = st.session_state.history_records
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
    detail_col, compare_col, delete_col = st.columns(3)
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
    with delete_col:
        if st.button("삭제", key=f"del_{rec['id']}", use_container_width=True):
            _delete_record(rec)
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
    if not st.session_state.get("history_loaded"):
        _load_backend_records()
        st.session_state.history_loaded = True
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

    refresh_col, source_col = st.columns([0.25, 1.75])
    with refresh_col:
        if st.button("새로고침", use_container_width=True):
            _load_backend_records()
            st.rerun()
    with source_col:
        if st.session_state.history_source == "backend":
            st.caption(f"백엔드 `{BACKEND_BASE_URL}`의 진단 기록을 표시 중입니다.")
        else:
            st.warning(
                "백엔드 진단 기록 API에 연결하지 못해 데모 기록을 표시 중입니다. "
                "FastAPI 서버와 DB가 켜져 있는지 확인해 주세요.",
                icon="⚠️",
            )

    st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)

    summary_cols = st.columns(4)
    all_records = st.session_state.history_records
    summary = [
        ("총 진단", f"{len(all_records)}건", "gray"),
        ("위험", f"{sum(1 for rec in all_records if rec['level'] == 'danger')}건", "danger"),
        ("주의", f"{sum(1 for rec in all_records if rec['level'] == 'caution')}건", "caution"),
        ("안전", f"{sum(1 for rec in all_records if rec['level'] == 'safe')}건", "safe"),
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

    selected = [rec for rec in all_records if rec["id"] in st.session_state.compare_set]
    if selected:
        names = " · ".join(rec["addr"].split()[1] if len(rec["addr"].split()) > 1 else rec["addr"] for rec in selected)
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
