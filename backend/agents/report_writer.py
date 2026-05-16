"""
report_writer — 최종 진단 리포트 생성 에이전트

입력: ModelAgentResult + SpecialTermsResult
처리: 전체 결과 종합 → LLM 최종 리포트 생성 → JSON 저장
출력: 최종 리포트 문장 + 저장된 JSON 경로
"""

import json
import os
import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from backend.config import get_llm
from backend.agents.model_agent import ModelAgentResult
from backend.agents.special_terms_agent import SpecialTermsResult


REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")


class DiagnosisReport(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    user_info: dict = Field(default_factory=dict)
    price_diagnosis: str = ""
    special_terms: list[dict] = Field(default_factory=list)
    terms_diagnosis: str = ""
    final_report: str = ""


class ReportWriterResult(BaseModel):
    success: bool
    report: DiagnosisReport | None = None
    saved_path: str = ""
    final_report: str = ""


FINAL_REPORT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 전세계약 위험 진단 전문 리포터입니다.
가격 분석과 특약 분석 결과를 종합하여, 임차인에게 전달할 최종 진단 리포트를 작성하세요.

작성 규칙:
- 가격 위험도와 특약 위험을 모두 종합적으로 판단하세요
- 가장 위험한 요인을 먼저 짚어주세요
- 구체적인 숫자와 판례 근거를 활용하세요
- 임차인이 취해야 할 구체적 행동을 권고하세요
- 존댓말로, 5~8문장 이내로 작성하세요
- 종합 위험 등급을 명시하세요 (위험/주의/안전)"""),
    ("human", """=== 가격 분석 ===
주소: {address}
전세금: {deposit:,}만원
위험등급: {price_risk_level}
위험점수: {price_risk_score}/100
진단: {price_diagnosis}

=== 특약 분석 ===
특약 수: {num_terms}건
{terms_summary}
특약 종합: {terms_diagnosis}""")
])


def build_report_data(model_result: ModelAgentResult,
                      terms_result: SpecialTermsResult | None) -> DiagnosisReport:
    report = DiagnosisReport()

    report.user_info = model_result.user_info.model_dump()
    report.price_diagnosis = model_result.diagnosis

    if terms_result and terms_result.analyses:
        report.special_terms = [
            {
                "term_text": a.term_text,
                "risk_level": a.risk_level,
                "related_cases": a.related_cases,
                "related_laws": a.related_laws,
                "diagnosis": a.diagnosis,
            }
            for a in terms_result.analyses
        ]
        report.terms_diagnosis = terms_result.overall_diagnosis

    return report


def generate_final_report(model_result: ModelAgentResult,
                          terms_result: SpecialTermsResult | None) -> str:
    terms_summary = "특약 없음"
    num_terms = 0

    if terms_result and terms_result.analyses:
        num_terms = len(terms_result.analyses)
        lines = []
        for i, a in enumerate(terms_result.analyses, 1):
            lines.append(f"특약{i} [{a.risk_level}]: {a.term_text[:50]}... → {a.diagnosis[:80]}")
        terms_summary = "\n".join(lines)

    llm = get_llm(temperature=0.3)
    chain = FINAL_REPORT_PROMPT | llm

    response = chain.invoke({
        "address": model_result.user_info.address,
        "deposit": model_result.user_info.deposit,
        "price_risk_level": model_result.user_info.risk_level,
        "price_risk_score": model_result.user_info.risk_score,
        "price_diagnosis": model_result.diagnosis,
        "num_terms": num_terms,
        "terms_summary": terms_summary,
        "terms_diagnosis": terms_result.overall_diagnosis if terms_result else "특약 없음",
    })

    return response.content.strip()


def save_report(report: DiagnosisReport) -> str:
    os.makedirs(REPORT_DIR, exist_ok=True)
    filename = f"report_{report.session_id}.json"
    filepath = os.path.join(REPORT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, ensure_ascii=False, indent=2)

    return filepath


def write_report(model_result: ModelAgentResult,
                 terms_result: SpecialTermsResult | None = None) -> ReportWriterResult:
    """최종 리포트 생성 + JSON 저장"""

    # 1. 리포트 데이터 구성
    report = build_report_data(model_result, terms_result)

    # 2. LLM 최종 리포트 생성
    report.final_report = generate_final_report(model_result, terms_result)

    # 3. JSON 저장
    saved_path = save_report(report)

    return ReportWriterResult(
        success=True,
        report=report,
        saved_path=saved_path,
        final_report=report.final_report,
    )
