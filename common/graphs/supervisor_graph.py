"""Top-level supervisor graph that routes to specific sub-graphs."""
from __future__ import annotations

import os
from typing import Any, Dict, TypedDict

from common.graphs.diagnosis_graph import run_diagnosis
from common.graphs.legal_consultation_graph import run_legal_consultation

class SupervisorState(TypedDict):
    session_id: str
    user_message: str | None
    contract_file: str | None
    category_id: str | None
    intent: str
    classification_method: str
    routing_reason: str
    final_response: Dict[str, Any]
    errors: list[str]

def run_supervisor(
    user_message: str | None = None,
    contract_file: str | None = None,
    category_id: str | None = None,
    session_id: str = "default-session",
) -> Dict[str, Any]:
    """
    Orchestrate routing between different specialized graphs.
    """
    state: SupervisorState = {
        "session_id": session_id,
        "user_message": user_message,
        "contract_file": contract_file,
        "category_id": category_id,
        "intent": "legal",
        "classification_method": "rule_based",
        "routing_reason": "default to legal consultation",
        "final_response": {},
        "errors": []
    }

    # 1. Simple Routing Logic (Mimic test_supervisor expectations)
    if contract_file:
        state["intent"] = "diagnosis"
        state["routing_reason"] = f"Detected contract file: {contract_file}"
        diag_result = run_diagnosis(contract_file=contract_file, session_id=session_id)
        state["final_response"] = {
            "type": "diagnosis",
            "report": diag_result.get("report", {}),
            "risk_score": diag_result.get("report", {}).get("risk_score", 0)
        }
    
    elif category_id or (user_message and any(k in user_message for k in ["RPG", "훈련", "시나리오", "게임", "/힌트", "/도움말"])):
        state["intent"] = "defense"
        state["routing_reason"] = "Detected RPG defense simulation keywords or category_id"
        state["final_response"] = {
            "type": "defense",
            "message": "방어 시뮬레이션 모드로 전환합니다. (Mock Response)",
            "scenario": category_id or "GENERAL"
        }
    
    else:
        state["intent"] = "legal"
        state["routing_reason"] = "Standard legal consultation query"
        legal_result = run_legal_consultation(user_question=user_message, session_id=session_id)
        state["final_response"] = {
            "type": "legal",
            "answer": legal_result.get("report", {}).get("answer", "상담 결과를 불러올 수 없습니다."),
            "references": legal_result.get("evidence_refs", [])
        }

    # Return structure expected by test_supervisor.py
    return {
        "intent": state["intent"],
        "classification_method": state["classification_method"],
        "routing_reason": state["routing_reason"],
        "final_response": state["final_response"],
        "errors": state["errors"],
        "session_id": state["session_id"]
    }

if __name__ == "__main__":
    # Quick test
    res = run_supervisor(user_message="전세가율이 뭐야?")
    print(f"Routing to: {res['intent']}")
