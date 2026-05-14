"""
최상위 Supervisor Graph
=======================
flowchart 구조:
  사용자 입력
      │
      ▼
  supervisor (입력 타입 판단)
      ├── Doc/PDF → contract_extractor → 기본정보 존재? → model_agent / special_terms_agent
      │                                                  → report_writer → JSON 저장 → 리포트 출력
      └── 채팅 테스트 → chat_supervisor → legal_agent (법률 RAG)
                                        → JSON reader (저장 결과 로드)
                                               → 답변 생성 → 채팅 응답 출력
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

# ── 내부 그래프 ─────────────────────────────────────────────────────────────


def _load_diagnosis_result(session_id: str) -> dict[str, Any] | None:
    """저장된 진단 JSON 결과를 불러옵니다 (JSON reader)."""
    save_dir = Path(__file__).resolve().parents[2] / "data" / "diagnosis_results"
    path = save_dir / f"{session_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _classify_input(
    *,
    contract_file: str | None,
    user_message: str | None,
    category_id: str | None,
) -> tuple[str, str, str]:
    """
    입력 타입 분류 → (intent, classification_method, routing_reason)
    intent: "diagnosis" | "legal" | "defense"
    """
    # 1. 계약서 파일이 직접 전달된 경우 → diagnosis
    if contract_file:
        ext = Path(contract_file).suffix.lower()
        if ext in {".pdf", ".docx", ".doc", ".txt", ".png", ".jpg"}:
            return "diagnosis", "file_extension", f"계약서 파일 감지 ({ext})"

    # 2. category_id 가 RPG 시나리오인 경우 → defense
    if category_id:
        return "defense", "category_id", f"RPG 시나리오 ID 직접 전달: {category_id}"

    msg = (user_message or "").strip()

    if not msg:
        return "legal", "default", "입력 없음 → 법률 상담 기본 라우팅"

    # 3. RPG / defense 키워드
    defense_patterns = [
        r"(rpg|게임|훈련|시나리오|사기꾼|npc|힌트|roleplay|/도움말|/힌트|/확인)",
        r"(방어\s*훈련|시뮬레이션|시나리오\s*시작)",
    ]
    for pattern in defense_patterns:
        if re.search(pattern, msg, re.IGNORECASE):
            return "defense", "keyword_match", f"RPG 키워드 감지: {pattern}"

    # 4. 법률 상담 키워드
    legal_patterns = [
        r"(전세|보증금|임대차|임차인|임대인|계약|특약|조항|대항력|확정일자|전입신고|등기|근저당|가압류|압류|신탁|체납|보증보험|HUG|SGI|법|판례|내용증명|임차권|경매|배당)",
    ]
    for pattern in legal_patterns:
        if re.search(pattern, msg, re.IGNORECASE):
            return "legal", "keyword_match", f"법률 키워드 감지"

    # 5. 기본 → 법률 상담
    return "legal", "default", "기본 법률 상담 라우팅"


# ── Diagnosis 실행 ────────────────────────────────────────────────────────────

def _run_diagnosis(
    contract_file: str | None,
    session_id: str,
) -> dict[str, Any]:
    """계약서 진단 그래프 실행."""
    try:
        from common.graphs.diagnosis_graph import run_diagnosis
        result = run_diagnosis(contract_file=contract_file, session_id=session_id)
        report = result.get("report") or {}
        return {
            "type": "diagnosis",
            "session_id": session_id,
            "risk_score": result.get("risk_score", 0),
            "risk_level": result.get("risk_level", "UNKNOWN"),
            "report": report,
            "errors": result.get("errors", []),
        }
    except Exception as exc:
        return {
            "type": "diagnosis",
            "session_id": session_id,
            "error": str(exc),
            "risk_score": 0,
            "risk_level": "UNKNOWN",
            "report": {},
            "errors": [str(exc)],
        }


# ── Chat supervisor 라우팅 ────────────────────────────────────────────────────

def _run_chat(
    user_message: str,
    session_id: str,
    conversation_history: list[dict[str, str]] | None,
) -> dict[str, Any]:
    """
    chat supervisor → legal_agent (법률 RAG) 또는 JSON reader (저장 결과 로드) 실행.
    """
    # JSON reader: 저장된 진단 결과 참조 요청인지 확인
    msg = user_message or ""
    is_report_request = any(
        kw in msg for kw in ["보고서", "리포트", "진단 결과", "이전 결과", "저장된", "분석 결과"]
    )

    saved_result: dict[str, Any] | None = None
    if is_report_request:
        saved_result = _load_diagnosis_result(session_id)

    # legal_agent (RAG 검색)
    try:
        from common.graphs.legal_consultation_graph import run_legal_consultation
        legal_state = run_legal_consultation(
            user_question=user_message,
            session_id=session_id,
            conversation_history=conversation_history or [],
        )
        report = legal_state.get("report") or {}
        answer = (
            report.get("answer")
            or legal_state.get("final_answer")
            or legal_state.get("safe_answer")
            or legal_state.get("draft_answer")
            or legal_state.get("answer_draft")
            or ""
        )
    except Exception as exc:
        report = {}
        answer = f"죄송합니다. 현재 법률 상담 서비스에 일시적인 오류가 발생했습니다. ({exc})"

    # 답변 생성: 저장된 진단 결과가 있으면 함께 제공
    if saved_result and is_report_request:
        answer = (
            f"[이전 진단 결과]\n"
            f"위험점수: {saved_result.get('risk_score', 'N/A')} / 위험등급: {saved_result.get('risk_level', 'N/A')}\n\n"
            + answer
        )

    return {
        "type": "chat",
        "session_id": session_id,
        "answer": answer,
        "report": report,
        "saved_diagnosis": saved_result,
        "errors": [],
    }


# ── Defense simulation 실행 ───────────────────────────────────────────────────

def _run_defense(
    category_id: str,
    user_message: str,
    session_id: str,
) -> dict[str, Any]:
    """RPG 방어 훈련 시뮬레이션 실행."""
    try:
        from common.graphs.defense_simulation_graph import run_defense_simulation
        result = run_defense_simulation(
            category_id=category_id,
            user_message=user_message,
            session_id=session_id,
        )
        return {
            "type": "defense",
            "session_id": session_id,
            "game_status": result.get("game_status", "PLAYING"),
            "npc_response": result.get("npc_response", ""),
            "feedback": result.get("feedback", ""),
            "errors": result.get("errors", []),
        }
    except Exception as exc:
        return {
            "type": "defense",
            "session_id": session_id,
            "error": str(exc),
            "errors": [str(exc)],
        }


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

def run_supervisor(
    *,
    contract_file: str | None = None,
    user_message: str | None = None,
    category_id: str | None = None,
    session_id: str = "supervisor-session",
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    최상위 Supervisor: 입력 타입 판단 후 적절한 그래프로 라우팅.

    Parameters
    ----------
    contract_file    : 계약서 파일 경로 (Doc/PDF 진단 경로)
    user_message     : 채팅 질문 / RPG 명령어
    category_id      : RPG 시나리오 카테고리 ID
    session_id       : 세션 ID (JSON 저장/로드에도 사용)
    conversation_history : 이전 대화 이력

    Returns
    -------
    dict with keys:
        intent              : "diagnosis" | "legal" | "defense"
        classification_method
        routing_reason
        final_response      : 실행 결과 dict
        errors              : list of error strings
    """
    intent, method, reason = _classify_input(
        contract_file=contract_file,
        user_message=user_message,
        category_id=category_id,
    )

    # ── 라우팅 실행 ──
    if intent == "diagnosis":
        final_response = _run_diagnosis(contract_file=contract_file, session_id=session_id)

    elif intent == "defense":
        final_response = _run_defense(
            category_id=category_id or "RIGHTS_CONCEALMENT",
            user_message=user_message or "/도움말",
            session_id=session_id,
        )

    else:  # legal (default)
        final_response = _run_chat(
            user_message=user_message or "",
            session_id=session_id,
            conversation_history=conversation_history,
        )

    return {
        "intent": intent,
        "classification_method": method,
        "routing_reason": reason,
        "session_id": session_id,
        "final_response": final_response,
        "errors": final_response.get("errors", []),
    }


# ── CLI 실행 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    def _default(v: Any) -> Any:
        if is_dataclass(v):
            return asdict(v)
        return str(v)

    print("\n[Supervisor Graph - 입력 타입 판단]\n")
    print("1: 계약서 파일 경로 입력 (diagnosis)")
    print("2: 법률 질문 입력 (legal)")
    print("3: RPG 훈련 (defense)")
    choice = input("선택 (1/2/3): ").strip()

    if choice == "1":
        fp = input("계약서 파일 경로: ").strip() or None
        result = run_supervisor(contract_file=fp, session_id="cli-diagnosis")
    elif choice == "3":
        result = run_supervisor(category_id="RIGHTS_CONCEALMENT", user_message="/도움말", session_id="cli-defense")
    else:
        q = input("질문: ").strip() or "보증금 반환이 안 되면 어떻게 해야 하나요?"
        result = run_supervisor(user_message=q, session_id="cli-legal")

    print(json.dumps(result, ensure_ascii=False, indent=2, default=_default))
