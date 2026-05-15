"""
special_terms_agent — 특약 조항 위험 분석 에이전트 (Neo4j Graph DB 활용)

흐름:
  1. 특약 텍스트 → LLM이 관련 법률 쟁점 키워드 추출
  2. 키워드로 Neo4j 그래프 검색 → 관련 판례 + 법조문 탐색
  3. 판례 근거를 바탕으로 LLM이 위험도 판정 + 진단 문장 생성

저장: 특약별 분석 결과 (챗봇 참조용)
출력: 진단 문장
"""

import json
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from backend.config import get_llm
from backend.graph.graph_builder import query_by_issue


# ── 데이터 모델 ──────────────────────────────────────────

class TermAnalysis(BaseModel):
    """개별 특약 분석 결과"""
    term_text: str
    risk_level: str = "미상"  # 위험/주의/안전
    related_issues: list[str] = Field(default_factory=list)
    related_cases: list[str] = Field(default_factory=list)
    related_laws: list[str] = Field(default_factory=list)
    diagnosis: str = ""


class SpecialTermsResult(BaseModel):
    """special_terms_agent 최종 반환"""
    success: bool
    analyses: list[TermAnalysis] = Field(default_factory=list)
    overall_diagnosis: str = ""


# ── 쟁점 키워드 추출 프롬프트 ────────────────────────────

ISSUE_EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 한국 임대차 법률 전문가입니다.
주어진 전세 계약서 특약 조항을 분석하여, 관련된 법률 쟁점 키워드를 추출하세요.

반드시 JSON 배열로만 응답하세요. 다른 텍스트는 포함하지 마세요.

키워드 예시: 보증금반환, 대항력, 우선변제권, 근저당, 전세권, 계약해제,
원상복구, 임차권등기, 전입신고, 확정일자, 사기죄, 배임, 경매,
이중매매, 보증보험, 신탁, 권리변동, 계약무효

["키워드1", "키워드2", "키워드3"]"""),
    ("human", "특약 조항: {term}")
])


# ── 위험도 판정 프롬프트 ─────────────────────────────────

RISK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 전세 계약 특약 위험도를 진단하는 법률 AI입니다.
특약 조항과 관련 판례 정보를 바탕으로 위험도를 판정하세요.

반드시 아래 JSON 형식으로만 응답하세요.

{{
  "risk_level": "위험 또는 주의 또는 안전",
  "diagnosis": "2~3문장 진단 결과"
}}

판정 기준:
- 위험: 판례에서 무효/사기/배임으로 판정된 유형과 유사하거나, 임차인에게 불리한 조항
- 주의: 법적 보호가 불충분하거나, 추가 확인이 필요한 조항
- 안전: 임차인을 보호하는 표준적인 특약"""),
    ("human", """특약 조항: {term}

관련 판례 정보:
{case_info}""")
])


# ── 핵심 로직 ────────────────────────────────────────────

def extract_issues(term: str) -> list[str]:
    """특약에서 쟁점 키워드 추출"""
    llm = get_llm(temperature=0.0)
    chain = ISSUE_EXTRACT_PROMPT | llm
    response = chain.invoke({"term": term})

    try:
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)
    except (json.JSONDecodeError, Exception):
        return []


def search_graph(issues: list[str]) -> list[dict]:
    """쟁점 키워드로 Neo4j 검색"""
    all_results = []
    seen_cases = set()

    for issue in issues:
        try:
            cases = query_by_issue(issue)
            for case in cases:
                if case["case_id"] not in seen_cases:
                    seen_cases.add(case["case_id"])
                    all_results.append(case)
        except Exception:
            continue

    return all_results[:5]  # 상위 5개만


def format_case_info(cases: list[dict]) -> str:
    """판례 정보를 LLM용 텍스트로 포맷"""
    if not cases:
        return "관련 판례를 찾지 못했습니다."

    lines = []
    for c in cases:
        laws = ", ".join(c.get("laws", [])) if c.get("laws") else "없음"
        lines.append(
            f"- {c.get('court', '')} {c['case_id']} ({c.get('date', '')})\n"
            f"  요지: {c.get('summary', '정보 없음')}\n"
            f"  관련 법조문: {laws}"
        )
    return "\n".join(lines)


def analyze_single_term(term: str) -> TermAnalysis:
    """단일 특약 분석"""
    # 1. 쟁점 키워드 추출
    issues = extract_issues(term)

    # 2. Neo4j 검색
    cases = search_graph(issues)

    # 3. LLM 위험도 판정
    case_info = format_case_info(cases)
    llm = get_llm(temperature=0.2)
    chain = RISK_PROMPT | llm
    response = chain.invoke({"term": term, "case_info": case_info})

    try:
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        parsed = json.loads(text)
        risk_level = parsed.get("risk_level", "미상")
        diagnosis = parsed.get("diagnosis", "")
    except (json.JSONDecodeError, Exception):
        risk_level = "미상"
        diagnosis = "특약 분석 중 오류가 발생했습니다."

    return TermAnalysis(
        term_text=term,
        risk_level=risk_level,
        related_issues=issues,
        related_cases=[c["case_id"] for c in cases],
        related_laws=list({law for c in cases for law in c.get("laws", []) if law}),
        diagnosis=diagnosis,
    )


# ── 진입점 ───────────────────────────────────────────────

OVERALL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 전세 계약 특약 분석 전문가입니다.
개별 특약 분석 결과를 종합하여 전체 소견을 작성하세요.
3~4문장으로 간결하게, 핵심 위험 요인과 권고사항을 포함하세요."""),
    ("human", "{analyses_text}")
])


def analyze_special_terms(terms: list[str]) -> SpecialTermsResult:
    """특약 조항 목록 전체 분석"""
    if not terms:
        return SpecialTermsResult(
            success=True,
            overall_diagnosis="특약 조항이 없습니다. 표준 계약 조건만으로 계약이 체결됩니다."
        )

    analyses = []
    for i, term in enumerate(terms, 1):
        print(f"  특약 {i}/{len(terms)} 분석 중...")
        analysis = analyze_single_term(term)
        analyses.append(analysis)

    # 종합 소견
    analyses_text = "\n\n".join(
        f"특약 {i+1}: {a.term_text}\n위험도: {a.risk_level}\n진단: {a.diagnosis}"
        for i, a in enumerate(analyses)
    )

    llm = get_llm(temperature=0.3)
    chain = OVERALL_PROMPT | llm
    response = chain.invoke({"analyses_text": analyses_text})

    return SpecialTermsResult(
        success=True,
        analyses=analyses,
        overall_diagnosis=response.content.strip(),
    )
