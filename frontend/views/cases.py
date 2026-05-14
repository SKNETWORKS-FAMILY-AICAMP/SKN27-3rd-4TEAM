"""나와 비슷한 사례 — 키워드 기반 관련 사례·판례 문서 검색."""

from pathlib import Path

import streamlit as st


BASE_DOCUMENTS = [
    {"kind": "피해 사례", "title": "전세사기 피해예방 종합안내서", "summary": "계약 전 등기부, 보증보험, 임대인 세금 체납 확인 절차를 정리한 안내 문서입니다.", "keywords": ["전세사기", "예방", "체크리스트", "보증보험", "등기부"]},
    {"kind": "피해 사례", "title": "경기도 전세피해 사례집", "summary": "보증금 미반환, 깡통전세, 다가구 선순위 권리 문제를 실제 사례 중심으로 정리했습니다.", "keywords": ["보증금", "미반환", "깡통전세", "다가구", "선순위"]},
    {"kind": "판례", "title": "대법원 2022다48327", "summary": "임차권등기명령과 우선변제권 유지 시점을 다룬 판례입니다.", "keywords": ["임차권등기", "우선변제", "보증금", "대항력"]},
    {"kind": "판례", "title": "신탁등기 임대차 분쟁 사례", "summary": "수탁자 동의 없는 임대차계약의 위험과 신탁원부 확인 필요성을 다룹니다.", "keywords": ["신탁", "수탁자", "동의서", "계약무효"]},
    {"kind": "특약", "title": "근저당 말소 조건부 특약 예시", "summary": "잔금일까지 선순위 근저당을 말소하지 않을 경우 계약 해제와 보증금 반환을 명확히 하는 문구입니다.", "keywords": ["근저당", "특약", "말소", "선순위"]},
]


def _load_pdf_documents():
    root = Path(r"E:\dev\SKN27-3rd-4TEAM\docs\pdf")
    if not root.exists():
        return []
    docs = []
    for path in sorted(root.rglob("*.pdf")):
        name = path.stem
        lower = name.lower()
        kind = "판례" if any(x in name for x in ["대법원", "지방법", "심판", "판결"]) else "피해 사례"
        keywords = [part for part in name.replace("_", " ").replace("-", " ").split() if part]
        if "전세" in name:
            keywords.append("전세")
        if "사기" in name or "피해" in name:
            keywords.append("피해")
        if "신탁" in name:
            keywords.append("신탁")
        docs.append({
            "kind": kind,
            "title": name,
            "summary": "docs 폴더에 있는 PDF 문서입니다. 파일명 기준으로 검색되며, 챗봇 답변 근거 자료로 활용할 수 있습니다.",
            "keywords": keywords,
            "path": str(path),
        })
    return docs


def _score(doc, query):
    if not query:
        return 1
    terms = [t.strip().lower() for t in query.split() if t.strip()]
    haystack = " ".join([doc["title"], doc["summary"], " ".join(doc.get("keywords", []))]).lower()
    return sum(1 for term in terms if term in haystack)


def render():
    st.markdown(
        '<div style="font-size:12px;font-weight:700;color:var(--gray-500);letter-spacing:.04em;margin-bottom:6px">사례 검색 · RAG 문서 기반</div>',
        unsafe_allow_html=True,
    )
    st.markdown("# 나와 비슷한 사례")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:14px;margin-top:-8px">키워드를 입력하면 피해 사례, 판례, 특약 문서 중 관련 자료를 찾아볼 수 있습니다.</p>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([2.2, 1])
    with c1:
        query = st.text_input("키워드 검색", placeholder="예: 근저당 신탁 보증금 미반환 임차권등기", label_visibility="collapsed")
    with c2:
        kind_filter = st.selectbox("문서 유형", ["전체", "피해 사례", "판례", "특약"], label_visibility="collapsed")

    documents = BASE_DOCUMENTS + _load_pdf_documents()
    results = []
    for doc in documents:
        if kind_filter != "전체" and doc["kind"] != kind_filter:
            continue
        score = _score(doc, query)
        if score > 0:
            results.append((score, doc))
    results.sort(key=lambda item: item[0], reverse=True)

    st.markdown(
        f'<div style="margin:12px 0 18px;color:var(--gray-500);font-size:13px;font-weight:700">검색 결과 {len(results)}건</div>',
        unsafe_allow_html=True,
    )

    if not results:
        st.info("검색 결과가 없습니다. '보증금', '근저당', '신탁', '임차권등기'처럼 핵심 단어로 다시 검색해보세요.")
        return

    for score, doc in results[:24]:
        keywords = "".join(
            f'<span style="background:var(--gray-100);padding:4px 9px;border-radius:999px;font-size:11px;color:var(--gray-700);margin-right:5px">#{kw}</span>'
            for kw in doc.get("keywords", [])[:6]
        )
        path_html = f'<div class="case-path">{doc["path"]}</div>' if doc.get("path") else ""
        st.markdown(
            f"""
            <div class="case-doc-card">
              <div class="case-kind">{doc['kind']}</div>
              <h3>{doc['title']}</h3>
              <p>{doc['summary']}</p>
              <div>{keywords}</div>
              {path_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
