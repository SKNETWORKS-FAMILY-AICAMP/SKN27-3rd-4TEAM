"""최근 진단한 계약서 상세 화면."""

from __future__ import annotations

import html
import os
from typing import Any

import requests
import streamlit as st

from utils.components import render_status_pill, risk_row, section_divider


LEVEL_KO = {"danger": "위험", "caution": "주의", "safe": "안전"}
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")


def _level_key(level: Any, score: int | float | None = None) -> str:
    text = str(level or "").upper()
    numeric = float(score or 0)
    if text in {"위험", "DANGER", "HIGH", "CRITICAL"} or numeric >= 70:
        return "danger"
    if text in {"주의", "CAUTION", "MEDIUM"} or numeric >= 40:
        return "caution"
    return "safe"


def _record_from_latest(result: dict[str, Any]) -> dict[str, Any]:
    info = result.get("contract_info") or {}
    summary = str(result.get("summary") or "").strip()
    score = int(float(result.get("risk_score") or 0))
    level = _level_key(result.get("risk_level"), score)
    address = str(info.get("address") or "").strip()
    raw_text = str(info.get("raw_text") or result.get("input_text") or "")
    title = address or _first_meaningful_line(raw_text) or _summary_title(summary)
    return {
        "id": result.get("id") or result.get("session_id") or "latest",
        "addr": title,
        "deposit": _money_text(info.get("deposit_amount")),
        "area": _area_text(info.get("area_m2")),
        "year": "-",
        "lessor": info.get("lessor_name") or "-",
        "lessee": info.get("lessee_name") or "-",
        "sale": _money_text(info.get("estimated_sale_price")),
        "ratio": _ratio_text(info.get("jeonse_ratio")),
        "score": score,
        "level": level,
        "date": "최근",
        "tags": _tags_from_factors(result.get("risk_factors") or [], level),
        "senior": "-",
        "hug": "-",
        "summary": summary,
        "input_text": raw_text,
        "risk_factors": result.get("risk_factors") or [],
        "rag_references": result.get("references") or result.get("rag_references") or [],
        "contract_info": info,
    }


def _selected_record() -> dict[str, Any] | None:
    latest = st.session_state.get("latest_diagnosis") or st.session_state.get("diagnosis_context")
    if latest:
        return _record_from_latest(latest)

    records = st.session_state.get("history_records") or []
    if not records:
        return _fetch_latest_record()
    rec_id = st.session_state.get("selected_record_id")
    if rec_id is not None:
        for record in records:
            if str(record.get("id")) == str(rec_id):
                return record
    return records[0]


def _fetch_latest_record() -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{BACKEND_BASE_URL}/api/v1/diagnosis/logs",
            params={"limit": 1},
            timeout=5,
        )
        response.raise_for_status()
        logs = response.json().get("logs") or []
    except requests.RequestException:
        return None
    if not logs:
        return None
    row = logs[0]
    info = row.get("contract_info") or {}
    score = int(float(row.get("risk_score") or 0))
    level = _level_key(row.get("risk_level"), score)
    summary = str(row.get("result_summary") or "").strip()
    input_text = str(row.get("input_text") or "")
    return {
        "id": row.get("id") or row.get("session_id") or "latest-log",
        "addr": info.get("address") or _first_meaningful_line(input_text) or _summary_title(summary),
        "deposit": _money_text(info.get("deposit_amount")),
        "area": _area_text(info.get("area_m2")),
        "year": "-",
        "lessor": info.get("lessor_name") or "-",
        "lessee": info.get("lessee_name") or "-",
        "sale": _money_text(info.get("estimated_sale_price")),
        "ratio": _ratio_text(info.get("jeonse_ratio")),
        "score": score,
        "level": level,
        "date": str(row.get("created_at") or "최근")[:10],
        "tags": _tags_from_factors(row.get("risk_factors") or [], level),
        "senior": "-",
        "hug": "-",
        "summary": summary,
        "input_text": input_text,
        "risk_factors": row.get("risk_factors") or [],
        "rag_references": row.get("rag_references") or [],
        "contract_info": info,
    }


def _detail_for_record(rec: dict[str, Any]) -> dict[str, Any]:
    info = rec.get("contract_info") or {}
    risks = []
    for factor in rec.get("risk_factors", []) or []:
        severity = str(factor.get("severity", "")).upper()
        tone = "danger" if severity in {"HIGH", "CRITICAL"} else "caution" if severity == "MEDIUM" else "safe"
        meta = "치명" if tone == "danger" else "주의" if tone == "caution" else "안전"
        risks.append(
            (
                factor.get("description") or factor.get("factor_id") or "문서 기반 확인 항목",
                meta,
                tone,
                factor.get("legal_basis") or factor.get("advice") or "업로드한 계약서와 RAG 근거를 기준으로 확인하세요.",
            )
        )

    if not risks:
        risks.append(
            (
                rec.get("summary") or "저장된 진단 요약을 확인하세요.",
                LEVEL_KO.get(rec.get("level"), "진단"),
                rec.get("level", "caution"),
                "백엔드 진단 기록에 저장된 요약 정보입니다.",
            )
        )
    period = ""
    if info.get("contract_start") or info.get("contract_end"):
        period = f"{info.get('contract_start') or '-'} ~ {info.get('contract_end') or '-'}"
    return {
        "building": info.get("housing_type") or "업로드 계약서",
        "sale": rec.get("sale") or _money_text(info.get("estimated_sale_price")),
        "period": period or "-",
        "risks": risks,
    }


def _money_text(value: Any) -> str:
    if value in (None, "", "-"):
        return "-"
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return str(value)
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


def _first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 5:
            return line[:42] + ("..." if len(line) > 42 else "")
    return ""


def _summary_title(summary: str) -> str:
    if not summary:
        return "최근 계약서 진단"
    first = summary.splitlines()[0].strip()
    return first[:42] + ("..." if len(first) > 42 else "")


def _tags_from_factors(factors: list[dict[str, Any]], level: str) -> list[str]:
    tags = [LEVEL_KO.get(level, "진단")]
    for factor in factors[:3]:
        category = str(factor.get("category") or factor.get("factor_id") or "").strip()
        if category and category not in tags:
            tags.append(category[:12])
    return tags[:4]


def _render_uploaded_document(rec: dict[str, Any]) -> None:
    summary = rec.get("summary")
    input_text = rec.get("input_text")
    if not summary and not input_text:
        return

    st.markdown("### 업로드 문서 내용")
    body = html.escape(str(summary or input_text or ""))
    st.markdown(
        f"""
        <div class="tw-card">
          <b>진단 요약</b>
          <div style="margin-top:8px;color:var(--gray-700);line-height:1.6">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_empty_state() -> None:
    st.markdown("# 최근 확인 매물")
    st.info("아직 진단한 계약서가 없습니다. AI 안심 상담에서 계약서 파일을 업로드하고 진단을 실행해 주세요.")
    if st.button("AI 안심 상담으로 이동", type="primary"):
        st.session_state.current_view = "chat"
        st.rerun()


def render() -> None:
    rec = _selected_record()
    if not rec:
        _render_empty_state()
        return

    detail = _detail_for_record(rec)
    status_type = _level_key(rec.get("level"), rec.get("score"))

    st.markdown(
        f'<div style="font-size:12px;font-weight:700;color:var(--gray-500);letter-spacing:.04em;margin-bottom:6px">최근 확인 매물 · 진단 #{rec["id"]}</div>',
        unsafe_allow_html=True,
    )

    title_col, status_col = st.columns([3, 1.2])
    with title_col:
        st.markdown(f"# {html.escape(str(rec['addr']))}")
        st.markdown(
            '<p style="color:var(--gray-500);font-size:14px;margin-top:-8px">업로드한 계약서 진단 결과를 기준으로 표시합니다.</p>',
            unsafe_allow_html=True,
        )
    with status_col:
        st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
        render_status_pill(status_type, int(float(rec.get("score") or 0)), f"{LEVEL_KO[status_type]} 계약서")

    section_divider()

    st.markdown(
        f"""
        <div style="background:var(--green-soft);border:1px solid #b8ead9;border-radius:12px;
                    padding:12px 14px;margin-top:4px;font-size:13px;color:#005a3f">
          분석 완료 · <b>{len(detail['risks'])}건 위험 신호</b>를 업로드한 파일 기준으로 표시합니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    section_divider()
    _render_uploaded_document(rec)
    if rec.get("summary") or rec.get("input_text"):
        section_divider()

    info_col, risk_col = st.columns([1, 1.15])

    with info_col:
        st.markdown("### 매물 정보")
        st.markdown(
            f"""
            <div class="tw-card">
              <div class="prop-detail-grid">
                <span>표시명</span><b>{html.escape(str(rec['addr']))}</b>
                <span>문서</span><b>{detail['building']}</b>
                <span>임대사업자(임대인)</span><b>{html.escape(str(rec.get('lessor', '-')))}</b>
                <span>임차인</span><b>{html.escape(str(rec.get('lessee', '-')))}</b>
                <span>보증금</span><b>{rec.get('deposit', '-')}</b>
                <span>면적</span><b>{rec.get('area', '-')}</b>
                <span>계약기간</span><b>{detail.get('period', '-')}</b>
                <span>예상 매매가</span><b>{detail['sale']}</b>
                <span>전세가율</span><b>{rec.get('ratio', '-')}</b>
                <span>보증보험</span><b>{rec.get('hug', '-')}</b>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
        st.markdown("### 계약 진행 상태")
        st.markdown(
            """
            <div class="tw-card">
              <div class="timeline-row done"><span></span><div><b>자료 분석 완료</b><small>업로드한 계약서 파일 기준</small></div></div>
              <div class="timeline-row now"><span></span><div><b>위험 검토 필요</b><small>아래 위험 항목을 확인하세요.</small></div></div>
              <div class="timeline-row"><span></span><div><b>체크리스트 확인</b><small>계약 전 필수 항목을 완료하세요.</small></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with risk_col:
        st.markdown("### 핵심 위험 신호")
        for title, meta, tone, law in detail["risks"]:
            risk_row(str(title), str(meta), str(tone), law=str(law))

        st.markdown(
            """
            <div class="tw-card" style="margin-top:12px">
              <div style="font-size:11px;font-weight:800;color:var(--gray-500);letter-spacing:.06em;margin-bottom:10px">권장 조치</div>
              <div class="action-row"><b>1</b><span>등기부등본을 계약 직전 다시 발급해 권리 변동을 확인</span></div>
              <div class="action-row"><b>2</b><span>보증보험 가입 가능 여부를 먼저 조회</span></div>
              <div class="action-row"><b>3</b><span>위험 권리는 말소 조건 특약으로 계약서에 명시</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    section_divider()

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("진단 기록", use_container_width=True):
            st.session_state.current_view = "history"
            st.rerun()
    with c2:
        if st.button("채팅에서 질문", use_container_width=True, type="primary"):
            st.session_state.diagnosis_context = st.session_state.get("latest_diagnosis") or st.session_state.get("diagnosis_context")
            st.session_state.current_view = "chat"
            st.rerun()
    with c3:
        if st.button("체크리스트", use_container_width=True):
            st.session_state.current_view = "checklist"
            st.rerun()
