"""사례·판례 플레이북 — 상황별 대응 가이드 + 변호사 상담 키트."""

import streamlit as st


PLAYBOOKS = [
    {
        "id": "ghost",
        "urg": "now",
        "urg_label": "긴급 · 지금 당장",
        "title": "임대인이 연락 두절됐어요",
        "desc": "잠수 · 문자 응답 없음 · 보증금 반환일이 지났을 때",
        "tl": [
            ("24시간 내", "내용증명 발송 준비"),
            ("1주 내", "임차권등기명령 신청"),
            ("1개월 내", "보증금 반환 소송"),
        ],
        "stats": "관련 판례 12건 · 사례 38건",
    },
    {
        "id": "auction",
        "urg": "now",
        "urg_label": "긴급 · 지금 당장",
        "title": "경매 통지서를 받았어요",
        "desc": "법원에서 경매개시결정 송달 · 매각기일 통지",
        "tl": [
            ("즉시", "배당요구 신청 (필수)"),
            ("2주 내", "임차권등기명령 · 우선변제권 확보"),
            ("매각기일 전", "HUG 사고접수"),
        ],
        "stats": "관련 판례 8건 · 사례 23건",
    },
    {
        "id": "change",
        "urg": "soon",
        "urg_label": "중요 · 1주 내",
        "title": "임대인이 갑자기 바뀌었어요",
        "desc": "매매·증여로 소유자 변경 통지를 받았을 때",
        "tl": [
            ("3일 내", "새 임대인 등기부 확인"),
            ("1주 내", "계약 승계 의사 확인"),
            ("2주 내", "필요 시 계약 해지권 행사"),
        ],
        "stats": "관련 판례 5건 · 사례 14건",
    },
    {
        "id": "newlien",
        "urg": "soon",
        "urg_label": "중요 · 1주 내",
        "title": "근저당이 새로 잡혔어요",
        "desc": "계약 후 임대인이 추가 대출로 근저당 설정",
        "tl": [
            ("즉시", "등기부 변동 캡처·증거 보존"),
            ("3일 내", "임차권등기명령 신청"),
            ("1주 내", "계약 위반 통지·해지 검토"),
        ],
        "stats": "관련 판례 9건 · 사례 17건",
    },
    {
        "id": "agent",
        "urg": "plan",
        "urg_label": "예방 · 계약 전",
        "title": "대리인이 계약하자고 해요",
        "desc": "임대인이 직접 안 오고 위임장으로 처리",
        "tl": [
            ("필수", "위임장·인감증명서 원본 확인"),
            ("필수", "임대인 본인과 영상 통화 녹화"),
            ("필수", "대리권 범위 명시 확인"),
        ],
        "stats": "관련 판례 4건 · 사례 11건",
    },
    {
        "id": "trust",
        "urg": "plan",
        "urg_label": "예방 · 계약 전",
        "title": "신탁등기 매물을 만났어요",
        "desc": "임대인이 실소유자가 아닌 경우",
        "tl": [
            ("필수", "신탁원부 발급 · 수탁자 확인"),
            ("필수", "수탁자(신탁회사) 동의서 필수"),
            ("필수", "수탁자 명의로 보증금 지급"),
        ],
        "stats": "관련 판례 6건 · 사례 9건",
    },
]


GHOST_DETAIL = [
    {
        "n": 1, "when": "24시간 내",
        "title": "증거 확보 · 통화 녹음 · 문자 캡처",
        "body": "임대인에게 연락한 모든 시도를 시간순으로 정리하세요. 통화는 녹음, 문자/카톡은 캡처. "
                "추후 소송에서 임대인의 고의 입증 핵심 자료가 됩니다.",
        "laws": ["민법 제387조 · 이행지체", "대법원 2019다204538 · 통지 의무"],
    },
    {
        "n": 2, "when": "3일 내",
        "title": "내용증명 발송",
        "body": "임대인 주소·등기상 주소로 동시 발송. \"보증금 반환 청구 · OO일까지 미반환 시 법적 조치\"를 명시. "
                "우체국에서 7,500원에 가능. 이게 곧 소송에서 \"독촉했다\"는 증거입니다.",
        "laws": ["민법 제388조 · 최고"],
    },
    {
        "n": 3, "when": "1주 내 · 가장 중요",
        "title": "임차권등기명령 신청 (서울중앙지법)",
        "body": "이사를 가야 해도 대항력·우선변제권이 살아 있게 합니다. 명령이 등기에 기재된 후엔 "
                "임대인이 집을 팔거나 추가 담보를 잡아도 당신의 권리가 우선합니다. 신청비 약 3만원. "
                "종로구 사례에선 신청 시 회수율이 43% → 81%로 상승했습니다.",
        "laws": ["주택임대차보호법 제3조의3", "대법원 2022다48327 · 효력 발생 시점"],
    },
    {
        "n": 4, "when": "2주 내",
        "title": "HUG 사고접수 (가입자만)",
        "body": "전세보증금반환보증에 가입했다면, 임차권등기명령 등기 후 HUG에 사고접수. "
                "평균 4.2개월 내 전액 대위변제. 가입하지 않았다면 다음 단계로.",
        "laws": [],
    },
    {
        "n": 5, "when": "1개월 내",
        "title": "보증금 반환청구 소송 제기",
        "body": "소액(5,000만원 이하)은 소액사건, 그 이상은 단독판사 사건. 종로구 사례 평균 1심 기간 6.8개월. "
                "승소 후 강제경매 신청 가능.",
        "laws": ["민사소송법 제248조"],
    },
    {
        "n": 6, "when": "3개월 내",
        "title": "강제경매 신청 · 배당요구",
        "body": "판결문 받은 후 부동산 강제경매 신청. 임차권등기를 미리 해뒀다면 이 시점에 권리가 보호됩니다. "
                "경매 매각가는 시세의 70~80%, 선순위 채권 변제 후 잔여분에서 회수.",
        "laws": ["민사집행법 제264조"],
    },
]


LAWYER_KIT = [
    ("임대차계약서 원본", "특약 포함 전 페이지", True),
    ("등기부등본 (최근 발급)", "발급일 1주 이내", True),
    ("전입신고·확정일자 증빙", "주민등록등본 · 확정일자 받은 계약서", True),
    ("보증금 지급 증빙", "계좌이체 내역 · 영수증", False),
    ("내용증명 사본", "발송·반송 증명서 포함", False),
    ("임대인과의 연락 기록", "통화 녹음 · 문자 캡처", False),
    ("HUG 가입 증서", "(가입한 경우만)", False),
    ("임대인 보유 부동산 조회", "인터넷등기소 동일 명의 검색", False),
]


def render():
    st.markdown(
        '<div style="font-size:12px;font-weight:700;color:var(--gray-500);'
        'letter-spacing:.04em;margin-bottom:6px">사례·판례 플레이북 · 상황별 대응 가이드</div>',
        unsafe_allow_html=True,
    )
    st.markdown("# 이미 일이 터졌다면, 단계별로 안내해 드려요")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:14px">'
        "상황 카드를 선택하면 시간 순서대로 무엇을 해야 하는지, 어떤 법령·판례가 근거인지 보여드립니다.</p>",
        unsafe_allow_html=True,
    )

    # 카드 그리드 (3열)
    if "selected_pb" not in st.session_state:
        st.session_state.selected_pb = "ghost"

    for row_start in range(0, len(PLAYBOOKS), 3):
        cols = st.columns(3)
        for i, pb in enumerate(PLAYBOOKS[row_start:row_start + 3]):
            with cols[i]:
                tl_html = "".join(
                    f'<div class="t"><span class="dot"></span><span><b>{when}</b> {what}</span></div>'
                    for when, what in pb["tl"]
                )
                st.markdown(
                    f"""
                    <div class="pb-card">
                      <span class="urg {pb['urg']}">{pb['urg_label']}</span>
                      <h4>{pb['title']}</h4>
                      <p>{pb['desc']}</p>
                      <div class="tl">{tl_html}</div>
                      <div class="footer">{pb['stats']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"자세히 보기 →", key=f"pb_{pb['id']}", use_container_width=True):
                    st.session_state.selected_pb = pb["id"]
                    st.rerun()

        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)

    # ───── 상세 (현재는 ghost만) ─────
    if st.session_state.selected_pb == "ghost":
        st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)
        st.markdown(
            '<span class="pb-card" style="display:inline-block;padding:4px 12px"><span class="urg now">긴급 · 지금 당장</span></span>',
            unsafe_allow_html=True,
        )
        st.markdown("## 임대인이 연락 두절됐어요")
        st.markdown(
            '<p style="color:var(--gray-700);font-size:14px;line-height:1.7">'
            "보증금 반환일이 지났는데도 임대인이 연락을 받지 않을 때, 시간이 곧 돈입니다. "
            "아래 단계를 시간 순서대로 따라가세요. 종로구 명륜2가 사례 38건의 평균 회수 기간은 "
            "<b>14개월</b>이지만, 1주 내 임차권등기명령을 신청한 경우 <b>9개월</b>로 줄어들었습니다.</p>",
            unsafe_allow_html=True,
        )

        for step in GHOST_DETAIL:
            highlight = "background:var(--blue-soft);border-color:#cfe1ff" if step["n"] == 3 else ""
            laws_html = "".join(
                f'<span class="law-chip"><span class="lico">법</span>{l}</span>' for l in step["laws"]
            )
            st.markdown(
                f"""
                <div style="display:flex;gap:18px;padding:18px;border-radius:14px;
                            background:var(--gray-100);margin-bottom:10px;{highlight}">
                  <div style="width:36px;height:36px;border-radius:50%;background:var(--blue);color:#fff;
                              display:grid;place-items:center;font-weight:800;flex-shrink:0">{step['n']}</div>
                  <div>
                    <div style="font-size:11px;font-weight:800;color:var(--blue);letter-spacing:.06em">
                      {step['when']}
                    </div>
                    <h5 style="margin:4px 0 8px;font-size:16px;font-weight:800;color:var(--gray-900)">{step['title']}</h5>
                    <p style="color:var(--gray-700);font-size:13px;line-height:1.7;margin:0 0 8px">{step['body']}</p>
                    <div>{laws_html}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ───── 변호사 상담 키트 ─────
    st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)
    st.markdown("### 📋 변호사 상담 준비 키트")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
        "위 단계 중 3번 이상이면 변호사 상담을 권장합니다. 아래 자료를 미리 챙겨가면 "
        "상담료(통상 1시간 ₩100,000~)를 아낄 수 있어요.</p>",
        unsafe_allow_html=True,
    )

    cols = st.columns(2)
    for i, (title, desc, done) in enumerate(LAWYER_KIT):
        with cols[i % 2]:
            done_cls = "done" if done else ""
            check = "✓" if done else ""
            st.markdown(
                f"""
                <div class="chk-item {done_cls}">
                  <div class="chk-icon">{check}</div>
                  <div>
                    <div class="title">{title}</div>
                    <div class="desc">{desc}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)
    c1, c2, _ = st.columns([1.4, 1.4, 3])
    with c1:
        st.button("대한법률구조공단 무료 상담 (132)", type="primary", use_container_width=True)
    with c2:
        st.button("자료 자동 정리 PDF", use_container_width=True)


# ---- 나와 비슷한 사례 검색 페이지 ----
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
    root = Path(__file__).resolve().parent.parent.parent / "docs" / "pdf"
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


def render_cases():
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

