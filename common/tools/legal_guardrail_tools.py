"""Guardrail helpers for legal consultation answers."""
from __future__ import annotations

from langchain_core.tools import tool

DISCLAIMER = "본 답변은 법률 자문이 아니라 공공자료와 판례·법령 근거를 바탕으로 한 일반 정보입니다. 구체적인 판단은 계약서와 증거를 확인한 전문가 상담을 권장합니다."

OVERCONFIDENT_REPLACEMENTS = {
    "무조건 이깁니다": "유리한 근거가 있을 수 있습니다",
    "반드시 돌려받을 수 있습니다": "반환 청구 근거로 활용될 수 있습니다",
    "승소 가능합니다": "주장이 받아들여질 가능성을 검토할 수 있습니다",
    "법적으로 문제 없습니다": "분쟁 가능성이 낮다고 단정하기는 어렵습니다",
    "확실합니다": "제공된 근거 범위에서 그렇게 볼 여지가 있습니다",
}


def apply_static_legal_guardrail(answer: str) -> str:
    guarded = answer or ""
    for bad, safe in OVERCONFIDENT_REPLACEMENTS.items():
        guarded = guarded.replace(bad, safe)
    if DISCLAIMER not in guarded:
        guarded = guarded.rstrip() + "\n\n" + DISCLAIMER
    return guarded.strip()


@tool
def apply_static_legal_guardrail_tool(answer: str) -> str:
    """Apply deterministic legal-safety wording replacements."""
    return apply_static_legal_guardrail(answer)
