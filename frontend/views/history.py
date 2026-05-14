"""Diagnosis history page backed by the real diagnosis API."""

from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Any

import requests
import streamlit as st


BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")

LEVEL_KO = {"danger": "위험", "caution": "주의", "safe": "안전"}
LEVEL_COLOR = {"danger": "var(--red)", "caution": "var(--amber)", "safe": "var(--green)"}
LEVEL_BG = {"danger": "var(--red-soft)", "caution": "var(--amber-soft)", "safe": "var(--green-soft)"}


def fetch_diagnosis_logs(limit: int = 30) -> list[dict[str, Any]]:
    response = requests.get(
        f"{BACKEND_BASE_URL}/api/v1/diagnosis/logs",
        params={"limit": limit},
        timeout=5,
    )
    response.raise_for_status()
    return response.json().get("logs", [])


def delete_diagnosis_log(log_id: int) -> None:
    response = requests.delete(f"{BACKEND_BASE_URL}/api/v1/diagnosis/logs/{log_id}", timeout=5)
    response.raise_for_status()


def normalize_backend_record(row: dict[str, Any]) -> dict[str, Any]:
    score = int(float(row.get("risk_score") or 0))
    level = _normalize_level(row.get("risk_level"), score)
    summary = str(row.get("result_summary") or "").strip()
    session_id = str(row.get("session_id") or "")
    info = row.get("contract_info") or {}
    risks = row.get("risk_factors") or []

    return {
        "id": row.get("id") or session_id or f"log-{row.get('created_at')}",
        "addr": info.get("address") or _summary_title(summary, session_id),
        "deposit": _money_text(info.get("deposit_amount")),
        "area": _area_text(info.get("area_m2")),
        "year": _year_text(info.get("contract_start")),
        "lessor": info.get("lessor_name") or "-",
        "lessee": info.get("lessee_name") or "-",
        "sale": _money_text(info.get("estimated_sale_price")),
        "score": score,
        "level": level,
        "date": _format_created_at(row.get("created_at")),
        "fav": False,
        "tags": _tags_from_risks(risks, level),
        "ratio": _ratio_text(info.get("jeonse_ratio")),
        "senior": _risk_value(risks, ["근저당", "선순위", "권리관계"]),
        "hug": _risk_value(risks, ["보증보험", "HUG"]),
        "summary": summary,
        "session_id": session_id,
        "input_text": row.get("input_text") or "",
        "risk_factors": risks,
        "rag_references": row.get("rag_references") or [],
        "contract_info": info,
    }


def _money_text(value: Any) -> str:
    if value in (None, "", "-"):
        return "-"
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return str(value)
    if amount >= 10000:
        return f"{amount / 10000:g}억"
    return f"{amount:,}만원"


def _area_text(value: Any) -> str:
    if value in (None, "", "-"):
        return "-"
    try:
        return f"{float(value):g}㎡"
    except (TypeError, ValueError):
        return str(value)


def _ratio_text(value: Any) -> str:
    if value in (None, "", "-"):
        return "-"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _year_text(value: Any) -> str:
    if not value:
        return "-"
    text = str(value)
    return f"{text[:4]}년" if len(text) >= 4 and text[:4].isdigit() else "-"


def _normalize_level(value: Any, score: int) -> str:
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
    if not value:
        return "-"
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return f"{parsed.month}/{parsed.day}"
    except ValueError:
        return text[:10]


def _summary_title(summary: str, session_id: str) -> str:
    if summary:
        first_line = summary.splitlines()[0].strip()
        return first_line[:42] + ("..." if len(first_line) > 42 else "")
    return f"진단 기록 {session_id[:8]}" if session_id else "진단 기록"


def _tags_from_risks(risks: list[dict[str, Any]], level: str) -> list[str]:
    tags = [LEVEL_KO.get(level, "진단")]
    for risk in risks:
        category = str(risk.get("category") or "").strip()
        description = str(risk.get("description") or "")
        for keyword, label in [
            ("근저당", "근저당"),
            ("선순위", "선순위"),
            ("보증보험", "보증보험"),
            ("특약", "특약"),
            ("전세가율", "전세가율"),
            ("가격", "가격위험"),
        ]:
            if (keyword in category or keyword in description) and label not in tags:
                tags.append(label)
    return tags[:4]


def _risk_value(risks: list[dict[str, Any]], keywords: list[str]) -> str:
    for risk in risks:
        haystack = f"{risk.get('category', '')} {risk.get('description', '')}"
        if any(keyword in haystack for keyword in keywords):
            return LEVEL_KO.get(_normalize_level(risk.get("severity"), 0), "주의")
    return "-"


def _history_css() -> str:
    return """
    <style>
      .block-container { max-width: 1160px !important; padding-top: 2rem !important; }
      .history-title { margin: 0; color: var(--gray-900); font-size: 32px; font-weight: 900; }
      .history-copy { margin: 8px 0 20px; color: var(--gray-500); font-size: 14px; font-weight: 700; }
      .history-stat {
        padding: 22px; border: 1px solid var(--gray-200); border-radius: 12px;
        background: #fff; text-align: center;
      }
      .history-stat .label { font-size: 12px; font-weight: 900; }
      .history-stat .value { margin-top: 8px; font-size: 30px; font-weight: 900; }
      .history-card {
        min-height: 190px; padding: 18px; border: 1px solid var(--gray-200);
        border-radius: 12px 12px 0 0; background: #fff;
      }
      .history-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
      .history-left { display: flex; align-items: center; gap: 9px; color: var(--gray-500); font-size: 12px; font-weight: 900; }
      .history-dot { width: 13px; height: 13px; border-radius: 50%; display: inline-block; }
      .history-addr { margin-top: 14px; color: var(--gray-900); font-size: 15px; line-height: 1.4; font-weight: 900; }
      .history-meta { margin-top: 8px; color: var(--gray-500); font-size: 12px; font-weight: 700; }
      .history-score { margin-top: 18px; display: flex; align-items: baseline; gap: 5px; }
      .history-score b { font-size: 32px; line-height: 1; font-weight: 900; }
      .history-score span { color: var(--gray-500); font-size: 13px; font-weight: 900; }
      .history-tags { margin-top: 18px; display: flex; flex-wrap: wrap; gap: 6px; }
      .history-tag {
        padding: 4px 8px; border-radius: 999px; background: var(--gray-100);
        color: var(--gray-700); font-size: 11px; font-weight: 800;
      }
      .history-actions { margin-top: -1px; }
      .history-actions div.stButton > button { min-height: 40px; border-radius: 0 0 10px 10px; }
      .compare-card {
        padding: 18px; border: 1px solid var(--gray-200); border-radius: 12px; background: #fff;
      }
      .compare-row {
        display: flex; justify-content: space-between; gap: 12px; padding: 9px 0;
        border-bottom: 1px solid var(--gray-100); font-size: 13px;
      }
      @media (max-width: 900px) { .history-title { font-size: 26px; } }
    </style>
    """


def _init_state() -> None:
    st.session_state.setdefault("history_records", [])
    st.session_state.setdefault("history_source", "backend")
    st.session_state.setdefault("history_api_error", None)
    st.session_state.setdefault("compare_set", set())
    st.session_state.setdefault("history_favorites", set())


def _load_backend_records() -> None:
    try:
        logs = fetch_diagnosis_logs()
        st.session_state.history_records = [normalize_backend_record(row) for row in logs]
        st.session_state.history_source = "backend"
        st.session_state.history_api_error = None
    except requests.RequestException as exc:
        st.session_state.history_records = []
        st.session_state.history_source = "error"
        st.session_state.history_api_error = str(exc)


def _delete_record(rec: dict[str, Any]) -> None:
    try:
        delete_diagnosis_log(int(rec["id"]))
        _load_backend_records()
        st.session_state.compare_set.discard(rec["id"])
        st.session_state.history_favorites.discard(rec["id"])
        st.toast("진단 기록을 삭제했습니다.")
    except Exception as exc:
        st.error(f"진단 기록 삭제 실패: {exc}")


def _go(view: str) -> None:
    st.session_state.current_view = view
    st.query_params.clear()
    st.rerun()


def _filtered_records() -> list[dict[str, Any]]:
    query = st.session_state.get("history_query", "").strip()
    level_filter = st.session_state.get("history_level", "전체")
    sort_key = st.session_state.get("history_sort", "최신순")
    favorites = st.session_state.history_favorites

    records = list(st.session_state.history_records)
    if query:
        records = [rec for rec in records if query in rec["addr"]]
    if level_filter == "즐겨찾기":
        records = [rec for rec in records if rec["id"] in favorites]
    elif level_filter != "전체":
        level_map = {"위험": "danger", "주의": "caution", "안전": "safe"}
        records = [rec for rec in records if rec["level"] == level_map[level_filter]]

    if sort_key == "위험도 높은순":
        records = sorted(records, key=lambda rec: rec["score"], reverse=True)
    elif sort_key == "위험도 낮은순":
        records = sorted(records, key=lambda rec: rec["score"])
    return records


def _summary_card(label: str, value: str, tone: str) -> None:
    color = "var(--gray-900)" if tone == "gray" else LEVEL_COLOR[tone]
    bg = "#fff" if tone == "gray" else LEVEL_BG[tone]
    st.markdown(
        f"""
        <div class="history-stat" style="background:{bg}">
          <div class="label" style="color:{color}">{html.escape(label)}</div>
          <div class="value" style="color:{color}">{html.escape(value)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _record_card(rec: dict[str, Any]) -> None:
    favorites = st.session_state.history_favorites
    is_fav = rec["id"] in favorites
    is_selected = rec["id"] in st.session_state.compare_set
    color = LEVEL_COLOR[rec["level"]]
    tags_html = "".join(f'<span class="history-tag">#{html.escape(tag)}</span>' for tag in rec["tags"])

    st.markdown(
        f"""
        <div class="history-card">
          <div class="history-top">
            <div class="history-left">
              <span class="history-dot" style="background:{color};box-shadow:0 0 0 5px {LEVEL_BG[rec['level']]}"></span>
              <span>{html.escape(str(rec['date']))} 진단</span>
            </div>
            <span style="color:{color};font-weight:900">{LEVEL_KO[rec['level']]}</span>
          </div>
          <div class="history-addr">{html.escape(str(rec['addr']))}</div>
          <div class="history-meta">{html.escape(str(rec['deposit']))} · {html.escape(str(rec['area']))} · {html.escape(str(rec['year']))}</div>
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
    detail_col, compare_col, fav_col, delete_col = st.columns(4)
    with detail_col:
        if st.button("상세", key=f"open_{rec['id']}", use_container_width=True):
            st.session_state.selected_record_id = rec["id"]
            _go("property")
    with compare_col:
        if st.button("비교 해제" if is_selected else "비교", key=f"cmp_{rec['id']}", use_container_width=True):
            if is_selected:
                st.session_state.compare_set.remove(rec["id"])
            elif len(st.session_state.compare_set) >= 2:
                st.toast("비교는 최대 2건까지 선택할 수 있어요.")
            else:
                st.session_state.compare_set.add(rec["id"])
            st.rerun()
    with fav_col:
        if st.button("★" if is_fav else "☆", key=f"fav_{rec['id']}", use_container_width=True):
            if is_fav:
                favorites.remove(rec["id"])
            else:
                favorites.add(rec["id"])
            st.rerun()
    with delete_col:
        if st.button("삭제", key=f"del_{rec['id']}", use_container_width=True):
            _delete_record(rec)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _compare_panel(selected: list[dict[str, Any]]) -> None:
    if len(selected) < 2:
        return
    st.markdown("### 선택 매물 위험 요소 비교")
    cols = st.columns(2)
    for col, rec in zip(cols, selected[:2]):
        with col:
            st.markdown(
                f"""
                <div class="compare-card">
                  <h4>{html.escape(str(rec['addr']))}</h4>
                  <div class="compare-row"><span>위험도</span><b>{rec['score']}점 · {LEVEL_KO[rec['level']]}</b></div>
                  <div class="compare-row"><span>보증금</span><b>{html.escape(str(rec['deposit']))}</b></div>
                  <div class="compare-row"><span>면적</span><b>{html.escape(str(rec['area']))}</b></div>
                  <div class="compare-row"><span>선순위 권리</span><b>{html.escape(str(rec['senior']))}</b></div>
                  <div class="compare-row"><span>보증보험</span><b>{html.escape(str(rec['hug']))}</b></div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render() -> None:
    _init_state()
    if not st.session_state.get("history_loaded"):
        _load_backend_records()
        st.session_state.history_loaded = True

    st.markdown(_history_css(), unsafe_allow_html=True)
    st.markdown('<div class="history-title">진단 기록</div>', unsafe_allow_html=True)
    st.markdown('<div class="history-copy">실제 업로드한 계약서 진단 결과만 표시합니다.</div>', unsafe_allow_html=True)

    q_col, level_col, sort_col, add_col = st.columns([1.55, 1.05, 1.05, 0.8])
    with q_col:
        st.text_input("주소 검색", placeholder="건물명 또는 주소", key="history_query", label_visibility="collapsed")
    with level_col:
        st.selectbox("위험도", ["전체", "즐겨찾기", "위험", "주의", "안전"], key="history_level", label_visibility="collapsed")
    with sort_col:
        st.selectbox("정렬", ["최신순", "위험도 높은순", "위험도 낮은순"], key="history_sort", label_visibility="collapsed")
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
            st.caption(f"백엔드 `{BACKEND_BASE_URL}`의 진단 로그를 표시 중입니다.")
        else:
            st.warning(f"진단 기록 API 연결 실패: {st.session_state.history_api_error}", icon="⚠️")

    all_records = st.session_state.history_records
    summary_cols = st.columns(4)
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
        st.info("표시할 실제 진단 기록이 없습니다. 계약서를 먼저 업로드해 진단해 주세요.")
        return

    for row_start in range(0, len(records), 3):
        cols = st.columns(3)
        for col, rec in zip(cols, records[row_start : row_start + 3]):
            with col:
                _record_card(rec)
        st.markdown('<div style="height:26px"></div>', unsafe_allow_html=True)

    selected = [rec for rec in all_records if rec["id"] in st.session_state.compare_set]
    if selected:
        st.info(f"비교 선택: {len(selected)}건")
        _compare_panel(selected)
