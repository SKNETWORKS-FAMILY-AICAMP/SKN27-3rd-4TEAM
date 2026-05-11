"""Adaptive RAG boundary for multi-agent graphs.

The RAG teammate can replace this module internals later. Agent graphs should keep
calling adaptive_rag(task_type, query, filters, top_k) and consume ContextPack only.
"""
from __future__ import annotations

from langchain_core.tools import tool

from common.schemas.shared import ContextPack, RetrievedContext, RetrievalQuality

TASK_SOURCE_MAP: dict[str, list[str]] = {
    "special_clause_analysis": ["checklist", "guide", "law", "case"],
    "required_check_analysis": ["checklist", "guide", "law"],
    "report_generation": ["checklist", "guide"],
    "legal_basis": ["law", "case", "guide"],
    "legal_case_search": ["case", "judgement"],
    "legal_law_guide_search": ["law", "guide", "checklist"],
    "defense_simulation_evidence": ["casebook", "guide", "law", "checklist"],
}

_FALLBACK_CONTEXTS: dict[str, list[RetrievedContext]] = {
    "special_clause_analysis": [
        RetrievedContext(
            source_id="mock-checklist-special-clause",
            title="전세계약 특약 점검 기준",
            doc_type="checklist",
            text=(
                "임차인에게 모든 수리비를 부담시키거나, 보증금 반환 시점을 과도하게 늦추거나, "
                "대항력 확보를 방해하는 특약은 위험 신호로 본다. 임대인의 추가 담보권 설정 제한과 "
                "잔금 다음날까지 권리 변동 금지 문구를 확인한다."
            ),
            score=0.75,
        )
    ],
    "required_check_analysis": [
        RetrievedContext(
            source_id="mock-checklist-required-docs",
            title="계약 전 필수 확인 서류",
            doc_type="checklist",
            text=(
                "계약서만으로는 등기부 권리관계, 임대인과 소유자 일치 여부, 선순위 보증금, 체납 세금, "
                "위반건축물 여부를 확정할 수 없다. 해당 자료를 별도로 확인해야 한다."
            ),
            score=0.72,
        )
    ],
    "legal_case_search": [
        RetrievedContext(
            source_id="mock-internal-case-deposit-return",
            title="내부 판례 샘플: 보증금 반환 지연 특약 관련",
            doc_type="case",
            text=(
                "임대인이 다음 임차인 입주나 자금 사정을 이유로 보증금 반환을 지연할 수 있는지에 관한 "
                "분쟁에서는 계약 종료, 목적물 인도, 반환 청구 사실, 특약의 구체적 문구가 핵심 쟁점이 된다. "
                "유사 판례는 임대인의 일방적 반환 지연 주장을 제한적으로 본 사례가 있다."
            ),
            score=0.78,
            metadata={
                "court": "내부 판례 자료",
                "case_number": "RAG_CASE_SAMPLE",
                "issue": "보증금 반환 지연 특약",
            },
        )
    ],
    "legal_law_guide_search": [
        RetrievedContext(
            source_id="mock-law-housing-lease",
            title="주택임대차보호법 및 임대차 가이드",
            doc_type="law",
            text=(
                "임차인은 대항력과 우선변제권 확보를 위해 전입신고, 점유, 확정일자 등 요건을 확인해야 하며, "
                "보증금 반환 분쟁에서는 계약 종료와 목적물 반환, 반환 요구 증거가 중요하다."
            ),
            score=0.72,
            metadata={"law": "주택임대차보호법", "issue": "보증금 반환 및 임차인 보호"},
        )
    ],
    "defense_simulation_evidence": [
        RetrievedContext(
            source_id="mock-casebook-defense-simulation",
            title="전세피해 사례집 기반 방어 훈련 기준",
            doc_type="casebook",
            text=(
                "전세사기 예방 훈련에서는 등기부 직접 발급, 신탁원부 확인, 임대인 신분 및 대리권 확인, "
                "전세가율과 보증보험 가능 여부 확인, 전입신고와 확정일자 확보, 불리한 특약 수정 요구를 "
                "핵심 방어 행동으로 본다."
            ),
            score=0.73,
        )
    ],
    "report_generation": [
        RetrievedContext(
            source_id="mock-guide-report",
            title="전세계약 위험 안내 리포트 작성 기준",
            doc_type="guide",
            text="위험도는 확정적 법률 판단이 아니라 계약 전 확인을 돕는 보조 정보로 설명해야 한다.",
            score=0.7,
        )
    ],
}


def adaptive_rag(task_type: str, query: str, filters: dict | None = None, top_k: int = 5) -> ContextPack:
    contexts = list(_FALLBACK_CONTEXTS.get(task_type, []))[:top_k]
    quality = RetrievalQuality(
        sufficient=bool(contexts),
        score=0.7 if contexts else 0.0,
        reason="mock context pack; replace with real Adaptive/Corrective RAG retriever",
    )
    return ContextPack(task_type=task_type, query=query, contexts=contexts, quality=quality)


@tool
def adaptive_rag_tool(task_type: str, query: str, filters: dict | None = None, top_k: int = 5) -> ContextPack:
    """Retrieve a ContextPack for a task using the configured Adaptive RAG boundary."""
    return adaptive_rag(task_type=task_type, query=query, filters=filters, top_k=top_k)