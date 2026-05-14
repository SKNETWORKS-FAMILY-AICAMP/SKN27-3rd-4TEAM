"""상담 챗 (메인) — 진단 결과 + RAG 스타일 챗봇."""

import os

import requests
import streamlit as st
from utils.components import (
    render_status_pill,
    law_banner,
    section_divider,
)


# ─── 데모 RAG 응답 ──────────────────────────────────────
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")


def register_documents_to_history(registry_file, contract_file, address: str, deposit_amount: int) -> dict:
    """등기부등본과 임대차계약서를 백엔드에 보내 진단 기록으로 저장한다."""
    response = requests.post(
        f"{BACKEND_BASE_URL}/api/v1/contracts/register-diagnosis",
        data={
            "address": address,
            "deposit_amount": deposit_amount,
        },
        files={
            "registry_document": (
                registry_file.name,
                registry_file.getvalue(),
                registry_file.type or "application/octet-stream",
            ),
            "lease_contract": (
                contract_file.name,
                contract_file.getvalue(),
                contract_file.type or "application/octet-stream",
            ),
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


DEMO_REPLIES = [
    {
        "q_match": ["근저당", "담보", "대출"],
        "answer": (
            "<b>근저당은 보증금 회수 가능성을 크게 흔드는 핵심 위험 요소입니다.</b><br/><br/>"
            "업로드한 등기부등본에서 근저당·저당권·채권최고액 문구가 발견되면, "
            "해당 권리가 임차인의 보증금보다 먼저 변제되는 선순위 권리인지 확인해야 합니다.<br/><br/>"
            "<b>대안:</b> 잔금일까지 말소 조건을 특약에 넣고, 미말소 시 계약 해제와 보증금 반환 조건을 명확히 적는 것이 좋습니다."
        ),
        "sources": [
            "📄 업로드 등기부등본",
            "⚖️ 주택임대차보호법 제3조의2",
            "📝 권리관계 점검 기준",
        ],
    },
    {
        "q_match": ["전세가율", "시세", "위험"],
        "answer": (
            "<b>전세가율은 보증금이 매매 시세 대비 얼마나 높은지 보는 지표입니다.</b><br/><br/>"
            "업로드한 계약서의 보증금과 실거래가/시세 데이터를 함께 비교해야 정확한 전세가율을 계산할 수 있습니다. "
            "일반적으로 비율이 높을수록 경매나 가격 하락 상황에서 보증금 회수 위험이 커집니다.<br/><br/>"
            "현재 업로드 진단에서는 문서 기반 위험 신호를 먼저 보여주고, 시세 연동값이 있으면 전세가율 판단까지 함께 확장할 수 있습니다."
        ),
        "sources": [
            "🏠 실거래가/시세 비교 기준",
            "⚖️ 보증보험 심사 기준",
        ],
    },
    {
        "q_match": ["특약", "계약서"],
        "answer": (
            "<b>업로드 계약서의 특약은 권리관계 위험과 함께 확인해야 합니다.</b><br/><br/>"
            "① <b>선순위 권리 말소 조건부 특약</b> — 잔금일까지 등기부상 위험 권리 말소 미이행 시 본 계약은 무효로 하며, "
            "임대인은 즉시 보증금을 반환한다.<br/>"
            "② <b>권리변동 통지 의무</b> — 계약 후 등기부에 새로운 권리(근저당·가압류·신탁 등)가 추가되는 경우 임대인은 즉시 통지하고 "
            "임차인은 계약을 해지할 권리를 갖는다.<br/>"
            "③ <b>전입신고·확정일자 보장</b> — 임대인은 임차인의 전입신고와 확정일자 취득에 협조하며, 이를 방해하는 일체의 행위를 하지 않는다."
        ),
        "sources": [
            "📋 주택임대차표준계약서",
            "⚖️ 주택임대차보호법 제10조",
            "📝 변호사 권장 특약 가이드",
        ],
    },
]

DEFAULT_REPLY = {
    "answer": (
        "아직 이 상담창에 연결된 업로드 진단 결과가 없습니다.<br/><br/>"
        "등기부등본과 임대차계약서를 업로드해 진단 기록을 등록하면, "
        "그 문서에서 발견된 근저당·신탁·압류·특약 등 실제 위험 신호를 기준으로 답변하겠습니다."
    ),
    "sources": ["📄 업로드 대기 중"],
}


LEVEL_KO = {"danger": "위험", "caution": "주의", "safe": "안전"}


def normalize_level(value: str, score: float = 0) -> str:
    """백엔드 위험 등급을 채팅 화면용 등급으로 변환한다."""
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


def risk_factor_to_chat_item(factor: dict) -> tuple[str, str, str, str]:
    """백엔드 위험 신호를 채팅 응답의 위험 항목 형식으로 변환한다."""
    severity = str(factor.get("severity", "")).upper()
    tone = "danger" if severity in {"HIGH", "CRITICAL"} else "caution" if severity == "MEDIUM" else "safe"
    meta = "치명" if tone == "danger" else "주의" if tone == "caution" else "안전"
    return (
        factor.get("description") or factor.get("factor_id") or "문서 기반 확인 항목",
        meta,
        tone,
        factor.get("advice") or "업로드 문서 원문과 계약 조건을 함께 확인하세요.",
    )


def build_uploaded_property_context(result: dict, registry_name: str, contract_name: str) -> dict:
    """업로드 진단 결과를 채팅 컨텍스트로 변환한다."""
    score = float(result.get("risk_score") or 0)
    parsed_fields = result.get("parsed_fields") or {}
    risk_factors = result.get("risk_factors") or []
    address = parsed_fields.get("address") or result.get("summary") or "업로드 계약서"
    deposit = parsed_fields.get("deposit_amount")
    deposit_text = f"{deposit:,}만원" if isinstance(deposit, int) else "-"
    senior = "확인 필요"
    if any(item.get("factor_id") == "MORTGAGE" for item in risk_factors):
        senior = "근저당/저당권 발견"
    return {
        "id": 0,
        "session_id": result.get("session_id", ""),
        "addr": str(address),
        "deposit": deposit_text,
        "area": "-",
        "year": "-",
        "score": int(score),
        "level": normalize_level(result.get("risk_level"), score),
        "ratio": "-",
        "senior": senior,
        "hug": "확인 필요",
        "risks": [risk_factor_to_chat_item(item) for item in risk_factors],
        "summary": result.get("summary", ""),
        "sources": [f"📄 {registry_name}", f"📋 {contract_name}"],
    }


def build_context_key(mode: str, ctx_doc: dict | None, ctx_prop: dict | None) -> str:
    """현재 상담 컨텍스트가 바뀌었는지 확인할 키를 만든다."""
    if mode == "doc" and ctx_doc:
        return f"doc:v2:{ctx_doc.get('title', '')}:{ctx_doc.get('kind', '')}"
    if mode == "property" and ctx_prop:
        return f"property:v2:{ctx_prop.get('session_id') or ctx_prop.get('id') or ctx_prop.get('addr')}"
    return "default:v2"


def initial_assistant_message(mode: str, ctx_doc: dict | None, ctx_prop: dict | None) -> dict:
    """모드별 첫 안내 메시지를 생성한다."""
    if mode == "default":
        return DEFAULT_REPLY
    reply = find_reply("", ctx_doc=ctx_doc if mode == "doc" else None, ctx_prop=ctx_prop if mode == "property" else None)
    return {"answer": reply["answer"], "sources": reply["sources"]}


def quick_questions_for(mode: str, ctx: dict | None) -> list[str]:
    """모드(default/doc/property)에 맞는 빠른 질문 4개 생성."""
    if mode == "doc" and ctx:
        kind = ctx.get("kind", "")
        keywords = ctx.get("keywords", [])
        kw1 = keywords[0] if len(keywords) > 0 else "핵심 주제"
        if kind == "판례":
            return [
                "핵심 판시 사항 요약해줘",
                f"{kw1} 관련 법리가 뭐야?",
                "내 매물에 어떻게 적용되나요?",
                "유사한 다른 판례가 있나요?",
            ]
        if kind == "피해 사례":
            return [
                "주요 위험 신호 알려줘",
                f"{kw1} 예방 체크리스트는?",
                "내 매물과 비교해줘",
                "관련 구제 절차는?",
            ]
        if kind == "특약":
            return [
                "이 특약을 그대로 써도 되나요?",
                "법적 효력 근거가 뭔가요?",
                "내 계약서 어디에 넣나요?",
                "위반 시 보호받는 절차는?",
            ]
        return [
            "핵심 요지를 알려줘",
            f"{kw1}에 대해 더 자세히",
            "내 매물에 어떻게 적용되나요?",
            "인용할 만한 조항 있나요?",
        ]

    if mode == "property" and ctx:
        level = ctx.get("level", "")
        first_risk = ctx["risks"][0][0] if ctx.get("risks") else "위험 신호"
        if level == "danger":
            return [
                f"{first_risk} — 왜 위험한가요?",
                "이 매물 계약을 포기해야 할까요?",
                "보증보험 가입 가능한가요?",
                "어떤 특약을 추가해야 안전한가요?",
            ]
        if level == "caution":
            return [
                f"{first_risk} 자세히 알려줘",
                "어떤 특약이 필요한가요?",
                "안전 신호도 있나요?",
                "계약 진행해도 될까요?",
            ]
        return [
            "이 매물 정말 안전한가요?",
            "추가로 확인할 항목은?",
            "계약 시 주의사항은?",
            "보증보험 가입 조건 알려줘",
        ]

    # default
    return [
        "근저당이 왜 문제인가요?",
        "특약 문구 예시 보여줘",
        "HUG 가입 조건 알려줘",
        "경매 절차 더 설명해줘",
    ]


def _badge(text: str) -> str:
    return (
        "<div style='background:var(--blue-soft);border-radius:8px;"
        "padding:8px 12px;margin-bottom:10px;font-size:12px;color:var(--blue);font-weight:700'>"
        f"{text}</div>"
    )


def find_reply(
    question: str,
    ctx_doc: dict | None = None,
    ctx_prop: dict | None = None,
) -> dict:
    """질문에 대한 응답 생성. ctx_doc / ctx_prop 우선순위로 근거 자료를 주입."""
    # 1) 데모 키워드 매칭
    base = None
    for r in DEMO_REPLIES:
        if any(kw in question for kw in r["q_match"]):
            base = r
            break

    # 2) 문서 컨텍스트 우선
    if ctx_doc:
        title = ctx_doc.get("title", "")
        kind = ctx_doc.get("kind", "")
        summary = ctx_doc.get("summary", "")
        keywords = ctx_doc.get("keywords", [])
        source_chip = f"📄 {title}"
        badge = _badge(f"📎 {title} ({kind}) 문서 기반 답변")
        if base:
            return {
                "answer": badge + base["answer"],
                "sources": [source_chip] + base["sources"],
            }
        kw_text = ", ".join(keywords[:5]) if keywords else "이 문서의 핵심 주제"
        return {
            "answer": (
                badge
                + f"질문하신 내용을 <b>{title}</b> 문서를 근거로 살펴보겠습니다.<br/><br/>"
                + f"이 문서는 <b>{kw_text}</b> 를 다루고 있으며, 주요 내용은 다음과 같습니다:<br/><br/>"
                + f"<i>{summary}</i><br/><br/>"
                + "더 구체적인 부분이 궁금하시면 다음과 같이 질문해 주세요:<br/>"
                + "• 이 문서의 핵심 조항/판시 사항이 뭔가요?<br/>"
                + "• 내 매물에 어떻게 적용되나요?<br/>"
                + "• 계약서·특약에 인용할 수 있는 문구는?"
            ),
            "sources": (
                [source_chip, f"🔖 키워드: {', '.join(keywords[:4])}"]
                if keywords else [source_chip]
            ),
        }

    # 3) 매물 컨텍스트
    if ctx_prop:
        addr = ctx_prop.get("addr", "")
        score = ctx_prop.get("score", 0)
        level = ctx_prop.get("level", "")
        ratio = ctx_prop.get("ratio", "")
        hug = ctx_prop.get("hug", "")
        risks = ctx_prop.get("risks", [])
        source_id = ctx_prop.get("session_id") or f"{int(ctx_prop.get('id') or 0):03d}"
        source_chip = f"📋 매물 진단 #{source_id}"
        badge = _badge(f"🏠 {addr} · 위험도 {score}점 ({LEVEL_KO.get(level, '')})")
        risk_list_html = "".join(
            f"<li><b>{r[0]}</b> ({r[1]}) — {r[3] if len(r) > 3 else ''}</li>"
            for r in risks[:5]
        )
        return {
            "answer": (
                badge
                + f"이 매물 <b>{addr}</b>은(는) 다음과 같은 진단 결과가 있습니다:<br/><br/>"
                + f"• 위험도: <b>{score}점</b> ({LEVEL_KO.get(level, '')})<br/>"
                + f"• 전세가율: <b>{ratio}</b><br/>"
                + f"• 선순위 권리: <b>{ctx_prop.get('senior', '')}</b><br/>"
                + f"• 보증보험: <b>{hug}</b><br/><br/>"
                + (f"<b>주요 위험 신호</b><ul>{risk_list_html}</ul>" if risk_list_html else "")
                + "구체적으로 어떤 위험 항목이나 대응 방법이 궁금하신가요?"
            ),
            "sources": [source_chip, f"⚠️ 위험 신호 {len(risks)}건"],
        }

    # 4) 컨텍스트 없음 — 기본
    return base or DEFAULT_REPLY


# ─── 화면 ──────────────────────────────────────────────
def render():
    # ─── 모드 결정 ───
    ctx_doc = st.session_state.get("chat_context_doc")
    ctx_prop = st.session_state.get("chat_context_property")
    if ctx_doc:
        mode = "doc"
    elif ctx_prop:
        mode = "property"
    else:
        mode = "default"
    context_key = build_context_key(mode, ctx_doc, ctx_prop)

    # ─── 컨텍스트 배너 ───
    if mode == "doc":
        head_l, head_r = st.columns([5, 1])
        with head_l:
            st.markdown(
                f"""
                <div style="background:var(--blue-soft);border:1px solid #cfe1ff;border-radius:12px;
                            padding:12px 16px;margin-bottom:12px;font-size:13px;color:var(--gray-900)">
                  📎 <b>{ctx_doc['title']}</b>
                  <span style="background:var(--blue);color:#fff;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:800;margin-left:8px">{ctx_doc['kind']}</span>
                  <div style="color:var(--gray-700);font-size:12px;margin-top:4px;line-height:1.5">{ctx_doc['summary']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with head_r:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            if st.button("× 자료 해제", key="clear_ctx_doc", use_container_width=True):
                del st.session_state.chat_context_doc
                st.session_state.pop("messages", None)
                st.rerun()
    elif mode == "property":
        level_color = {"danger": "var(--red)", "caution": "var(--amber)", "safe": "var(--green)"}.get(ctx_prop["level"], "var(--gray-500)")
        level_bg = {"danger": "var(--red-soft)", "caution": "var(--amber-soft)", "safe": "var(--green-soft)"}.get(ctx_prop["level"], "var(--gray-100)")
        head_l, head_r = st.columns([5, 1])
        with head_l:
            st.markdown(
                f"""
                <div style="background:{level_bg};border:1px solid {level_color};border-radius:12px;
                            padding:12px 16px;margin-bottom:12px;font-size:13px;color:var(--gray-900)">
                  🏠 <b>{ctx_prop['addr']}</b>
                  <span style="background:{level_color};color:#fff;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:800;margin-left:8px">
                    {ctx_prop['score']}점 · {LEVEL_KO.get(ctx_prop['level'], '')}
                  </span>
                  <div style="color:var(--gray-700);font-size:12px;margin-top:6px;line-height:1.5">
                    전세 {ctx_prop['deposit']} · {ctx_prop['area']} · {ctx_prop['year']} ·
                    전세가율 <b>{ctx_prop['ratio']}</b> · 보증보험 <b>{ctx_prop['hug']}</b>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with head_r:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            if st.button("× 매물 해제", key="clear_ctx_prop", use_container_width=True):
                del st.session_state.chat_context_property
                st.session_state.pop("messages", None)
                st.rerun()

    # 상단 법령 개정 알림
    law_banner(
        "<b>2026.3.1 주택임대차보호법 제8조 개정</b> · 소액임차인 우선변제 한도가 "
        "₩1억 → <b>₩1.5억</b>으로 상향",
        pill="법령 개정",
    )

    # ─── 헤더 (모드별 제목/서브) ───
    if mode == "doc":
        eyebrow = f"상담 챗 · {ctx_doc['kind']} 자료 기반"
        title = "선택한 자료 기반 AI 상담"
        head_sub = (
            f"<b>{ctx_doc['title']}</b> 문서를 근거로 질문에 답합니다. "
            "모든 답변은 출처를 함께 보여드립니다."
        )
    elif mode == "property":
        analysis_id = ctx_prop.get("session_id") or f"{int(ctx_prop.get('id') or 0):03d}"
        eyebrow = f"상담 챗 · {ctx_prop['addr']} · 분석 #{analysis_id}"
        title = "내 매물 기반 AI 상담"
        head_sub = (
            f"진단된 매물(<b>{ctx_prop['addr']}</b>)의 위험 항목·계약 정보를 근거로 답변합니다."
        )
    else:
        eyebrow = "상담 챗 · 업로드 문서 기반"
        title = "내 자료 기반 AI 상담"
        head_sub = "업로드한 등기부등본·계약서를 근거로 질문에 답합니다. 모든 답변은 출처를 함께 보여드립니다."

    col_h1, col_h2 = st.columns([3, 1.4])
    with col_h1:
        st.markdown(
            f'<div style="font-size:12px;font-weight:700;color:var(--gray-500);'
            f'letter-spacing:.04em;margin-bottom:6px">{eyebrow}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"# {title}")
        st.markdown(
            f'<p style="color:var(--gray-500);font-size:14px;margin-top:-8px">{head_sub}</p>',
            unsafe_allow_html=True,
        )
    with col_h2:
        st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
        if mode == "property":
            render_status_pill(ctx_prop["level"], ctx_prop["score"], f"{LEVEL_KO[ctx_prop['level']]} 매물")
        # doc 모드는 상태 핀 생략 (배너로 이미 표시)

    section_divider()

    # ─── 자료 업로드 (default 모드만) ───
    if mode == "default":
        st.markdown("### 📎 내 자료")
        st.markdown(
            '<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">'
            "업로드한 자료를 기반으로 챗봇이 답변합니다.</p>",
            unsafe_allow_html=True,
        )

        info_l, info_r = st.columns([2, 1])
        with info_l:
            address_input = st.text_input(
                "주소",
                value="",
                placeholder="계약서에 적힌 주소를 입력하거나 문서 업로드 후 자동 추출 결과를 확인하세요.",
            )
        with info_r:
            deposit_input = st.number_input("보증금 (만원)", min_value=0, value=0, step=500, format="%d")

        doc_l, doc_r = st.columns(2)
        with doc_l:
            registry_file = st.file_uploader(
                "등기부등본 (.docx)",
                type=["docx"],
                help="등기소·정부24에서 발급한 등기부등본을 docx 파일로 첨부하세요.",
            )
        with doc_r:
            contract_file = st.file_uploader(
                "임대차계약서 (.docx)",
                type=["docx"],
                help="특약 조항이 모두 포함된 임대차계약서를 docx 파일로 첨부하세요.",
            )

        if registry_file and contract_file:
            if st.button("업로드 문서로 진단 기록 등록", type="primary", use_container_width=True):
                try:
                    with st.spinner("문서를 분석하고 진단 기록에 저장하는 중입니다..."):
                        result = register_documents_to_history(
                            registry_file,
                            contract_file,
                            address_input,
                            int(deposit_input),
                        )
                    st.session_state.history_loaded = False
                    st.session_state.chat_context_property = build_uploaded_property_context(
                        result,
                        registry_file.name,
                        contract_file.name,
                    )
                    st.session_state.pop("messages", None)
                    st.session_state.pop("chat_message_context_key", None)
                    st.success(
                        f"진단 기록에 등록되었습니다. 위험도 {result['risk_score']:.0f}점 · {result['risk_level']}"
                    )
                    st.rerun()
                except requests.exceptions.ConnectionError:
                    st.error("FastAPI 서버에 연결할 수 없습니다. 백엔드 서버가 켜져 있는지 확인해 주세요.")
                except requests.exceptions.HTTPError as exc:
                    detail = exc.response.text if exc.response is not None else str(exc)
                    st.error(f"진단 기록 등록 실패: {detail}")
                except Exception as exc:
                    st.error(f"진단 기록 등록 중 오류가 발생했습니다: {exc}")
        else:
            st.info("등기부등본과 임대차계약서를 모두 업로드하면 진단 기록에 등록할 수 있습니다.")

        section_divider()

    # ─── 챗봇 섹션 (모드별 서브타이틀/빠른질문) ───
    st.markdown("### 💬 궁금한 점을 물어보세요")
    if mode == "doc":
        sub = f"<b>{ctx_doc['title']}</b> ({ctx_doc['kind']}) 자료를 근거로 답변합니다."
    elif mode == "property":
        sub = f"이 매물 <b>{ctx_prop['addr']}</b>의 진단 결과·위험 신호를 근거로 답변합니다."
    else:
        sub = "내 자료(등기부·계약서·종로구 실거래가)를 근거로 답변합니다."
    st.markdown(
        f'<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">{sub}</p>',
        unsafe_allow_html=True,
    )

    # 세션 메시지 초기화 또는 상담 컨텍스트 변경 시 첫 답변을 다시 만든다.
    if (
        "messages" not in st.session_state
        or st.session_state.get("chat_message_context_key") != context_key
    ):
        first_reply = initial_assistant_message(mode, ctx_doc, ctx_prop)
        st.session_state.messages = [{
            "role": "assistant",
            "content": first_reply["answer"],
            "sources": first_reply["sources"],
        }]
        st.session_state.chat_message_context_key = context_key

    # 빠른 질문 (모드별 동적)
    quick = st.columns(4)
    active_ctx = ctx_doc if mode == "doc" else (ctx_prop if mode == "property" else None)
    quick_qs = quick_questions_for(mode, active_ctx)

    for i, q in enumerate(quick_qs):
        with quick[i]:
            if st.button(q, key=f"q_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": q})
                reply = find_reply(q, ctx_doc=ctx_doc, ctx_prop=ctx_prop)
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply["answer"], "sources": reply["sources"]}
                )
                st.rerun()

    # 메시지 렌더링
    st.markdown('<div style="margin-top:16px"></div>', unsafe_allow_html=True)
    for m in st.session_state.messages:
        if m["role"] == "user":
            st.markdown(f'<div class="chat-q">{m["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-a">{m["content"]}</div>', unsafe_allow_html=True)
            if m.get("sources"):
                refs = "".join(f'<span class="ref">{s}</span>' for s in m["sources"])
                st.markdown(
                    f'<div class="rag-src"><b>근거 자료</b>{refs}</div>',
                    unsafe_allow_html=True,
                )

    # 입력
    placeholder = {
        "doc": "예: 이 문서의 핵심 판시 사항이 뭔가요?",
        "property": "예: 발견된 근저당은 어떻게 대응해야 하나요?",
        "default": "예: 이 특약이 왜 위험한가요?",
    }[mode]
    if prompt := st.chat_input(placeholder):
        st.session_state.messages.append({"role": "user", "content": prompt})
        reply = find_reply(
            prompt,
            ctx_doc=st.session_state.get("chat_context_doc"),
            ctx_prop=st.session_state.get("chat_context_property"),
        )
        st.session_state.messages.append(
            {"role": "assistant", "content": reply["answer"], "sources": reply["sources"]}
        )
        st.rerun()
