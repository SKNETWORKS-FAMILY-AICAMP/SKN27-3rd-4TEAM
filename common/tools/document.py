"""Compatibility wrapper for contract document parsing.

The diagnosis nodes import this module as their document boundary.  The actual
PDF/TXT extraction logic lives in ``pdf_contract.py``.
"""
from __future__ import annotations

from typing import Any

from common.tools.pdf_contract import detect_contract_sections, extract_contract_fields as _extract_contract_fields
from common.tools.pdf_contract import extract_pdf_text


def parse_contract_file(file_path: str | None) -> tuple[str, list[str], float | None]:
    """Parse a contract file into full text, page texts, and OCR confidence."""
    return extract_pdf_text(file_path)


def extract_contract_fields(text: str) -> dict[str, Any]:
    """Extract structured fields from already parsed contract text."""
    sections = detect_contract_sections(text)
    return _extract_contract_fields(text, sections)
