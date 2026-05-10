"""External evidence search boundary for legal consultation.

Provider selection is controlled by environment variables so the graph code does
not change when the team swaps search APIs.

Supported providers:
- mock: no network, trusted public-source placeholders
- naver: Naver Search API, requires NAVER_CLIENT_ID/NAVER_CLIENT_SECRET
- serpapi: SerpAPI Google search, requires SERPAPI_API_KEY
- custom: generic GET endpoint, requires EXTERNAL_SEARCH_ENDPOINT
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from typing import Any

from common.schemas.legal_consultation import ExternalSource

DEFAULT_PROVIDER = os.getenv("EXTERNAL_SEARCH_PROVIDER", "mock").strip().lower()
DEFAULT_TIMEOUT = float(os.getenv("EXTERNAL_SEARCH_TIMEOUT", "10"))

TRUSTED_DOMAINS = [
    "law.go.kr",
    "molit.go.kr",
    "klac.or.kr",
    "hldcc.or.kr",
    "khug.or.kr",
    "gov.kr",
]

TRUSTED_SOURCE_HINTS = [
    "국가법령정보센터",
    "국토교통부",
    "대한법률구조공단",
    "주택임대차분쟁조정위원회",
    "HUG 주택도시보증공사",
]


def search_external_sources(query: str, question_type: str, max_results: int = 3) -> list[ExternalSource]:
    """Search trusted external evidence using the configured provider.

    If the provider is not configured or a network/API error occurs, this returns
    mock trusted-source placeholders. This keeps the LangGraph runnable in class
    demos while preserving a clean replacement point for real APIs.
    """
    provider = DEFAULT_PROVIDER
    try:
        if provider == "naver":
            results = _search_naver(query, question_type, max_results)
        elif provider == "serpapi":
            results = _search_serpapi(query, question_type, max_results)
        elif provider == "custom":
            results = _search_custom(query, question_type, max_results)
        else:
            results = []
    except Exception:
        results = []

    if not results:
        return _mock_sources(max_results)
    return _prioritize_trusted_sources(results)[:max_results]


def _search_naver(query: str, question_type: str, max_results: int) -> list[ExternalSource]:
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        return []

    params = urllib.parse.urlencode({"query": _external_query(query), "display": max(max_results, 5), "sort": "sim"})
    request = urllib.request.Request(f"https://openapi.naver.com/v1/search/webkr.json?{params}")
    request.add_header("X-Naver-Client-Id", client_id)
    request.add_header("X-Naver-Client-Secret", client_secret)
    payload = _read_json(request)

    sources: list[ExternalSource] = []
    for item in payload.get("items", []):
        title = _clean_html(item.get("title", ""))
        link = item.get("link")
        summary = _clean_html(item.get("description", ""))
        sources.append(ExternalSource(title=title or "외부 검색 결과", publisher=_publisher_from_url(link), url=link, summary=summary, source_type="naver_web_search"))
    return sources


def _search_serpapi(query: str, question_type: str, max_results: int) -> list[ExternalSource]:
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return []

    params = urllib.parse.urlencode({"engine": "google", "q": _external_query(query), "api_key": api_key, "num": max_results, "hl": "ko"})
    request = urllib.request.Request(f"https://serpapi.com/search.json?{params}")
    payload = _read_json(request)

    sources: list[ExternalSource] = []
    for item in payload.get("organic_results", [])[:max_results]:
        link = item.get("link")
        sources.append(ExternalSource(title=item.get("title") or "외부 검색 결과", publisher=_publisher_from_url(link), url=link, summary=item.get("snippet") or "", source_type="serpapi_google_search"))
    return sources


def _search_custom(query: str, question_type: str, max_results: int) -> list[ExternalSource]:
    endpoint = os.getenv("EXTERNAL_SEARCH_ENDPOINT")
    if not endpoint:
        return []

    separator = "&" if "?" in endpoint else "?"
    url = f"{endpoint}{separator}{urllib.parse.urlencode({'q': _external_query(query), 'question_type': question_type, 'limit': max_results})}"
    payload = _read_json(urllib.request.Request(url))
    items = payload.get("results") or payload.get("items") or []

    sources: list[ExternalSource] = []
    for item in items[:max_results]:
        link = item.get("url") or item.get("link")
        sources.append(ExternalSource(title=item.get("title") or "외부 검색 결과", publisher=item.get("publisher") or _publisher_from_url(link), url=link, summary=item.get("summary") or item.get("snippet") or item.get("description") or "", source_type="custom_search"))
    return sources


def _mock_sources(max_results: int) -> list[ExternalSource]:
    sources = [
        ExternalSource(
            title="주택임대차보호법 관련 법령 확인 필요",
            publisher="국가법령정보센터",
            url="https://www.law.go.kr",
            summary="주택임대차보호법의 대항력, 우선변제권, 보증금 반환 관련 조항 확인에 사용하는 공신력 자료입니다.",
            source_type="mock_external_fallback",
        ),
        ExternalSource(
            title="임대차 분쟁 상담 및 구조 안내 확인 필요",
            publisher="대한법률구조공단",
            url="https://www.klac.or.kr",
            summary="구체적인 분쟁 가능성이 있는 경우 무료 법률 상담 또는 구조 절차를 확인할 수 있는 기관 자료입니다.",
            source_type="mock_external_fallback",
        ),
        ExternalSource(
            title="주택임대차분쟁조정 제도 확인 필요",
            publisher="주택임대차분쟁조정위원회",
            url="https://www.hldcc.or.kr",
            summary="보증금 반환, 수선 의무, 계약 해지 등 임대차 분쟁 조정 절차를 확인할 수 있는 자료입니다.",
            source_type="mock_external_fallback",
        ),
    ]
    return sources[:max_results]


def _read_json(request: urllib.request.Request) -> dict[str, Any]:
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _external_query(query: str) -> str:
    base = re.sub(r"\s+", " ", query).strip()
    return f"전세계약 주택임대차보호법 판례 {base}"[:350]


def _prioritize_trusted_sources(sources: list[ExternalSource]) -> list[ExternalSource]:
    def score(source: ExternalSource) -> tuple[int, str]:
        url = source.url or ""
        trusted = 1 if any(domain in url for domain in TRUSTED_DOMAINS) else 0
        return (-trusted, source.title)

    return sorted(sources, key=score)


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return unescape(text).strip()


def _publisher_from_url(url: str | None) -> str | None:
    if not url:
        return None
    host = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    if "law.go.kr" in host:
        return "국가법령정보센터"
    if "molit.go.kr" in host:
        return "국토교통부"
    if "klac.or.kr" in host:
        return "대한법률구조공단"
    if "hldcc.or.kr" in host:
        return "주택임대차분쟁조정위원회"
    if "khug.or.kr" in host:
        return "HUG 주택도시보증공사"
    return host or None
