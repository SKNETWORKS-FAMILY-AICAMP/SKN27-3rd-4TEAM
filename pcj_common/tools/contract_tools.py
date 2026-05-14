"""
계약서 검토 에이전트용 @tool 모음

Tools:
  - parse_contract_document  : docx/pdf 파일을 읽어 구조화된 섹션 텍스트 반환
  - check_required_fields    : 추출된 JSON 에서 누락 필드 확인
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.tools import tool


@tool
def parse_contract_document(file_path: str) -> str:
    """
    계약서 파일(.docx 또는 .pdf)을 읽어 구조화된 섹션 텍스트를 반환합니다.
    docx는 테이블 구조를 분석하여 각 필드를 정확한 섹션에서 추출합니다.

    Args:
        file_path: 계약서 파일의 절대 경로 (.docx 또는 .pdf)
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in {".docx", ".pdf"}:
        return f"[오류] 지원하지 않는 파일 형식입니다: '{ext}'. .docx 또는 .pdf 파일을 사용하세요."

    if not path.exists():
        return f"[오류] 파일을 찾을 수 없습니다: {file_path}"

    try:
        if ext == ".docx":
            return _extract_structured_sections(path)
        else:
            return _read_pdf(path)
    except Exception as exc:
        return f"[오류] 파일 파싱 실패: {exc}"


def _get_unique_cells(row):
    cells = []
    seen = set()
    for cell in row.cells:
        t = cell.text.strip()
        if t not in seen:
            seen.add(t)
            cells.append(t)
    return cells


def _normalize_date(text):
    m = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', text)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    return text.strip()


def _extract_structured_sections(path):
    import docx

    doc = docx.Document(str(path))

    fields = {
        "landlord": None,
        "tenant": None,
        "address": None,
        "housing_type": None,
        "area": None,
        "deposit": None,
        "period": None,
        "special_terms": [],
    }

    for table in doc.tables:
        rows = [_get_unique_cells(row) for row in table.rows]

        for cells in rows:
            if not cells:
                continue
            c0 = cells[0]
            c1 = cells[1] if len(cells) > 1 else ""
            c2 = cells[2] if len(cells) > 2 else ""

            # 임대사업자 이름: TABLE 0 - 임대사업자 | 성명(법인명) | 오성호
            if c0 == "임대사업자" and "성명" in c1 and fields["landlord"] is None:
                val = c2.replace("(서명 또는 인)", "").strip()
                if val:
                    fields["landlord"] = val

            # 임차인 이름: TABLE 0 - 임차인 | 성명(법인명) | 최유진
            if c0 == "임차인" and "성명" in c1 and fields["tenant"] is None:
                val = c2.replace("(서명 또는 인)", "").strip()
                if val:
                    fields["tenant"] = val

            # 주택 소재지: TABLE 2 - 주택 소재지 | 서울특별시 종로구 ...
            if "주택 소재지" in c0 and c1 and fields["address"] is None:
                fields["address"] = c1.strip()

            # 주택 유형: TABLE 2 - 주택 유형 | 아파트[□] ... 다세대주택[■] ...
            if "주택 유형" in c0 and c1 and fields["housing_type"] is None:
                m = re.search(r'([가-힣]+)\[■\]', c1)
                if m:
                    fields["housing_type"] = m.group(1)

            # 전용면적: TABLE 2 - 민간임대주택면적(㎡) | 주거전용면적: 84.84 ㎡ | ...
            if "민간임대주택면적" in c0 and c1 and fields["area"] is None:
                m = re.search(r'주거전용면적[:\s]+(\d+\.?\d*)', c1)
                if m:
                    fields["area"] = float(m.group(1))

            # 전세금: TABLE 3 - 금액 | 금 사억원정 (₩400,000,000) | ...
            if c0 == "금액" and c1 and fields["deposit"] is None:
                m = re.search(r'₩([\d,]+)', c1)
                if m:
                    fields["deposit"] = int(m.group(1).replace(",", ""))

            # 임대 기간: TABLE 3 - 임대차계약기간 | 2025년 02월 25일 ∼ 2027년 02월 24일
            if "임대차계약기간" in c0 and c1 and fields["period"] is None:
                parts = re.split(r'[∼~]', c1)
                if len(parts) == 2:
                    fields["period"] = f"{_normalize_date(parts[0])} ~ {_normalize_date(parts[1])}"

            # 특약사항: TABLE 6 - 번호가 붙은 항목들
            for cell_text in cells:
                for line in cell_text.split("\n"):
                    m = re.match(r'^(\d+)[.]\s+(.+)', line.strip())
                    if m:
                        content = m.group(2).strip()
                        if content and content not in fields["special_terms"]:
                            fields["special_terms"].append(content)

    NOT_FOUND = "없음"
    lines = [
        "=== 계약서 구조화 정보 (코드 추출) ===",
        "",
        "[ 계약 당사자 ]",
        f"임대사업자(임대인) 이름 : {fields['landlord'] or NOT_FOUND}",
        f"임차인 이름             : {fields['tenant'] or NOT_FOUND}",
        "",
        "[ 임대 목적물 ]",
        f"주택 소재지 : {fields['address'] or NOT_FOUND}",
        f"주택 유형   : {fields['housing_type'] or NOT_FOUND}",
        f"전용면적    : {fields['area'] or NOT_FOUND}",
        "",
        "[ 계약 조건 ]",
        f"전세금(임대보증금) : {fields['deposit'] or NOT_FOUND}",
        f"임대 기간          : {fields['period'] or NOT_FOUND}",
        "",
        "[ 특약사항 ]",
    ]

    special = fields["special_terms"]
    if special:
        for i, term in enumerate(special, 1):
            lines.append(f"{i}. {term}")
    else:
        lines.append(NOT_FOUND)

    return "\n".join(lines)


def _read_pdf(path):
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(p for p in pages if p.strip())


REQUIRED_FIELDS = {
    "landlord":     "임대인",
    "tenant":       "임차인",
    "address":      "주소",
    "area":         "주택 면적",
    "housing_type": "주택 유형",
    "deposit":      "전세금",
    "period":       "계약 기간",
}

OPTIONAL_FIELDS = ["special_terms"]


@tool
def check_required_fields(extracted_json: str) -> str:
    """
    LLM이 계약서에서 추출한 데이터(JSON 문자열)를 받아
    필수 항목의 누락 여부를 확인하고 결과를 반환합니다.

    반환 형식:
      - 성공: {"status": "success", "data": {...}}
      - 실패: {"status": "fail", "missing_fields": [...], "message": "..."}

    Args:
        extracted_json: 추출된 계약 정보 JSON 문자열
                        필수 필드: landlord, tenant, address, area,
                                   housing_type, deposit, period
                        선택 필드: special_terms (특약사항 리스트, 없으면 빈 리스트)
    """
    try:
        data = json.loads(extracted_json)
    except json.JSONDecodeError as exc:
        return json.dumps({
            "status": "fail",
            "missing_fields": list(REQUIRED_FIELDS.values()),
            "message": f"JSON 파싱 실패: {exc}.",
        }, ensure_ascii=False)

    missing = [
        korean_name
        for field, korean_name in REQUIRED_FIELDS.items()
        if not data.get(field)
    ]

    if missing:
        return json.dumps({
            "status": "fail",
            "missing_fields": missing,
            "message": f"계약서에 다음 항목이 누락되어 있습니다: {', '.join(missing)}",
        }, ensure_ascii=False)

    return json.dumps({
        "status": "success",
        "data": data,
        "message": "계약서 데이터 추출이 완료되었습니다.",
    }, ensure_ascii=False)
