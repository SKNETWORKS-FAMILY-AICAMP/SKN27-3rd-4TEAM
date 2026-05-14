"""
전세계약 위험 진단 에이전트 - 전세계약서 파서
역할: 업로드된 계약서(PDF/텍스트)에서 핵심 정보 추출

추출 항목:
  - 임대인/임차인 이름
  - 물건지 주소
  - 보증금 · 월세
  - 계약기간 (시작일 ~ 종료일)
  - 특약사항 원문
  - 위험 키워드 탐지
"""

from __future__ import annotations
import re
import io
from pathlib import Path

import pdfplumber

from app.models.schemas import ContractInfo


# ── 위험 키워드 패턴 ─────────────────────────────────────

RISK_KEYWORDS = [
    # 전세가율
    "전세가율", "시세", "매매가",
    # 권리관계
    "근저당", "가압류", "가처분", "저당권", "담보", "선순위", "후순위",
    "미등기", "무허가", "건축물대장",
    # 절차
    "현금", "계좌", "확정일자", "전입신고", "대항력", "임차권등기",
    # 임대인 관련
    "대리인", "위임", "인감", "소유자",
    # 특약 위험
    "원상복구", "수리", "하자", "누수", "도배", "장판",
    "전세보증보험", "HUG", "SGI",
    # 보증금
    "보증금", "계약금", "잔금",
]


class ContractParser:
    """전세계약서 파싱 클래스"""

    # ── 공개 메서드 ──────────────────────────────────────

    @classmethod
    def from_text(cls, text: str) -> ContractInfo:
        """텍스트에서 계약서 정보 추출"""
        parser = cls()
        return parser._parse(text)

    @classmethod
    def from_pdf_bytes(cls, pdf_bytes: bytes) -> ContractInfo:
        """PDF 바이트에서 텍스트 추출 후 파싱"""
        text = cls._extract_pdf_text(pdf_bytes)
        return cls.from_text(text)

    @classmethod
    def from_pdf_path(cls, path: str) -> ContractInfo:
        """PDF 파일 경로에서 파싱"""
        with open(path, "rb") as f:
            return cls.from_pdf_bytes(f.read())

    # ── PDF 텍스트 추출 ──────────────────────────────────

    @staticmethod
    def _extract_pdf_text(pdf_bytes: bytes) -> str:
        """pdfplumber로 PDF 전체 텍스트 추출"""
        text_parts = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)
        except Exception as e:
            return f"[PDF 추출 오류: {e}]"
        return "\n".join(text_parts)

    # ── 파싱 핵심 로직 ────────────────────────────────────

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

    # ── 개별 필드 추출 ────────────────────────────────────

    @staticmethod
    def _extract_lessor(text: str) -> str | None:
        """임대인 이름 추출"""
        patterns = [
            r"임\s*대\s*인[:\s]*([가-힣]{2,5})\b",
            r"임대인\s*\(?\s*성\s*명\s*\)?\s*[:\s]+([가-힣]{2,5})",
            r"임\s*대\s*인\s+성명[:\s]+([가-힣]{2,5})",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        return None

    @staticmethod
    def _extract_lessee(text: str) -> str | None:
        """임차인 이름 추출"""
        patterns = [
            r"임\s*차\s*인[:\s]*([가-힣]{2,5})\b",
            r"임차인\s*\(?\s*성\s*명\s*\)?\s*[:\s]+([가-힣]{2,5})",
            r"임\s*차\s*인\s+성명[:\s]+([가-힣]{2,5})",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        return None

    @staticmethod
    def _extract_address(text: str) -> str | None:
        """물건지 주소 추출"""
        patterns = [
            r"소\s*재\s*지[:\s]+([^\n]{5,80})",
            r"임\s*대\s*목\s*적\s*물[:\s]+([^\n]{5,80})",
            r"부\s*동\s*산\s*의\s*표\s*시[:\s]+([^\n]{5,80})",
            r"[가-힣]+(?:시|도)\s+[가-힣]+(?:구|군|시)\s+[가-힣0-9\s\-]+(?:동|로|길|번지|호)[^\n]{0,30}",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1 if "group" in dir(m) and m.lastindex else 0).strip()
        return None

    @staticmethod
    def _extract_deposit(text: str) -> int | None:
        """보증금 추출 (만원 단위)"""
        patterns = [
            r"보\s*증\s*금[:\s]*금?\s*([\d,]+)\s*원",
            r"보증금\s*:\s*금\s*([\d,]+)\s*원",
            r"전세금[:\s]*금?\s*([\d,]+)\s*원",
            r"보\s*증\s*금.*?([0-9,]{3,})\s*만?\s*원",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                raw = (m.group(1) or "").replace(",", "").strip()
                if not raw or not raw.isdigit():
                    continue
                try:
                    amount = int(raw)
                    # 원 단위면 만원으로 변환
                    if amount >= 10_000_000:
                        amount //= 10000
                    return amount
                except ValueError:
                    continue
        return None

    @staticmethod
    def _extract_monthly_rent(text: str) -> int | None:
        """월세 추출 (만원 단위). 순전세면 0"""
        patterns = [
            r"월\s*세[:\s]*금?\s*([\d,]+)\s*원",
            r"차\s*임[:\s]*금?\s*([\d,]+)\s*원",
            r"월\s*차\s*임[:\s]*([\d,]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                raw = (m.group(1) or "").replace(",", "").strip()
                if not raw or not raw.isdigit():
                    continue
                try:
                    amount = int(raw)
                    if amount >= 1_000_000:
                        amount //= 10000
                    return amount
                except ValueError:
                    continue
        return 0  # 순전세

    @staticmethod
    def _extract_date(text: str, which: str) -> str | None:
        """계약 시작/종료일 추출"""
        # 일반: 20XX년 XX월 XX일 ~ 20XX년 XX월 XX일
        period_pattern = r"(\d{4})[.\s년]\s*(\d{1,2})[.\s월]\s*(\d{1,2})[.\s일]?\s*[~\-~]\s*(\d{4})[.\s년]\s*(\d{1,2})[.\s월]\s*(\d{1,2})"
        m = re.search(period_pattern, text)
        if m:
            if which == "start":
                return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
            else:
                return f"{m.group(4)}-{m.group(5).zfill(2)}-{m.group(6).zfill(2)}"

        # 단일 날짜
        single = r"(\d{4})[.\s년]\s*(\d{1,2})[.\s월]\s*(\d{1,2})"
        dates = re.findall(single, text)
        if dates:
            y, m_, d = dates[0] if which == "start" else dates[-1]
            return f"{y}-{m_.zfill(2)}-{d.zfill(2)}"
        return None

    @staticmethod
    def _extract_special_terms(text: str) -> str | None:
        """특약사항 원문 추출"""
        patterns = [
            r"특\s*약\s*사\s*항[:\s]*([\s\S]{10,1000}?)(?=\n\n|\Z|서명|날인|임대인|임차인)",
            r"특\s*약[:\s]*([\s\S]{10,800}?)(?=\n\n|\Z)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    # ── 키워드 추출 ──────────────────────────────────────

    @classmethod
    def extract_risk_keywords(cls, text: str) -> list[str]:
        """
        계약서 텍스트에서 위험 관련 키워드 추출.
        Neo4j 그래프 검색과 RAG 쿼리에 활용.
        """
        found = []
        for kw in RISK_KEYWORDS:
            if kw in text:
                found.append(kw)
        return list(dict.fromkeys(found))  # 순서 유지 + 중복 제거

    @classmethod
    def extract_summary_keywords(cls, info: ContractInfo) -> list[str]:
        """
        ContractInfo에서 주요 키워드 추출 (벡터 검색 쿼리용).
        """
        keywords = []
        if info.deposit_amount:
            keywords.append(f"보증금 {info.deposit_amount}만원")
        if info.address:
            # 동·구 단위 추출
            dong = re.findall(r"[가-힣]{2,4}[동구]", info.address)
            keywords.extend(dong)
        if info.special_terms:
            kws = cls.extract_risk_keywords(info.special_terms)
            keywords.extend(kws)
        keywords.extend(["전세계약", "위험 진단", "임차인 보호"])
        return keywords
