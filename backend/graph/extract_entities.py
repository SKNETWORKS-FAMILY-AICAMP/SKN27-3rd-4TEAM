"""
판례 PDF → 엔티티 추출 (LLM 기반)

각 판례에서 추출:
  - case_id: 사건번호 (예: 2022다48327)
  - court: 법원 (대법원, 서울고등법원, 헌법재판소 등)
  - date: 판결일
  - summary: 판결요지 (2~3문장)
  - cited_laws: 인용 법조문 목록
  - cited_cases: 인용 판례 사건번호 목록
  - issues: 쟁점 키워드 목록
"""

import os
import re
import json
import fitz  # PyMuPDF
from pydantic import BaseModel, Field
from backend.config import get_llm
from langchain_core.prompts import ChatPromptTemplate


class CaseEntity(BaseModel):
    filename: str = ""
    case_id: str = ""
    court: str = ""
    date: str = ""
    summary: str = ""
    cited_laws: list[str] = Field(default_factory=list)
    cited_cases: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 한국 법률 판례 분석 전문가입니다.
주어진 판례 텍스트에서 아래 정보를 추출하세요.

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.

{{
  "case_id": "사건번호 (예: 2022다48327)",
  "court": "법원명 (예: 대법원)",
  "date": "판결일 (예: 2022-06-15)",
  "summary": "판결요지 2~3문장 요약",
  "cited_laws": ["인용된 법조문1", "법조문2"],
  "cited_cases": ["인용된 다른 판례 사건번호1", "사건번호2"],
  "issues": ["쟁점 키워드1", "키워드2"]
}}

규칙:
- cited_laws: "주택임대차보호법 제3조", "민법 제621조" 형식
- cited_cases: 사건번호만 (예: "99다69624", "2020도9756")
- issues: 전세사기 관련 핵심 쟁점 키워드 (예: "보증금반환", "대항력", "우선변제권", "계약해제", "사기죄", "배임", "이중매매", "근저당", "경매", "임차권등기")
- 확인 불가한 항목은 빈 배열 []로"""),
    ("human", "다음은 판례 텍스트입니다:\n\n{text}")
])


def extract_text_from_pdf(filepath: str) -> str:
    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text.strip()


def parse_case_info_from_filename(filename: str) -> tuple[str, str, str]:
    """파일명에서 법원, 날짜, 사건번호 추출 (백업용)"""
    name = os.path.basename(filename).replace(".pdf", "")
    court = ""
    if "대법원" in name:
        court = "대법원"
    elif "헌법재판소" in name:
        court = "헌법재판소"
    elif "고등법원" in name or "고법" in name:
        parts = name.split()
        court = parts[0] if parts else "고등법원"

    date_match = re.search(r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})', name)
    date = ""
    if date_match:
        date = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

    case_match = re.search(r'(\d{2,4}[가-힣]+\d+)', name)
    case_id = case_match.group(1) if case_match else ""

    return court, date, case_id


def extract_entities_from_pdf(filepath: str) -> CaseEntity:
    """단일 판례 PDF에서 엔티티 추출"""
    filename = os.path.basename(filepath)
    text = extract_text_from_pdf(filepath)

    if not text:
        court, date, case_id = parse_case_info_from_filename(filepath)
        return CaseEntity(filename=filename, court=court, date=date, case_id=case_id)

    # LLM 추출
    llm = get_llm(temperature=0.0)
    chain = EXTRACT_PROMPT | llm

    truncated = text[:2000]
    response = chain.invoke({"text": truncated})

    try:
        resp_text = response.content.strip()
        if resp_text.startswith("```"):
            resp_text = resp_text.split("\n", 1)[1] if "\n" in resp_text else resp_text[3:]
            resp_text = resp_text.rsplit("```", 1)[0]
        parsed = json.loads(resp_text)
        entity = CaseEntity(filename=filename, **parsed)
    except (json.JSONDecodeError, Exception):
        court, date, case_id = parse_case_info_from_filename(filepath)
        entity = CaseEntity(filename=filename, court=court, date=date, case_id=case_id,
                           summary="LLM 추출 실패 - 파일명에서 기본 정보만 추출")

    # 파일명 정보로 보정
    if not entity.court or not entity.date or not entity.case_id:
        court, date, case_id = parse_case_info_from_filename(filepath)
        if not entity.court:
            entity.court = court
        if not entity.date:
            entity.date = date
        if not entity.case_id:
            entity.case_id = case_id

    return entity


def extract_all(pdf_dir: str = "docs/pdf/판례") -> list[CaseEntity]:
    """모든 판례 PDF에서 엔티티 추출"""
    import glob
    pdf_files = sorted(glob.glob(os.path.join(pdf_dir, "**/*.pdf"), recursive=True))
    if not pdf_files:
        pdf_files = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))

    entities = []
    for i, filepath in enumerate(pdf_files, 1):
        filename = os.path.basename(filepath)
        print(f"[{i}/{len(pdf_files)}] {filename}")

        try:
            entity = extract_entities_from_pdf(filepath)
            entities.append(entity)
            print(f"  → {entity.court} {entity.case_id} / 법조문 {len(entity.cited_laws)}개 / 쟁점 {len(entity.issues)}개")
        except Exception as e:
            print(f"  → 실패: {e}")

    return entities


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    # 테스트: 1개만 추출
    import glob
    pdfs = sorted(glob.glob("docs/pdf/판례/*.pdf"))
    if pdfs:
        print(f"=== 테스트: {os.path.basename(pdfs[0])} ===\n")
        entity = extract_entities_from_pdf(pdfs[0])
        print(json.dumps(entity.model_dump(), ensure_ascii=False, indent=2))
