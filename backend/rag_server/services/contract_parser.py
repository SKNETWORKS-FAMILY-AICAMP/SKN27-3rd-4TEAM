"""
전세계약 위험 진단 에이전트 - 전세계약서 파서
임포트 경로: rag_server.services.contract_parser
"""

from __future__ import annotations
import re
import io
import pdfplumber
from rag_server.models.schemas import ContractInfo

RISK_KEYWORDS = [
    "전세가율", "시세", "매매가",
    "근저당", "가압류", "가처분", "저당권", "담보", "선순위", "후순위",
    "미등기", "무허가", "건축물대장",
    "현금", "계좌", "확정일자", "전입신고", "대항력", "임차권등기",
    "대리인", "위임", "인감", "소유자",
    "원상복구", "수리", "하자", "누수", "도배", "장판",
    "전세보증보험", "HUG", "SGI",
    "보증금", "계약금", "잔금",
]


class ContractParser:

    @classmethod
    def from_text(cls, text: str) -> ContractInfo:
        return cls()._parse(text)

    @classmethod
    def from_pdf_bytes(cls, pdf_bytes: bytes) -> ContractInfo:
        return cls.from_text(cls._extract_pdf_text(pdf_bytes))

    @staticmethod
    def _extract_pdf_text(pdf_bytes: bytes) -> str:
        parts = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
        except Exception as e:
            return f"[PDF 추출 오류: {e}]"
        return "\n".join(parts)

    def _parse(self, text: str) -> ContractInfo:
        return ContractInfo(
            lessor_name=self._extract_lessor(text),
            lessee_name=self._extract_lessee(text),
            address=self._extract_address(text),
            deposit_amount=self._extract_deposit(text),
            monthly_rent=self._extract_monthly_rent(text),
            contract_start=self._extract_date(text, "start"),
            contract_end=self._extract_date(text, "end"),
            special_terms=self._extract_special_terms(text),
            raw_text=text,
        )

    @staticmethod
    def _extract_lessor(text: str) -> str | None:
        for pat in [r"임\s*대\s*인[:\s]*([가-힣]{2,5})\b",
                    r"임대인\s*\(?\s*성\s*명\s*\)?\s*[:\s]+([가-힣]{2,5})"]:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        return None

    @staticmethod
    def _extract_lessee(text: str) -> str | None:
        for pat in [r"임\s*차\s*인[:\s]*([가-힣]{2,5})\b",
                    r"임차인\s*\(?\s*성\s*명\s*\)?\s*[:\s]+([가-힣]{2,5})"]:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        return None

    @staticmethod
    def _extract_address(text: str) -> str | None:
        for pat in [r"소\s*재\s*지[:\s]+([^\n]{5,80})",
                    r"임\s*대\s*목\s*적\s*물[:\s]+([^\n]{5,80})"]:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        return None

    @staticmethod
    def _extract_deposit(text: str) -> int | None:
        for pat in [r"보\s*증\s*금[:\s]*금?\s*([\d,]+)\s*원",
                    r"전세금[:\s]*금?\s*([\d,]+)\s*원"]:
            m = re.search(pat, text)
            if m:
                try:
                    amt = int(m.group(1).replace(",", ""))
                    return amt // 10000 if amt >= 10_000_000 else amt
                except ValueError:
                    continue
        return None

    @staticmethod
    def _extract_monthly_rent(text: str) -> int | None:
        for pat in [r"월\s*세[:\s]*금?\s*([\d,]+)\s*원",
                    r"차\s*임[:\s]*금?\s*([\d,]+)\s*원"]:
            m = re.search(pat, text)
            if m:
                try:
                    amt = int(m.group(1).replace(",", ""))
                    return amt // 10000 if amt >= 1_000_000 else amt
                except ValueError:
                    continue
        return 0

    @staticmethod
    def _extract_date(text: str, which: str) -> str | None:
        m = re.search(
            r"(\d{4})[.\s년]\s*(\d{1,2})[.\s월]\s*(\d{1,2})[.\s일]?\s*[~\-~]\s*"
            r"(\d{4})[.\s년]\s*(\d{1,2})[.\s월]\s*(\d{1,2})", text)
        if m:
            if which == "start":
                return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
            return f"{m.group(4)}-{m.group(5).zfill(2)}-{m.group(6).zfill(2)}"
        dates = re.findall(r"(\d{4})[.\s년]\s*(\d{1,2})[.\s월]\s*(\d{1,2})", text)
        if dates:
            y, mo, d = dates[0] if which == "start" else dates[-1]
            return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
        return None

    @staticmethod
    def _extract_special_terms(text: str) -> str | None:
        m = re.search(
            r"특\s*약\s*사\s*항[:\s]*([\s\S]{10,1000}?)(?=\n\n|\Z|서명|날인|임대인|임차인)",
            text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    @classmethod
    def extract_risk_keywords(cls, text: str) -> list[str]:
        return list(dict.fromkeys(kw for kw in RISK_KEYWORDS if kw in text))

    @classmethod
    def extract_summary_keywords(cls, info: ContractInfo) -> list[str]:
        kws = []
        if info.deposit_amount:
            kws.append(f"보증금 {info.deposit_amount}만원")
        if info.address:
            kws.extend(re.findall(r"[가-힣]{2,4}[동구]", info.address))
        if info.special_terms:
            kws.extend(cls.extract_risk_keywords(info.special_terms))
        kws.extend(["전세계약", "위험 진단", "임차인 보호"])
        return kws
