# rag/jm/legal/tools.py
# 법률 상담 에이전트에서 사용할 RAG 검색 도구와 답변 검토 도구를 정의합니다.

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from .search import LegalSearchHit, search_legal_documents


def _hit_to_dict(hit: LegalSearchHit) -> dict[str, Any]:
    """법률 검색 결과를 JSON으로 출력하기 쉬운 딕셔너리로 변환합니다."""

    return {
        "score": hit.score,
        "source": hit.metadata.get("source"),
        "file_name": hit.metadata.get("file_name"),
        "page": hit.metadata.get("page"),
        "content": hit.content,
    }


def _hits_to_json(hits: list[LegalSearchHit]) -> str:
    """법률 검색 결과 목록을 한글이 깨지지 않는 JSON 문자열로 변환합니다."""

    payload = [_hit_to_dict(hit) for hit in hits]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _filter_hits_by_file_keywords(
    hits: list[LegalSearchHit],
    keywords: tuple[str, ...],
) -> list[LegalSearchHit]:
    """검색 결과 중 파일명이나 출처에 특정 키워드가 들어간 결과만 남깁니다."""

    filtered: list[LegalSearchHit] = []
    for hit in hits:
        source_text = f"{hit.metadata.get('source', '')} {hit.metadata.get('file_name', '')}"
        if any(keyword in source_text for keyword in keywords):
            filtered.append(hit)
    return filtered


def _exclude_hits_by_file_keywords(
    hits: list[LegalSearchHit],
    keywords: tuple[str, ...],
) -> list[LegalSearchHit]:
    """검색 결과 중 파일명이나 출처에 제외 키워드가 들어간 결과를 제거합니다."""

    filtered: list[LegalSearchHit] = []
    for hit in hits:
        source_text = f"{hit.metadata.get('source', '')} {hit.metadata.get('file_name', '')}"
        if not any(keyword in source_text for keyword in keywords):
            filtered.append(hit)
    return filtered


@tool
def legal_document_search_tool(query: str, k: int = 5) -> str:
    """법령, 판례, 표준계약서, 절차 문서를 모두 대상으로 RAG 근거를 검색합니다."""

    hits = search_legal_documents(query=query, k=k, scope="all")
    return _hits_to_json(hits)


@tool
def law_article_search_tool(query: str, k: int = 5) -> str:
    """법률, 시행령, 민법, 특별법 같은 법령 조항 중심으로 근거를 검색합니다."""

    expanded_query = f"{query}\n법 조항 법령 주택임대차보호법 민법 특별법 시행령"
    hits = search_legal_documents(query=expanded_query, k=max(k * 2, 8), scope="law")
    law_hits = _filter_hits_by_file_keywords(
        hits,
        ("법률", "시행령", "민법", "주택임대차보호법", "특별법"),
    )
    law_hits = _exclude_hits_by_file_keywords(law_hits, ("사례집", "표준계약서"))
    return _hits_to_json(law_hits[:k] if law_hits else hits[:k])


@tool
def judgement_search_tool(query: str, k: int = 5) -> str:
    """판례 문서만 대상으로 RAG 근거를 검색합니다."""

    expanded_query = f"{query}\n판례 대법원 지방법원 고등법원 판결 결정"
    hits = search_legal_documents(query=expanded_query, k=k, scope="judgement")
    return _hits_to_json(hits)


@tool
def standard_contract_search_tool(query: str, k: int = 5) -> str:
    """주택임대차표준계약서 문서만 대상으로 RAG 근거를 검색합니다."""

    expanded_query = f"{query}\n주택임대차표준계약서 표준계약서 계약서 임대차계약"
    hits = search_legal_documents(query=expanded_query, k=max(k * 2, 8), scope="standard_contract")
    contract_hits = _filter_hits_by_file_keywords(hits, ("표준계약서", "주택임대차표준계약서"))
    return _hits_to_json(contract_hits[:k] if contract_hits else hits[:k])


@tool
def legal_procedure_search_tool(query: str, k: int = 5) -> str:
    """임차권등기명령, 전세피해 신청 같은 법률 절차 중심 근거를 검색합니다."""

    expanded_query = f"{query}\n절차 신청 명령 등기 구제 지원 상담 피해자 결정"
    hits = search_legal_documents(query=expanded_query, k=k, scope="all")
    procedure_hits = _filter_hits_by_file_keywords(hits, ("상담사례집", "특별법", "주택임대차보호법"))
    return _hits_to_json(procedure_hits[:k] if procedure_hits else hits[:k])


@tool
def legal_answer_review_tool(answer: str, evidence_json: str) -> str:
    """법률 답변 초안이 근거와 주의 문구를 갖췄는지 검토합니다."""

    try:
        evidence = json.loads(evidence_json)
    except json.JSONDecodeError:
        evidence = []

    issues: list[str] = []
    if not evidence:
        issues.append("검색 근거가 없습니다.")
    if len(answer.strip()) < 80:
        issues.append("답변이 너무 짧아 법률 근거 설명이 부족합니다.")
    if not any(keyword in answer for keyword in ("근거", "법", "조항", "판례", "계약서", "확인", "절차")):
        issues.append("답변에 법률 근거나 확인 사항이 충분히 드러나지 않습니다.")
    if not any(keyword in answer for keyword in ("변호사", "법률 상담", "공공", "확인")):
        issues.append("최종 법률 판단은 전문가에게 확인해야 한다는 안내가 부족합니다.")

    payload = {
        "passed": not issues,
        "message": "PASS" if not issues else "보완 필요",
        "issues": issues,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


LEGAL_TOOLS = [
    legal_document_search_tool,
    law_article_search_tool,
    judgement_search_tool,
    standard_contract_search_tool,
    legal_procedure_search_tool,
    legal_answer_review_tool,
]
