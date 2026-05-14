"""Chat view wired to the FastAPI RAG/diagnosis backend."""

from __future__ import annotations

import html
import os
import uuid
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any

import requests
import streamlit as st

from utils.components import law_banner, render_status_pill, section_divider


API_TIMEOUT = int(os.getenv("FRONTEND_API_TIMEOUT", "45"))


def _api_base_urls() -> list[str]:
    configured = [
        os.getenv("BACKEND_API_URL"),
        os.getenv("API_BASE_URL"),
        os.getenv("RAG_SERVER_URL"),
    ]
    urls = ["http://localhost:8000"]
    for value in configured:
        if value:
            normalized = value.rstrip("/")
            if normalized and normalized not in urls:
                urls.append(normalized)
    # Fallback to 8001 if not already present
    if "http://localhost:8001" not in urls:
        urls.append("http://localhost:8001")
    return urls


def _session_id() -> str:
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = f"chat-{uuid.uuid4().hex[:10]}"
    return st.session_state.chat_session_id


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for base_url in _api_base_urls():
        try:
            response = requests.post(
                f"{base_url}{path}",
                json=payload,
                timeout=API_TIMEOUT,
            )
            if response.ok:
                return response.json()
            errors.append(f"{base_url}: HTTP {response.status_code}: {response.text[:300]}")
        except requests.RequestException as exc:
            errors.append(f"{base_url}: {exc}")
    raise RuntimeError("; ".join(errors) or "backend unavailable")


def _post_file(path: str, uploaded_file: Any) -> dict[str, Any]:
    errors: list[str] = []
    file_tuple = (
        uploaded_file.name,
        uploaded_file.getvalue(),
        uploaded_file.type or "application/octet-stream",
    )
    for base_url in _api_base_urls():
        try:
            response = requests.post(
                f"{base_url}{path}",
                files={"file": file_tuple},
                data={"session_id": _session_id()},
                timeout=API_TIMEOUT,
            )
            if response.ok:
                return response.json()
            errors.append(f"{base_url}: HTTP {response.status_code}: {response.text[:300]}")
        except requests.RequestException as exc:
            errors.append(f"{base_url}: {exc}")
    raise RuntimeError("; ".join(errors) or "backend unavailable")


def _strip_html(value: str) -> str:
    return value.replace("<br/>", "\n").replace("<br>", "\n")


def _history_for_api() -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in st.session_state.get("messages", [])[-8:]:
        history.append(
            {
                "role": str(message.get("role", "user")),
                "content": _strip_html(str(message.get("content", ""))),
            }
        )
    return history


def _extract_docx_text(data: bytes) -> str:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for para in root.findall(".//w:p", ns):
        texts = [node.text or "" for node in para.findall(".//w:t", ns)]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _file_to_text(uploaded_file: Any) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()
    if name.endswith(".docx"):
        return _extract_docx_text(data)
    if name.endswith(".txt"):
        for encoding in ("utf-8-sig", "utf-8", "cp949"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
    raise ValueError("지원하지 않는 파일 형식입니다. PDF, DOCX, TXT를 업로드해 주세요.")


def diagnose_contract(uploaded_file: Any) -> dict[str, Any]:
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        return _post_file("/api/v1/diagnosis/upload", uploaded_file)
    text = _file_to_text(uploaded_file)
    return _post_json(
        "/api/v1/diagnosis/text",
        {"session_id": _session_id(), "contract_text": text},
    )


def ask_backend(question: str) -> dict[str, Any]:
    context = st.session_state.get("diagnosis_context")
    message = question
    if context:
        message = (
            "아래 전세 계약서 진단 결과를 우선 참고해서 답변해 주세요.\n\n"
            f"{_format_diagnosis_for_prompt(context)}\n\n"
            f"사용자 질문: {question}"
        )
    return _post_json(
        "/api/v1/chat/query",
        {
            "session_id": _session_id(),
            "message": message,
            "history": _history_for_api(),
        },
    )


def _format_diagnosis_for_prompt(result: dict[str, Any]) -> str:
    risk_factors = result.get("risk_factors") or []
    factor_lines = []
    for item in risk_factors[:6]:
        factor_lines.append(
            "- "
            + str(item.get("category") or item.get("factor_id") or "위험요소")
            + ": "
            + str(item.get("description") or "")
            + " / 조치: "
            + str(item.get("advice") or "")
        )
    return "\n".join(
        [
            f"위험점수: {result.get('risk_score')}",
            f"위험등급: {result.get('risk_level')}",
            f"요약: {result.get('summary')}",
            "위험요소:",
            *factor_lines,
        ]
    )


def _references(result: dict[str, Any]) -> list[str]:
    refs = []
    for ref in result.get("references", [])[:6]:
        title = str(ref.get("title") or "RAG 근거")
        doc_type = str(ref.get("doc_type") or "문서")
        score = ref.get("relevance_score")
        suffix = f" · {score:.2f}" if isinstance(score, (int, float)) else ""
        refs.append(f"{title} ({doc_type}{suffix})")
    return refs


def _assistant_message(answer: str, sources: list[str] | None = None) -> dict[str, Any]:
    return {"role": "assistant", "content": answer, "sources": sources or []}


def _render_message(message: dict[str, Any]) -> None:
    content = str(message.get("content", ""))
    if message.get("role") == "user":
        st.markdown(f'<div class="chat-q">{html.escape(content)}</div>', unsafe_allow_html=True)
        return

    st.markdown(f'<div class="chat-a">{content}</div>', unsafe_allow_html=True)
    sources = message.get("sources") or []
    if sources:
        refs = "".join(f'<span class="ref">{html.escape(str(source))}</span>' for source in sources)
        st.markdown(f'<div class="rag-src"><b>근거 자료</b>{refs}</div>', unsafe_allow_html=True)


def _risk_level_key(level: str | None, score: float | int | None) -> str:
    text = str(level or "")
    numeric = float(score or 0)
    if "위험" in text or numeric >= 80:
        return "danger"
    if "주의" in text or numeric >= 60:
        return "caution"
    return "safe"


def _render_diagnosis_summary(result: dict[str, Any]) -> None:
    level = result.get("risk_level")
    score = result.get("risk_score", 0)
    factors = result.get("risk_factors") or []
    render_status_pill(_risk_level_key(level, score), int(float(score or 0)), "계약서 위험도")
    st.markdown(
        f"""
        <div style="background:var(--gray-50);border:1px solid var(--gray-200);border-radius:12px;
                    padding:14px 16px;margin:10px 0 14px;color:var(--gray-900)">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
            <b>계약서 진단 결과</b>
            <span style="font-weight:800">{html.escape(str(level))} · {score}점</span>
          </div>
          <div style="font-size:13px;color:var(--gray-700);line-height:1.55;margin-top:8px">
            {html.escape(str(result.get("summary") or ""))}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for item in factors[:4]:
        st.markdown(
            f"- **{item.get('category') or item.get('factor_id')}**: "
            f"{item.get('description', '')}"
        )


def render() -> None:
    law_banner(
        "<b>전세 계약 상담</b> · 업로드한 계약서 진단 결과와 RAG 근거를 함께 참고합니다.",
        pill="RAG 연결",
    )

    col_h1, col_h2 = st.columns([3, 1.2])
    with col_h1:
        st.markdown(
            '<div style="font-size:12px;font-weight:700;color:var(--gray-50);'
            'letter-spacing:.04em;margin-bottom:6px">AI 계약 상담</div>',
            unsafe_allow_html=True,
        )
        st.markdown("# 전세계약서와 법률 근거 기반 상담")
        st.markdown(
            '<p style="color:var(--gray-500);font-size:14px;margin-top:-8px">'
            "질문은 RAG 채팅으로, 계약서 파일은 진단 agent 경로로 보냅니다.</p>",
            unsafe_allow_html=True,
        )
    with col_h2:
        st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
        status = "safe" if st.session_state.get("backend_ready") else "caution"
        render_status_pill(status, 100 if status == "safe" else 60, "Backend")

    section_divider()

    with st.container(border=True):
        st.markdown("### 계약서 파일")
        uploaded = st.file_uploader(
            "계약서 업로드",
            type=["pdf", "docx", "txt"],
            label_visibility="collapsed",
        )
        diagnose_clicked = st.button(
            "계약서 진단",
            type="primary",
            use_container_width=True,
            disabled=uploaded is None,
        )
        if diagnose_clicked and uploaded is not None:
            with st.spinner("계약서를 읽고 RAG 기반 진단을 실행하는 중입니다..."):
                try:
                    result = diagnose_contract(uploaded)
                    st.session_state.diagnosis_context = result
                    st.session_state.backend_ready = True
                    st.session_state.messages = [
                        _assistant_message(
                            "계약서 진단이 완료되었습니다. 이제 이 계약서를 기준으로 질문해 주세요.",
                            _references(result),
                        )
                    ]
                    st.rerun()
                except Exception as exc:
                    st.session_state.backend_ready = False
                    st.error(f"계약서 진단 실패: {exc}")

    if st.session_state.get("diagnosis_context"):
        _render_diagnosis_summary(st.session_state.diagnosis_context)

    section_divider()
    st.markdown("### 상담")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            _assistant_message(
                "안녕하세요. 전세 계약 관련 질문을 입력하거나 계약서 파일을 먼저 업로드해 주세요.",
                [],
            )
        ]

    quick_questions = [
        "이 계약서에서 가장 위험한 조항은 뭐야?",
        "보증금을 지키려면 지금 뭘 확인해야 해?",
        "전입신고와 확정일자는 왜 중요해?",
        "HUG 보증보험 가입 가능성을 어떻게 봐야 해?",
    ]
    cols = st.columns(4)
    for index, question in enumerate(quick_questions):
        with cols[index]:
            if st.button(question, key=f"quick_chat_{index}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": question})
                with st.spinner("RAG 근거를 찾고 답변을 생성하는 중입니다..."):
                    try:
                        result = ask_backend(question)
                        st.session_state.backend_ready = True
                        st.session_state.messages.append(
                            _assistant_message(result.get("answer", ""), _references(result))
                        )
                    except Exception as exc:
                        st.session_state.backend_ready = False
                        st.session_state.messages.append(
                            _assistant_message(f"백엔드 연결 실패: {html.escape(str(exc))}", [])
                        )
                st.rerun()

    st.markdown('<div style="margin-top:16px"></div>', unsafe_allow_html=True)
    for message in st.session_state.messages:
        _render_message(message)

    if prompt := st.chat_input("전세 계약, 보증금, 특약, 등기부 관련 질문을 입력하세요."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.spinner("RAG 근거를 찾고 답변을 생성하는 중입니다..."):
            try:
                result = ask_backend(prompt)
                st.session_state.backend_ready = True
                st.session_state.messages.append(
                    _assistant_message(result.get("answer", ""), _references(result))
                )
            except Exception as exc:
                st.session_state.backend_ready = False
                st.session_state.messages.append(
                    _assistant_message(f"백엔드 연결 실패: {html.escape(str(exc))}", [])
                )
        st.rerun()
