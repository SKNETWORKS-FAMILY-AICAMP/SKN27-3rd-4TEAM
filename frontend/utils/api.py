"""Streamlit 프론트에서 FastAPI 백엔드를 호출하는 공통 유틸."""

from __future__ import annotations

import os
from typing import Any

import requests


BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")


def upload_contract_file(filename: str, content: bytes, content_type: str | None) -> dict[str, Any]:
    """계약서 파일을 백엔드 업로드 API로 전송하고 추출 결과를 반환한다."""
    response = requests.post(
        f"{BACKEND_BASE_URL}/api/v1/contracts/upload",
        files={"file": (filename, content, content_type or "application/octet-stream")},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()
