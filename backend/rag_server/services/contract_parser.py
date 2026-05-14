"""Contract text extraction and deterministic field parsing."""

from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

try:
    import pdfplumber
except ModuleNotFoundError:  # pragma: no cover - DOCX parsing does not need pdfplumber
    pdfplumber = None

from rag_server.models.schemas import ContractInfo


RISK_KEYWORDS = [
    "전세가율",
    "시세",
    "매매가",
    "근저당",
    "가압류",
    "압류",
    "담보",
    "선순위",
    "후순위",
    "미등기",
    "무허가",
    "위반건축물",
    "계약금",
    "보증금",
    "월임대료",
    "월세",
    "확정일자",
    "전입신고",
    "대항력",
    "우선변제권",
    "대리인",
    "위임",
    "신탁",
    "소유자",
    "원상복구",
    "수리",
    "이자",
    "전세보증보험",
    "임대보증금보증",
    "HUG",
    "SGI",
    "특약",
    "반환",
]


class ContractParser:
    @classmethod
    def from_text(cls, text: str) -> ContractInfo:
        return cls()._parse(text)

    @classmethod
    def from_pdf_bytes(cls, pdf_bytes: bytes) -> ContractInfo:
        return cls.from_text(cls.extract_pdf_text(pdf_bytes))

    @classmethod
    def from_docx_bytes(cls, docx_bytes: bytes) -> ContractInfo:
        return cls.from_text(cls.extract_docx_text(docx_bytes))

    @staticmethod
    def extract_pdf_text(pdf_bytes: bytes) -> str:
        parts: list[str] = []
        if pdfplumber is None:
            return "[PDF extraction error: pdfplumber is not installed]"
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
        except Exception as exc:
            return f"[PDF extraction error: {exc}]"
        return "\n".join(parts).strip()

    @staticmethod
    def extract_docx_text(docx_bytes: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
                xml_bytes = archive.read("word/document.xml")
            root = ET.fromstring(xml_bytes)
        except Exception as exc:
            return f"[DOCX extraction error: {exc}]"

        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        lines: list[str] = []
        for para in root.findall(".//w:p", ns):
            text = "".join(node.text or "" for node in para.findall(".//w:t", ns)).strip()
            if text:
                lines.append(text)
        return "\n".join(lines)

    def _parse(self, text: str) -> ContractInfo:
        lines = _lines(text)
        info = ContractInfo(
            lessor_name=_party_name(lines, "임대사업자") or _party_name(lines, "임대인"),
            lessee_name=_party_name(lines, "임차인"),
            address=_property_address(lines, text),
            housing_type=_housing_type(lines),
            area_m2=_area_m2(text),
            deposit_amount=_deposit_amount(lines, text),
            monthly_rent=_monthly_rent(lines, text),
            contract_start=None,
            contract_end=None,
            special_terms=_special_terms(text),
            raw_text=text,
        )
        start, end = _contract_period(lines, text)
        info.contract_start = start
        info.contract_end = end
        return info

    @classmethod
    def extract_risk_keywords(cls, text: str) -> list[str]:
        lowered = text.lower()
        return list(dict.fromkeys(keyword for keyword in RISK_KEYWORDS if keyword.lower() in lowered))

    @classmethod
    def extract_summary_keywords(cls, info: ContractInfo) -> list[str]:
        keywords: list[str] = ["전세계약", "위험 진단", "임차인 보호"]
        if info.deposit_amount:
            keywords.append(f"보증금 {info.deposit_amount}만원")
        if info.address:
            keywords.extend(re.findall(r"[가-힣]{2,8}(?:동|구|시|군)", info.address))
        if info.special_terms:
            keywords.extend(cls.extract_risk_keywords(info.special_terms))
        return list(dict.fromkeys(keywords))


def _lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _next_value(lines: list[str], label: str, window: int = 4) -> str | None:
    for index, line in enumerate(lines):
        if label == line or label in line:
            for value in lines[index + 1:index + 1 + window]:
                if value and not _looks_like_label(value):
                    return value
    return None


def _party_name(lines: list[str], role: str) -> str | None:
    for index, line in enumerate(lines):
        if line != role:
            continue
        for offset in range(index + 1, min(index + 10, len(lines) - 1)):
            if "성명" in lines[offset]:
                candidate = _strip_signature(lines[offset + 1])
                if _looks_like_name(candidate):
                    return candidate
        for value in lines[index + 1:index + 6]:
            candidate = _strip_signature(value)
            if _looks_like_name(candidate):
                return candidate
    return None


def _strip_signature(value: str) -> str:
    return re.sub(r"\(?서명.*", "", value).strip()


def _looks_like_name(value: str) -> bool:
    return bool(re.fullmatch(r"[가-힣A-Za-z]{2,20}", value or ""))


def _looks_like_label(value: str) -> bool:
    labels = {
        "성명",
        "성명(법인명)",
        "주소",
        "주택 유형",
        "구분",
        "금액",
        "월임대료",
        "임대보증금",
        "임대차계약기간",
    }
    return value in labels or value.endswith("여부")


def _property_address(lines: list[str], text: str) -> str | None:
    for index, line in enumerate(lines):
        if "주택 소재지" not in line:
            continue
        for value in lines[index + 1:index + 6]:
            if _looks_like_label(value):
                continue
            if _looks_like_property_address(value):
                return value
            if any(stop in value for stop in ("주택[", "아파트[", "연립주택[", "다가구주택[")):
                return None
    return _address_from_property_section(text)


def _address_from_property_section(text: str) -> str | None:
    match = re.search(
        r"주택\s*소재지\s*\n\s*((?:서울특별시|경기도|인천광역시|부산광역시|대구광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|제주특별자치도)[^\n]{5,120})",
        text,
    )
    if not match:
        return None
    candidate = match.group(1).strip()
    return candidate if _looks_like_property_address(candidate) else None


def _looks_like_property_address(value: str | None) -> bool:
    if not value:
        return False
    if "[" in value or "]" in value:
        return False
    if not re.search(r"(서울특별시|경기도|인천광역시|부산광역시|대구광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|제주특별자치도)", value):
        return False
    if not re.search(r"(구|군|시)\s*[가-힣0-9]", value):
        return False
    return bool(re.search(r"(동|읍|면|리|가)\s*[0-9]", value) or re.search(r"제?\s*\d+\s*호", value))


def _housing_type(lines: list[str]) -> str | None:
    value = _next_value(lines, "주택 유형")
    if not value:
        return None
    checked = re.search(r"([가-힣]+주택|아파트)\s*\[■\]", value)
    if checked:
        return checked.group(1)
    return value


def _area_m2(text: str) -> float | None:
    match = re.search(r"주거전용면적\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*㎡", text)
    if match:
        return float(match.group(1))
    match = re.search(r"전용면적[^\d]{0,20}([0-9]+(?:\.[0-9]+)?)\s*㎡", text)
    return float(match.group(1)) if match else None


def _won_to_manwon(raw: str) -> int:
    amount = int(raw.replace(",", ""))
    return amount // 10_000 if amount >= 10_000 else amount


def _deposit_amount(lines: list[str], text: str) -> int | None:
    for index, line in enumerate(lines):
        if line == "임대보증금" or "임대보증금, 월임대료" in line:
            window = "\n".join(lines[index:index + 12])
            match = re.search(r"₩\s*([0-9,]+)", window)
            if match:
                return _won_to_manwon(match.group(1))

    patterns = [
        r"임대보증금[^\n₩]{0,80}₩\s*([0-9,]+)",
        r"보증금[^\n₩]{0,80}₩\s*([0-9,]+)",
        r"전세금[^\n₩]{0,80}₩\s*([0-9,]+)",
        r"임대보증금[^\n0-9]{0,30}([0-9,]+)\s*원",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            return _won_to_manwon(match.group(1))
    return None


def _monthly_rent(lines: list[str], text: str) -> int:
    for index, line in enumerate(lines):
        if line == "월임대료":
            window = "\n".join(lines[index:index + 8])
            matches = re.findall(r"₩\s*([0-9,]+)", window)
            if matches:
                return _won_to_manwon(matches[-1])
    match = re.search(r"월(?:임대료|세)[^\n₩]{0,80}₩\s*([0-9,]+)", text, re.S)
    return _won_to_manwon(match.group(1)) if match else 0


def _contract_period(lines: list[str], text: str) -> tuple[str | None, str | None]:
    for index, line in enumerate(lines):
        if "임대차계약기간" in line:
            window = " ".join(lines[index:index + 8])
            dates = _dates(window)
            if len(dates) >= 2:
                return dates[0], dates[1]
    return None, None


def _dates(text: str) -> list[str]:
    values = []
    for year, month, day in re.findall(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", text):
        values.append(f"{year}-{month.zfill(2)}-{day.zfill(2)}")
    for year, month, day in re.findall(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text):
        values.append(f"{year}-{month.zfill(2)}-{day.zfill(2)}")
    return values


def _special_terms(text: str) -> str | None:
    marker = re.search(r"【\s*특약사항\s*】|\[\s*특약사항\s*\]|특약사항", text)
    if marker:
        tail = text[marker.end():]
        end = re.search(r"\n\s*(?:\d+\.\s*개인정보|개인정보|임대인|임차인|서명|날인)", tail)
        value = tail[: end.start()].strip() if end else tail[:1800].strip()
        return value or None

    match = re.search(
        r"(?:제17조\(특약\))\s*[:\n]?\s*"
        r"([\s\S]{10,1800}?)(?=\n\s*(?:\d+\.\s*개인정보|개인정보|임대인|임차인|서명|날인|$))",
        text,
    )
    return match.group(1).strip() if match else None
