"""PDF-first contract processing tools.

These tools only prepare trustworthy contract text/fields. Risk judgement is
kept in downstream agents so the graph can route by extracted state.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from common.schemas.diagnosis import ContractSections, FieldValidationResult, PdfValidationResult
from common.tools.llm import extract_json_object, ollama_generate

MOCK_CONTRACT_TEXT = """
전세계약서
임대인 홍길동 임차인 김철수
소재지 서울특별시 종로구 청운동 12-3
보증금 금 200,000,000원 월세 0원
계약기간 2025.03.01부터 2027.03.01까지
주택유형 연립다세대 전용면적 52.3㎡
특약사항
1. 임차인은 시설물 수리비를 전액 부담한다.
2. 임대인은 잔금일 다음날까지 근저당권 등 권리변동을 하지 않는다.
""".strip()

REQUIRED_FIELDS = ["landlord", "tenant", "address", "deposit_amount", "contract_start", "contract_end"]


def validate_pdf(file_path: str | None, *, max_size_mb: int = 30) -> PdfValidationResult:
    if not file_path:
        return PdfValidationResult(
            valid=True,
            file_path=None,
            extension=None,
            warnings=["contract_file missing; mock contract will be used"],
        )

    path = Path(file_path)
    errors: list[str] = []
    warnings: list[str] = []
    suffix = path.suffix.lower()
    if not path.exists():
        errors.append(f"file not found: {file_path}")
    if suffix not in {".pdf", ".txt", ".md", ".png", ".jpg", ".jpeg"}:
        errors.append(f"unsupported contract file extension: {suffix}")

    size = path.stat().st_size if path.exists() else None
    if size and size > max_size_mb * 1024 * 1024:
        errors.append(f"file too large: {size} bytes")

    page_count = _count_pdf_pages(path) if path.exists() and suffix == ".pdf" else None
    if suffix == ".pdf" and page_count == 0:
        warnings.append("pdf page count could not be detected")

    return PdfValidationResult(
        valid=not errors,
        file_path=str(path) if path.exists() else file_path,
        extension=suffix or None,
        file_size_bytes=size,
        page_count=page_count,
        errors=errors,
        warnings=warnings,
    )


def extract_pdf_text(file_path: str | None) -> tuple[str, list[str], float | None]:
    if not file_path:
        return MOCK_CONTRACT_TEXT, [MOCK_CONTRACT_TEXT], None

    path = Path(file_path)
    if not path.exists():
        return MOCK_CONTRACT_TEXT, [MOCK_CONTRACT_TEXT], None

    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return text, [text], None
    if suffix == ".pdf":
        text, pages = _extract_pdf_with_pypdf(path)
        if _looks_readable_korean(text):
            return text, pages, None
        text, pages = _extract_pdf_with_pymupdf(path)
        if text:
            return text, pages, None
    return MOCK_CONTRACT_TEXT, [MOCK_CONTRACT_TEXT], None


def ocr_pdf(file_path: str | None) -> tuple[str, list[str], float | None]:
    """Best-effort OCR placeholder.

    The project has no OCR engine pinned yet. This returns extracted text when
    possible and low confidence otherwise, leaving a clear replacement point.
    """
    text, pages, _ = extract_pdf_text(file_path)
    confidence = 0.55 if text and text != MOCK_CONTRACT_TEXT else 0.0
    return text, pages, confidence


def detect_contract_sections(text: str) -> ContractSections:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)
    special_start = _find_line_index(lines, ["특약", "특약사항", "특별약정"])
    special_terms_text = "\n".join(lines[special_start + 1:]) if special_start is not None else ""
    before_special = "\n".join(lines[:special_start]) if special_start is not None else joined
    return ContractSections(
        full_text=joined,
        parties_text=_matching_lines(before_special, ["임대인", "임차인", "대리인"]),
        property_text=_matching_lines(before_special, ["소재지", "주소", "주택유형", "전용면적"]),
        payment_text=_matching_lines(before_special, ["보증금", "월세", "차임", "계약금", "잔금"]),
        period_text=_matching_lines(before_special, ["계약기간", "부터", "까지"]),
        special_terms_text=special_terms_text,
    )


def extract_contract_fields(text: str, sections: ContractSections | None = None) -> dict[str, Any]:
    try:
        fields = _extract_with_llm(text)
        fields["extraction_method"] = "ollama"
    except Exception:
        fields = _extract_with_regex(text)
        fields["extraction_method"] = "regex_fallback"
    if sections:
        fields["special_terms"] = fields.get("special_terms") or _extract_special_terms(sections.special_terms_text)
    return fields


def validate_contract_fields(fields: dict[str, Any]) -> FieldValidationResult:
    missing = [name for name in REQUIRED_FIELDS if fields.get(name) in (None, "", [])]
    warnings: list[str] = []
    if not fields.get("special_terms"):
        warnings.append("special_terms missing or empty")
    if not fields.get("housing_type"):
        warnings.append("housing_type missing")
    if not fields.get("exclusive_area_m2"):
        warnings.append("exclusive_area_m2 missing")
    return FieldValidationResult(valid=not missing, missing_fields=missing, warnings=warnings)


def _count_pdf_pages(path: Path) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def _extract_pdf_with_pypdf(path: Path) -> tuple[str, list[str]]:
    try:
        from pypdf import PdfReader

        pages = [(page.extract_text() or "").strip() for page in PdfReader(str(path)).pages]
        return "\n\n".join(page for page in pages if page), pages
    except Exception:
        return "", []


def _extract_pdf_with_pymupdf(path: Path) -> tuple[str, list[str]]:
    try:
        import fitz

        document = fitz.open(str(path))
        pages = [page.get_text("text").strip() for page in document]
        document.close()
        return "\n\n".join(page for page in pages if page), pages
    except Exception:
        return "", []


def _extract_with_llm(text: str) -> dict[str, Any]:
    prompt = f"""
다음 전세계약서 텍스트에서 JSON 객체만 추출해.
숫자는 만원 단위 정수로 정규화해.
필드: landlord, tenant, address, dong_name, deposit_amount, monthly_rent,
contract_start, contract_end, housing_type, exclusive_area_m2, special_terms

계약서:
{text[:6000]}
""".strip()
    data = extract_json_object(
        ollama_generate(
            prompt,
            system="너는 한국 전세계약서 정보추출기다. JSON만 반환한다.",
            temperature=0.0,
        )
    )
    if not isinstance(data, dict):
        raise ValueError("contract extraction returned non-object")
    return data


def _extract_with_regex(text: str) -> dict[str, Any]:
    normalized = re.sub(r"[ \t]+", " ", text)
    address = _first_match(normalized, [r"소재지\s*([^\n]+)", r"주소\s*([^\n]+)"])
    area_raw = _first_match(normalized, [r"전용면적\s*([0-9.]+)\s*(?:㎡|m2)", r"면적\s*([0-9.]+)\s*(?:㎡|m2)"])
    housing_type = _first_match(normalized, [r"(연립다세대|오피스텔|단독다가구|단독|다가구|아파트)"])
    return {
        "landlord": _first_match(normalized, [r"임대인\s*([가-힣A-Za-z]{2,20})"]),
        "tenant": _first_match(normalized, [r"임차인\s*([가-힣A-Za-z]{2,20})"]),
        "address": address,
        "dong_name": _extract_dong(address or normalized),
        "deposit_amount": _money_to_manwon(_first_match(normalized, [r"보증금\s*(?:금)?\s*([0-9,]+)\s*원", r"보증금\s*([0-9,]+)\s*만원"])),
        "monthly_rent": _money_to_manwon(_first_match(normalized, [r"월세\s*(?:금)?\s*([0-9,]+)\s*원", r"월세\s*([0-9,]+)\s*만원"])),
        "contract_start": _first_match(normalized, [r"([0-9]{4}[.\-/][0-9]{1,2}[.\-/][0-9]{1,2})\s*부터"]),
        "contract_end": _first_match(normalized, [r"부터\s*([0-9]{4}[.\-/][0-9]{1,2}[.\-/][0-9]{1,2})\s*까지"]),
        "housing_type": _normalize_housing_type(housing_type),
        "exclusive_area_m2": float(area_raw) if area_raw else None,
        "special_terms": _extract_special_terms(text),
    }


def _looks_readable_korean(text: str) -> bool:
    if not text.strip():
        return False
    korean_chars = len(re.findall(r"[가-힣]", text))
    replacement_chars = text.count("?") + text.count("�")
    return korean_chars >= 10 and replacement_chars < max(10, len(text) * 0.1)


def _find_line_index(lines: list[str], needles: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if any(needle in line for needle in needles):
            return index
    return None


def _matching_lines(text: str, needles: list[str]) -> str:
    return "\n".join(line for line in text.splitlines() if any(needle in line for needle in needles))


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


def _money_to_manwon(value: str | None) -> int | None:
    if not value:
        return None
    number = int(value.replace(",", ""))
    return number // 10000 if number > 100000 else number


def _extract_dong(text: str) -> str | None:
    match = re.search(r"([가-힣0-9]+동)", text)
    return match.group(1) if match else None


def _normalize_housing_type(value: str | None) -> str | None:
    if not value:
        return None
    return "단독다가구" if value in {"단독", "다가구", "단독다가구"} else value


def _extract_special_terms(text: str) -> list[str]:
    if not text:
        marker = re.search(r"특약(?:사항)?", text)
        if not marker:
            return []
    tail = text
    marker = re.search(r"특약(?:사항)?", text)
    if marker:
        tail = text[marker.end():]
    lines = [line.strip(" -\t") for line in tail.splitlines()]
    return [line for line in lines if line and len(line) > 4][:30]


@tool
def validate_pdf_tool(file_path: str | None = None) -> PdfValidationResult:
    """Validate a contract PDF/TXT file before parsing."""
    return validate_pdf(file_path)


@tool
def extract_pdf_text_tool(file_path: str | None = None) -> tuple[str, list[str], float | None]:
    """Extract text from a contract PDF/TXT file."""
    return extract_pdf_text(file_path)


@tool
def ocr_pdf_tool(file_path: str | None = None) -> tuple[str, list[str], float | None]:
    """OCR fallback for scanned PDFs. Currently a replaceable best-effort stub."""
    return ocr_pdf(file_path)


@tool
def detect_contract_sections_tool(text: str) -> ContractSections:
    """Detect coarse contract sections from extracted text."""
    return detect_contract_sections(text)


@tool
def extract_contract_fields_tool(text: str) -> dict[str, Any]:
    """Extract structured contract fields from contract text."""
    return extract_contract_fields(text)


@tool
def validate_contract_fields_tool(fields: dict[str, Any]) -> FieldValidationResult:
    """Validate required contract fields after extraction."""
    return validate_contract_fields(fields)
