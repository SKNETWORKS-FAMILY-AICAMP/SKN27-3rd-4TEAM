"""LLM-backed legal answer guardrail."""
from __future__ import annotations

import json
from typing import Any

from common.schemas.legal_consultation_schema import GuardrailResult
from common.tools.legal_guardrail_tools import apply_static_legal_guardrail
from common.tools.llm import LLMUnavailable, extract_json_object, llm_generate


def run_legal_guardrail_agent(
    *,
    draft_answer: str,
    evidence_refs: list[dict[str, Any]],
    question_type: str | None,
) -> GuardrailResult:
    static_guarded = apply_static_legal_guardrail(draft_answer)
    prompt = f"""
너는 부동산 법률상담 답변의 안전성 검수 agent다.

역할:
- 단정적 법률 판단 제거
- 변호사 상담 권고 문구 유지
- 근거 없는 확정 표현 제거
- 사용자가 바로 이해할 수 있게 과도하게 딱딱한 문장은 다듬기

근거가 부족하면 부족하다고 표시한다.

반환 JSON:
{{
  "safe_answer": "최종 안전 답변",
  "changed": true,
  "warnings": ["검수 메모"]
}}

question_type: {question_type}
evidence_count: {len(evidence_refs)}

draft_answer:
{static_guarded}
""".strip()
    try:
        data = extract_json_object(
            llm_generate(
                prompt,
                system="너는 법률 상담 guardrail agent다. JSON만 반환한다.",
                temperature=0.0,
            )
        )
    except Exception as exc:
        return GuardrailResult(
            safe_answer=static_guarded,
            changed=static_guarded != draft_answer,
            warnings=[f"LLM guardrail unavailable; static guardrail applied: {exc}"],
            llm_used=False,
        )

    return GuardrailResult(
        safe_answer=str(data.get("safe_answer") or static_guarded),
        changed=bool(data.get("changed", False)),
        warnings=[str(item) for item in data.get("warnings", [])],
        llm_used=True,
    )
