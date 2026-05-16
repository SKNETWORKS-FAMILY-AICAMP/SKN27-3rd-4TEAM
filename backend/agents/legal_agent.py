"""
legal_agent — RAG 기반 법률상담 에이전트

기능:
  1. 사용자 질문 → 법률 쟁점 키워드 추출
  2. Neo4j 그래프에서 관련 판례 + 법조문 검색
  3. 검색 결과를 근거로 법률 상담 응답 생성

출력: 판례 근거가 포함된 법률 상담 응답
"""

import json
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from backend.config import get_llm
from backend.graph.graph_builder import query_by_issue, query_related_cases


class LegalReference(BaseModel):
    case_id: str = ""
    court: str = ""
    date: str = ""
    summary: str = ""
    laws: list[str] = Field(default_factory=list)


class LegalResponse(BaseModel):
    answer: str = ""
    references: list[LegalReference] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


# ── 쟁점 키워드 추출 ────────────────────────────────────

ISSUE_EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """사용자의 전세 관련 질문에서 법률 쟁점 키워드를 추출하세요.
반드시 JSON 배열로만 응답하세요.

추출 가능한 키워드:
보증금반환, 대항력, 우선변제권, 근저당, 전세권, 계약해제, 원상복구,
임차권등기, 전입신고, 확정일자, 사기죄, 배임, 경매, 이중매매,
보증보험, 신탁, 권리변동, 계약무효, 전세가율, 깡통전세,
소액임차인, 최우선변제, 임대인, 임차인, 보증금, 전세사기

관련 쟁점이 없으면 빈 배열 []을 반환하세요.
["키워드1", "키워드2"]"""),
    ("human", "{question}")
])


def extract_issues(question: str) -> list[str]:
    llm = get_llm(temperature=0.0)
    chain = ISSUE_EXTRACT_PROMPT | llm
    response = chain.invoke({"question": question})
    try:
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)
    except (json.JSONDecodeError, Exception):
        return []


# ── Neo4j 판례 검색 ─────────────────────────────────────

def search_cases(issues: list[str], max_results: int = 5) -> list[dict]:
    all_cases = []
    seen = set()

    for issue in issues:
        try:
            cases = query_by_issue(issue)
            for c in cases:
                cid = c.get("case_id", "")
                if cid and cid not in seen:
                    seen.add(cid)
                    all_cases.append(c)
        except Exception:
            continue

    return all_cases[:max_results]


def format_references(cases: list[dict]) -> tuple[str, list[LegalReference]]:
    if not cases:
        return "관련 판례를 찾지 못했습니다.", []

    refs = []
    lines = []
    for c in cases:
        laws = [l for l in c.get("laws", []) if l] if c.get("laws") else []
        ref = LegalReference(
            case_id=c.get("case_id", ""),
            court=c.get("court", ""),
            date=c.get("date", ""),
            summary=c.get("summary", ""),
            laws=laws,
        )
        refs.append(ref)

        law_str = ", ".join(laws) if laws else "없음"
        lines.append(
            f"■ {ref.court} {ref.case_id} ({ref.date})\n"
            f"  요지: {ref.summary}\n"
            f"  관련 법조문: {law_str}"
        )

    return "\n\n".join(lines), refs


# ── 법률 상담 응답 생성 ─────────────────────────────────

LEGAL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 한국 전세(임대차) 법률 상담 AI입니다.
사용자의 질문에 대해 관련 판례와 법조문을 근거로 정확한 법률 정보를 제공합니다.

상담 규칙:
- 관련 판례의 사건번호와 판결 요지를 구체적으로 인용하세요
- 적용되는 법조문(주택임대차보호법, 민법 등)을 명시하세요
- 임차인 보호 관점에서 실질적인 조언을 제공하세요
- 법률 자문이 아닌 정보 제공임을 명시하세요
- 확실하지 않은 사항은 전문가 상담을 권고하세요
- 4~6문장으로 답변하세요
- 존댓말을 사용하세요"""),
    ("human", """사용자 질문: {question}

참고 판례:
{case_references}""")
])


def consult(question: str) -> LegalResponse:
    """법률 상담 질문에 대한 RAG 응답 생성"""

    # 1. 쟁점 추출
    issues = extract_issues(question)

    # 2. 판례 검색
    cases = search_cases(issues)

    # 3. 참고 자료 포맷
    ref_text, refs = format_references(cases)

    # 4. LLM 응답
    llm = get_llm(temperature=0.3)
    chain = LEGAL_PROMPT | llm
    response = chain.invoke({
        "question": question,
        "case_references": ref_text,
    })

    return LegalResponse(
        answer=response.content.strip(),
        references=refs,
        issues=issues,
    )
