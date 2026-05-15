"""진단 기록 — reports/ JSON 파일에서 실제 진단 결과를 불러와 표시."""

from __future__ import annotations

import json
import os
import glob
from pathlib import Path

import streamlit as st


REPORT_DIR = Path(__file__).resolve().parent.parent.parent / "reports"

LEVEL_KO = {"danger": "위험", "caution": "주의", "safe": "안전", "unknown": "미상"}
LEVEL_COLOR = {"danger": "var(--red)", "caution": "var(--amber)", "safe": "var(--green)", "unknown": "var(--gray-500)"}
LEVEL_BG = {"danger": "var(--red-soft)", "caution": "var(--amber-soft)", "safe": "var(--green-soft)", "unknown": "var(--gray-100)"}


def _risk_to_level(risk_level: str) -> str:
    m = {"위험": "danger", "주의": "caution", "안전": "safe"}
    return m.get(risk_level, "unknown")


def _deposit_display(deposit: int) -> str:
    if deposit >= 10000:
        eok = deposit / 10000
        if eok == int(eok):
            return f"₩{int(eok)}억"
        return f"₩{eok:.1f}억"
    return f"₩{deposit:,}만"


@st.cache_data(ttl=5)
def _load_reports() -> list[dict]:
    """reports/ 디렉토리에서 모든 진단 JSON 로드"""
    pattern = str(REPORT_DIR / "report_*.json")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    records = []
    for i, filepath in enumerate(files):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            continue

        ui = data.get("user_info", {})
        risk_level = ui.get("risk_level", "미상")
        level = _risk_to_level(risk_level)
        deposit = ui.get("deposit", 0)
        score = ui.get("risk_score", 0)
        area = ui.get("area_m2")
        created = data.get("created_at", "")
        date_short = created[:10] if created else ""

        # 태그 생성
        tags = []
        if ui.get("jeonse_ratio") and ui["jeonse_ratio"] >= 80:
            tags.append(f"전세가율{ui['jeonse_ratio']:.0f}%")
        terms = data.get("special_terms", [])
        danger_terms = [t for t in terms if t.get("risk_level") == "위험"]
        if danger_terms:
            tags.append(f"특약위험{len(danger_terms)}건")
        if not tags:
            tags.append(risk_level)

        records.append({
            "id": i + 1,
            "session_id": data.get("session_id", ""),
            "addr": ui.get("address", "주소 미상"),
            "deposit": _deposit_display(deposit),
            "deposit_raw": deposit,
            "area": f"{area}㎡" if area else "",
            "score": score,
            "level": level,
            "date": date_short,
            "tags": tags,
            "ratio": f"{ui.get('jeonse_ratio', 0):.0f}%" if ui.get("jeonse_ratio") else "미상",
            "hug": (
                "데이터 없음" if ui.get("jeonse_ratio") is None
                else "가입 어려움" if ui["jeonse_ratio"] >= 90
                else "확인 필요" if ui["jeonse_ratio"] >= 80
                else "가능성 있음"
            ),
            "filepath": filepath,
            "report_data": data,
        })

    return records


def _history_css() -> str:
    return """
    <style>
      .history-page-title {
        margin: 0; color: var(--gray-900); font-size: 32px;
        line-height: 1.22; font-weight: 900;
      }
      .history-page-copy {
        margin: 10px 0 20px; color: var(--gray-500);
        font-size: 14px; font-weight: 600;
      }
      .history-stat {
        min-height: 120px; padding: 24px;
        border: 1px solid var(--gray-200); border-radius: 16px;
        background: #fff; text-align: center;
      }
      .history-stat .label { font-size: 12px; font-weight: 900; }
      .history-stat .value {
        margin-top: 10px; font-size: 34px;
        line-height: 1; font-weight: 900;
      }
      .history-card {
        min-height: 200px; padding: 18px;
        border: 1px solid var(--gray-200);
        border-radius: 14px; background: #fff;
      }
      .history-card-top {
        display: flex; align-items: center; gap: 10px;
        margin-bottom: 12px;
      }
      .history-dot {
        width: 14px; height: 14px; border-radius: 50%;
        display: inline-block; flex: 0 0 auto;
      }
      .history-date {
        color: var(--gray-500); font-size: 12px; font-weight: 900;
      }
      .history-addr {
        color: var(--gray-900); font-size: 15px;
        line-height: 1.4; font-weight: 900;
      }
      .history-meta {
        margin-top: 7px; color: var(--gray-500);
        font-size: 12px; font-weight: 700;
      }
      .history-score {
        margin-top: 20px; display: flex;
        align-items: baseline; gap: 4px;
      }
      .history-score b {
        font-size: 32px; line-height: 1; font-weight: 900;
      }
      .history-score span {
        color: var(--gray-500); font-size: 13px; font-weight: 900;
      }
      .history-tags {
        margin-top: 22px; display: flex;
        flex-wrap: wrap; gap: 6px;
      }
      .history-tag {
        padding: 4px 8px; border-radius: 999px;
        background: var(--gray-100); color: var(--gray-700);
        font-size: 11px; font-weight: 800;
      }
      .history-actions { margin-top: -1px; }
    </style>
    """


def _init_state():
    if "compare_set" not in st.session_state:
        st.session_state.compare_set = set()


def _summary_card(label: str, value: str, tone: str):
    color = "var(--gray-900)" if tone == "gray" else LEVEL_COLOR.get(tone, "var(--gray-900)")
    bg = "#fff" if tone == "gray" else LEVEL_BG.get(tone, "#fff")
    st.markdown(
        f'<div class="history-stat" style="background:{bg}">'
        f'<div class="label" style="color:{color}">{label}</div>'
        f'<div class="value" style="color:{color}">{value}</div></div>',
        unsafe_allow_html=True,
    )


def _record_card(rec):
    color = LEVEL_COLOR.get(rec["level"], "var(--gray-500)")
    bg = LEVEL_BG.get(rec["level"], "var(--gray-100)")
    tags_html = "".join(f'<span class="history-tag">#{tag}</span>' for tag in rec["tags"])

    st.markdown(
        f"""
        <div class="history-card">
          <div class="history-card-top">
            <span class="history-dot" style="background:{color};box-shadow:0 0 0 5px {bg}"></span>
            <span class="history-date">{rec['date']} 진단</span>
          </div>
          <div class="history-addr">{rec['addr']}</div>
          <div class="history-meta">{rec['deposit']}{' · ' + rec['area'] if rec['area'] else ''}</div>
          <div class="history-score">
            <b style="color:{color}">{rec['score']}</b>
            <span>/ 100 · {LEVEL_KO.get(rec['level'], '미상')}</span>
          </div>
          <div class="history-tags">{tags_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    detail_col, chat_col = st.columns(2)
    with detail_col:
        if st.button("자세히", key=f"open_{rec['id']}", use_container_width=True):
            st.session_state.selected_record_id = rec["id"]
            st.session_state.current_view = "property"
            st.rerun()
    with chat_col:
        if st.button("💬 상담", key=f"chat_{rec['id']}", use_container_width=True, type="primary"):
            st.session_state.session_id = rec["session_id"]
            if "chat_session" in st.session_state:
                del st.session_state.chat_session
            st.session_state.current_view = "chat"
            st.session_state.diagnosis_done = True
            st.session_state.report = rec["report_data"]
            st.rerun()


def _filtered_records(records):
    query = st.session_state.get("history_query", "").strip()
    level_filter = st.session_state.get("history_level", "전체")
    sort_key = st.session_state.get("history_sort", "최신순")

    filtered = records
    if query:
        filtered = [r for r in filtered if query in r["addr"]]
    if level_filter != "전체":
        level_map = {"위험만": "danger", "주의만": "caution", "안전만": "safe"}
        if level_filter in level_map:
            filtered = [r for r in filtered if r["level"] == level_map[level_filter]]

    if sort_key == "위험도 높은순":
        filtered = sorted(filtered, key=lambda r: r["score"], reverse=True)
    elif sort_key == "위험도 낮은순":
        filtered = sorted(filtered, key=lambda r: r["score"])
    elif sort_key == "보증금 높은순":
        filtered = sorted(filtered, key=lambda r: r["deposit_raw"], reverse=True)

    return filtered


def render():
    _init_state()
    st.markdown(_history_css(), unsafe_allow_html=True)

    records = _load_reports()

    st.markdown('<div class="history-page-title">진단 기록</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="history-page-copy">진단한 매물을 확인하고, 챗봇 상담으로 이어갈 수 있어요.</div>',
        unsafe_allow_html=True,
    )

    # 필터 바
    q_col, level_col, sort_col, add_col = st.columns([1.55, 1.15, 1.15, 0.75])
    with q_col:
        st.text_input("주소 검색", placeholder="동 이름 또는 주소", key="history_query", label_visibility="collapsed")
    with level_col:
        st.selectbox("위험도", ["전체", "위험만", "주의만", "안전만"], key="history_level", label_visibility="collapsed")
    with sort_col:
        st.selectbox("정렬", ["최신순", "위험도 높은순", "위험도 낮은순", "보증금 높은순"], key="history_sort", label_visibility="collapsed")
    with add_col:
        if st.button("+ 새 진단", type="primary", use_container_width=True):
            st.session_state.current_view = "chat"
            st.rerun()

    st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)

    # 통계 카드
    if records:
        scols = st.columns(4)
        summary = [
            ("총 진단", f"{len(records)}건", "gray"),
            ("위험", f"{sum(1 for r in records if r['level'] == 'danger')}건", "danger"),
            ("주의", f"{sum(1 for r in records if r['level'] == 'caution')}건", "caution"),
            ("안전", f"{sum(1 for r in records if r['level'] == 'safe')}건", "safe"),
        ]
        for col, (label, value, tone) in zip(scols, summary):
            with col:
                _summary_card(label, value, tone)

        st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)

    # 기록 카드
    filtered = _filtered_records(records)

    if not records:
        st.markdown(
            '<div style="background:#fff;border:1px solid var(--gray-200);border-radius:16px;'
            'padding:48px;text-align:center">'
            '<p style="font-size:18px;font-weight:900;color:var(--gray-900);margin-bottom:8px">'
            '아직 진단 기록이 없습니다</p>'
            '<p style="color:var(--gray-500);font-size:14px">'
            '계약서를 업로드하거나 주소를 입력해서 첫 진단을 시작해 보세요.</p></div>',
            unsafe_allow_html=True,
        )
        if st.button("🔍 진단 시작하기", type="primary"):
            st.session_state.current_view = "chat"
            st.rerun()
        return

    if not filtered:
        st.info("조건에 맞는 진단 기록이 없습니다.")
        return

    for row_start in range(0, len(filtered), 3):
        cols = st.columns(3)
        for col, rec in zip(cols, filtered[row_start:row_start + 3]):
            with col:
                _record_card(rec)
        st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
