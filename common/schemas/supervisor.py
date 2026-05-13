"""Supervisor graph schemas.

SupervisorState is the unified entry point that routes user input
to one of the three sub-graphs:
  - diagnosis       : 계약서 파일 분석 (DiagnosisGraph)
  - legal           : 법률 질문 상담 (LegalConsultationGraph)
  - defense         : 전세사기 방어 RPG (DefenseSimulationGraph)
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

# ── 라우팅 결정 타입 ────────────────────────────────────────────────
AgentIntent = Literal["diagnosis", "legal", "defense", "unknown"]

ClassificationMethod = Literal["rule_contract_file", "rule_category_id",
                                "rule_keyword", "llm", "default"]


class SupervisorState(TypedDict, total=False):
    # ── 공통 입력 ───────────────────────────────────────────────────
    session_id: str

    # 계약서 진단용 입력
    contract_file: str | None           # PDF/TXT 파일 경로

    # 법률 상담용 입력
    user_message: str | None            # 사용자 질문 또는 메시지
    contract_context: dict[str, Any] | None  # 관련 계약 문맥 (선택)

    # RPG 방어 훈련용 입력
    category_id: str | None             # 시나리오 카테고리 ID
    current_stage_index: int            # 현재 스테이지 (기본 0)
    risk_exposure: int                  # 누적 위험 노출 점수 (기본 0)
    failed_stage_count: int             # 실패 스테이지 수 (기본 0)
    hint_used_count: int                # 힌트 사용 횟수 (기본 0)

    # ── Supervisor 제어 ─────────────────────────────────────────────
    intent: AgentIntent                 # 분류된 입력 의도
    next_agent: str                     # 라우팅 대상 ("diagnosis" | "legal" | "defense" | "end")
    routing_reason: str                 # 라우팅 결정 이유 (설명용)
    classification_method: ClassificationMethod  # 분류에 사용된 방법

    # ── Sub-graph 실행 결과 ─────────────────────────────────────────
    diagnosis_result: dict[str, Any] | None
    legal_result: dict[str, Any] | None
    defense_result: dict[str, Any] | None

    # ── 최종 출력 ───────────────────────────────────────────────────
    final_response: dict[str, Any]      # 프론트엔드에 전달할 통합 응답
    status: Literal["routing", "running", "completed", "error"]
    errors: list[str]
