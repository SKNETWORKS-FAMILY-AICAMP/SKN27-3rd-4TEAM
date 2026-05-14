"""
PDF 검토 에이전트

노트북 패턴 기반:
  1. @tool 로 도구 정의 (parse_contract_document, check_required_fields)
  2. create_agent 로 에이전트 생성
  3. supervisor 는 이 에이전트를 invoke() 로 호출하고 결과를 받음

사용 예:
    agent = create_pdf_review_agent()
    result = agent.invoke({"messages": [HumanMessage(content="file_path: /path/to/contract.docx")]})
"""
from __future__ import annotations

import sys
import os

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from langgraph.prebuilt import create_react_agent as create_agent
from langchain_core.messages import HumanMessage

from pcj_common.tools.contract_tools import check_required_fields, parse_contract_document

try:
    from pcj_common.tools.llm import build_chat_llm
except ImportError:
    build_chat_llm = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 에이전트 시스템 프롬프트
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
당신은 전세 계약서를 검토하는 전문 AI 에이전트입니다.
반드시 아래 순서대로 도구를 사용하여 작업하세요.

[작업 순서]
1. parse_contract_document 도구로 계약서를 읽습니다.
   - 이 도구는 계약서를 코드로 분석하여 섹션별로 구조화된 텍스트를 반환합니다.
   - 각 항목은 [ 계약 당사자 ], [ 임대 목적물 ], [ 계약 조건 ], [ 특약사항 ] 섹션으로 나뉩니다.
   - 항목이 없으면 "없음" 으로 표시됩니다.

2. 반환된 구조화 텍스트에서 다음 필드를 읽어 JSON 을 만듭니다:
   - landlord     : "임대사업자(임대인) 이름" 항목의 값. "없음"이면 null.
   - tenant       : "임차인 이름" 항목의 값. "없음"이면 null.
   - address      : "주택 소재지" 항목의 값. "없음"이면 null.
   - area         : "전용면적" 항목의 숫자 값. "없음"이면 null.
   - housing_type : "주택 유형" 항목의 값. "없음"이면 null.
   - deposit      : "전세금(임대보증금)" 항목의 숫자 값(원 단위 정수). "없음"이면 null.
   - period       : "임대 기간" 항목의 값. "없음"이면 null.
   - special_terms: "특약사항" 섹션의 항목들을 문자열 리스트로. 없으면 [].

3. 만든 JSON 문자열을 check_required_fields 도구에 전달합니다.

4. check_required_fields 도구의 반환값을 그대로 최종 답변으로 출력합니다.

[절대 원칙]
- 구조화 텍스트에 "없음"으로 표시된 항목은 반드시 null 로 설정하세요.
- 절대로 다른 섹션의 값으로 대체하거나 추측하지 마세요.
- 도구 없이 직접 답변하지 마세요.
""".strip()


# ---------------------------------------------------------------------------
# 에이전트 팩토리
# ---------------------------------------------------------------------------

def create_pdf_review_agent():
    """
    PDF 검토 에이전트를 생성하여 반환합니다.

    Returns
    -------
    CompiledStateGraph
        create_agent 로 생성된 실행 가능한 에이전트.
        supervisor 에서 invoke() 로 호출합니다.
    """
    if build_chat_llm is None:
        raise RuntimeError("LLM 을 사용할 수 없습니다. pcj_common.tools.llm 을 확인하세요.")

    llm = build_chat_llm(temperature=0.0)
    tools = [parse_contract_document, check_required_fields]

    agent = create_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_PROMPT,
    )
    return agent


# ---------------------------------------------------------------------------
# 편의 함수: 파일 경로를 받아 바로 실행
# ---------------------------------------------------------------------------

def run_pdf_review_agent(file_path: str) -> str:
    """
    계약서 파일 경로를 받아 에이전트를 실행하고 결과 JSON 문자열을 반환합니다.

    Parameters
    ----------
    file_path : str
        .docx 또는 .pdf 계약서 파일 경로

    Returns
    -------
    str
        check_required_fields 결과 JSON 문자열
        {"status": "success", "data": {...}}
        또는
        {"status": "missing_data", "missing_fields": [...], "message": "..."}
    """
    agent = create_pdf_review_agent()
    result = agent.invoke({
        "messages": [HumanMessage(content=f"다음 계약서 파일을 검토해주세요: {file_path}")]
    })
    return result["messages"][-1].content
