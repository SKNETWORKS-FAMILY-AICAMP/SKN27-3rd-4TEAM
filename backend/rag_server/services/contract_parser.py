"""Contract text extraction and lightweight field parsing."""

from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

import pdfplumber

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
    "잔금",
    "확정일자",
    "전입신고",
    "대항력",
    "우선변제권",
    "대리인",
    "위임",
    "인감",
    "소유자",
    "원상복구",
    "수리",
    "하자",
    "전세보증보험",
    "HUG",
    "SGI",
    "보증금",
    "특약",
    "반환",
    "신탁",
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
        return ContractInfo(
            lessor_name=self._extract_name(text, ["임대인", "집주인", "소유자"]),
            lessee_name=self._extract_name(text, ["임차인", "세입자"]),
            address=self._extract_address(text),
            deposit_amount=self._extract_money(text, ["보증금", "전세금", "임대차보증금"]),
            monthly_rent=self._extract_money(text, ["월세", "차임"]) or 0,
            contract_start=self._extract_period(text, "start"),
            contract_end=self._extract_period(text, "end"),
            special_terms=self._extract_special_terms(text),
            raw_text=text,
        )

    @staticmethod
    def _extract_name(text: str, labels: list[str]) -> str | None:
        for label in labels:
            patterns = [
                rf"{label}\s*(?:성명|이름)?\s*[:：]\s*([가-힣A-Za-z]{{2,20}})",
                rf"{label}\s*[\(（][^)）]*(?:성명|이름)[^)）]*[\)）]\s*([가-힣A-Za-z]{{2,20}})",
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1).strip()
        return None

    @staticmethod
    def _extract_address(text: str) -> str | None:
        patterns = [
            r"(?:소재지|주소|부동산의 표시)\s*[:：]\s*([^\n]{5,120})",
            r"((?:서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)[^\n]{5,120})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _extract_money(text: str, labels: list[str]) -> int | None:
        for label in labels:
            patterns = [
                rf"{label}\s*[:：]?\s*(?:금)?\s*([0-9,]+)\s*(?:원|만원)?",
                rf"{label}[^\n]{{0,20}}([0-9,]+)\s*(?:원|만원)",
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if not match:
                    continue
                raw_amount = (match.group(1) or "").replace(",", "").strip()
                if not raw_amount or not raw_amount.isdigit():
                    continue
                amount = int(raw_amount)
                suffix = match.group(0)
                if "만원" in suffix:
                    return amount
                return amount // 10000 if amount >= 1_000_000 else amount
        return None

    @staticmethod
    def _extract_period(text: str, which: str) -> str | None:
        pattern = (
            r"(\d{4})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})"
            r"(?:일)?\s*(?:부터|~|-|∼|부터\s*)\s*"
            r"(\d{4})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})"
        )
        match = re.search(pattern, text)
        if match:
            offset = 0 if which == "start" else 3
            y, m, d = match.group(1 + offset), match.group(2 + offset), match.group(3 + offset)
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"

        dates = re.findall(r"(\d{4})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})", text)
        if dates:
            y, m, d = dates[0] if which == "start" else dates[-1]
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        return None

    @staticmethod
    def _extract_special_terms(text: str) -> str | None:
        match = re.search(
            r"(?:특약사항|특약|기타사항)\s*[:：]?\s*([\s\S]{10,1500}?)(?=\n\s*(?:임대인|임차인|서명|날인|$))",
            text,
        )
        return match.group(1).strip() if match else None

    @classmethod
    def extract_risk_keywords(cls, text: str) -> list[str]:
        return list(dict.fromkeys(keyword for keyword in RISK_KEYWORDS if keyword.lower() in text.lower()))

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
