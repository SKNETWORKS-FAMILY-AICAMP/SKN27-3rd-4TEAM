"""계약서 업로드 문서의 텍스트와 핵심 필드를 추출하는 서비스."""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from dataclasses import dataclass
from html import unescape
from xml.etree import ElementTree

import pdfplumber


@dataclass
class ExtractedContract:
    """프론트가 바로 표시할 수 있는 계약서 추출 결과."""

    contract_id: str
    filename: str
    content_type: str | None
    extracted_text: str
    parsed_fields: dict[str, str | int | None]


class DocumentExtractor:
    """PDF/DOCX 계약서에서 텍스트와 기본 계약 정보를 추출한다."""

    MAX_FILE_SIZE = 10 * 1024 * 1024
    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

    @classmethod
    def extract(cls, filename: str, content: bytes, content_type: str | None = None) -> ExtractedContract:
        """파일 확장자에 맞는 추출기를 선택해 계약서 내용을 반환한다."""
        extension = cls._get_extension(filename)
        if extension not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError("PDF, DOCX, TXT 파일만 업로드할 수 있습니다.")
        if len(content) > cls.MAX_FILE_SIZE:
            raise ValueError("파일 크기는 10MB 이하여야 합니다.")

        if extension == ".pdf":
            text = cls._extract_pdf_text(content)
        elif extension == ".docx":
            text = cls._extract_docx_text(content)
        else:
            text = cls._extract_plain_text(content)

        cleaned_text = cls._normalize_text(text)
        return ExtractedContract(
            contract_id=str(uuid.uuid4()),
            filename=filename,
            content_type=content_type,
            extracted_text=cleaned_text,
            parsed_fields=cls._extract_fields(cleaned_text),
        )

    @staticmethod
    def _get_extension(filename: str) -> str:
        """파일명에서 소문자 확장자를 안전하게 분리한다."""
        lowered = filename.lower().strip()
        match = re.search(r"(\.[a-z0-9]+)$", lowered)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_pdf_text(content: bytes) -> str:
        """pdfplumber로 PDF 전체 페이지의 텍스트를 추출한다."""
        text_parts: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts)

    @staticmethod
    def _extract_docx_text(content: bytes) -> str:
        """DOCX 내부 XML을 직접 읽어 문단 텍스트를 추출한다."""
        with zipfile.ZipFile(io.BytesIO(content)) as docx:
            xml_bytes = docx.read("word/document.xml")

        root = ElementTree.fromstring(xml_bytes)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", namespace):
            chunks = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
            if chunks:
                paragraphs.append("".join(chunks))
        return "\n".join(paragraphs)

    @staticmethod
    def _extract_plain_text(content: bytes) -> str:
        """인코딩이 다른 TXT 파일도 최대한 읽을 수 있게 순차 디코딩한다."""
        for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

    @staticmethod
    def _normalize_text(text: str) -> str:
        """공백과 HTML 엔티티를 정리해 후속 분석에 쓰기 좋은 텍스트로 만든다."""
        unescaped = unescape(text)
        normalized_lines = [re.sub(r"\s+", " ", line).strip() for line in unescaped.splitlines()]
        return "\n".join(line for line in normalized_lines if line)

    @classmethod
    def _extract_fields(cls, text: str) -> dict[str, str | int | None]:
        """정규식 기반으로 1차 계약 핵심 정보를 추출한다."""
        return {
            "address": cls._first_match(
                text,
                [
                    r"(?:소재지|부동산의 표시|임대차 목적물)[:\s]*([^\n]{5,120})",
                    r"((?:서울|경기|인천|부산|대구|대전|광주|울산|세종|제주)[^\n]{5,120})",
                ],
            ),
            "deposit_amount": cls._extract_amount(text, ["보증금", "전세금", "임대차보증금"]),
            "monthly_rent": cls._extract_amount(text, ["월세", "차임"]),
            "contract_start": cls._extract_period(text, 0),
            "contract_end": cls._extract_period(text, 1),
            "special_terms": cls._extract_special_terms(text),
        }

    @staticmethod
    def _first_match(text: str, patterns: list[str]) -> str | None:
        """여러 후보 패턴 중 가장 먼저 잡히는 값을 반환한다."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _extract_amount(text: str, labels: list[str]) -> int | None:
        """금액 표현을 만원 단위 정수로 변환한다."""
        label_pattern = "|".join(re.escape(label) for label in labels)
        patterns = [
            rf"(?:{label_pattern})[:\s]*(?:금\s*)?([0-9,]+)\s*원",
            rf"(?:{label_pattern})[:\s]*(?:금\s*)?([0-9,]+)\s*만원",
            rf"(?:{label_pattern})[:\s]*(?:금\s*)?([0-9,]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            amount = int(match.group(1).replace(",", ""))
            if "만원" in match.group(0):
                return amount
            return amount // 10_000 if amount >= 10_000 else amount
        return None

    @staticmethod
    def _extract_period(text: str, index: int) -> str | None:
        """계약기간에서 시작일 또는 종료일을 ISO 형식으로 추출한다."""
        date_pattern = r"(\d{4})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})"
        dates = re.findall(date_pattern, text)
        if not dates:
            return None
        selected = dates[0] if index == 0 else dates[-1]
        return f"{selected[0]}-{selected[1].zfill(2)}-{selected[2].zfill(2)}"

    @staticmethod
    def _extract_special_terms(text: str) -> str | None:
        """특약사항 블록이 있으면 다음 큰 항목 전까지 잘라낸다."""
        match = re.search(r"(?:특약사항|특약)[:\s]*([\s\S]{10,1200}?)(?=\n(?:임대인|임차인|서명|날인|계약일)|$)", text)
        return match.group(1).strip() if match else None
