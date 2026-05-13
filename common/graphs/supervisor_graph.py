"""Supervisor graph — 전세계약 위험 진단 통합 오케스트레이터.

입력 데이터의 특성에 따라 세 개의 전문 sub-graph 중 하나로 자동 라우팅합니다.

    ┌─────────────────────────────────────────────────────────────────┐
    │                        Supervisor Graph                         │
    │                                                                 │
    │  사용자 입력                                                      │
    │      │                                                          │
    │      ▼                                                          │
    │  [supervisor_node]  ← LLM + 키워드 기반 입력 의도 분류             │
    │      │                                                          │
    │      ▼ (conditional_edge)                                       │
    │   ┌──┴──────────────────┬───────────────────┐                  │
    │   ▼                     ▼                   ▼                  │
    │ [diagnosis_node]  [legal_node]   [defense_node]                 │
    │ 계약서 파일 분석    법률 질문 상담   RPG 방어 훈련                   │
    │   │                     │                   │                  │
    │   └──────────┬──────────┘                   │                  │
    │              └──────────────────────────────┘                  │
    │                         │                                      │
    │                         ▼                                      │
    │                  [result_node]  ← 결과 패키징 + 프론트 응답 생성   │
    │                         │                                      │
    │                        END                                     │
    └─────────────────────────────────────────────────────────────────┘

라우팅 우선순위:
    1. contract_file 있음      → "diagnosis"  (계약서 진단)
    2. category_id 있음        → "defense"   (RPG 방어 훈련)
    3. user_message 키워드 분석 → "legal" / "defense"
    4. LLM(Ollama) 분류        → 위 세 가지 중 하나
    5. fallback                → "legal"
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, is_dataclass
from typing import Any, Literal

from common.schemas.supervisor import AgentIntent, SupervisorState

# ── 라우팅 키워드 사전 ─────────────────────────────────────────────────

# RPG / 방어 훈련 관련 키워드
_DEFENSE_KEYWORDS: set[str] = {
    "rpg", "시나리오", "훈련", "게임", "방어", "스테이지", "stage",
    "/힌트", "/상태", "/근거", "/도움말", "/포기",
    "사기꾼", "npc", "압박", "대응해봐", "어떻게 대응",
    "전세사기 훈련", "방어 rpg", "defense",
}

# 계약서 진단 관련 키워드 (user_message로 진단 요청하는 경우)
_DIAGNOSIS_KEYWORDS: set[str] = {
    "계약서", "pdf", "txt", "파일", "분석해줘", "진단해줘",
    "계약서를 올렸", "계약서 검토", "업로드",
}

# 법률 상담 관련 키워드
_LEGAL_KEYWORDS: set[str] = {
    "특약", "보증금", "전입신고", "확정일자", "대항력", "우선변제",
    "등기부", "근저당", "가압류", "신탁", "임차인", "임대인",
    "전세사기", "법", "판례", "법령", "조항", "위험한가요",
    "어떻게 되나요", "가능한가요", "합법", "불법", "권리",
    "보증보험", "hug", "전세가율", "깡통전세", "소유자",
}


# ── 헬퍼 ─────────────────────────────────────────────────────────────

def _safe_session_id(state: SupervisorState) -> str:
    return state.get("session_id") or f"supervisor-{uuid.uuid4().hex[:8]}"


def _json_default(v: Any) -> Any:
    if is_dataclass(v):
        return asdict(v)
    return str(v)


def _to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj):
        return asdict(obj)
    return {}


# ── 1. Supervisor Node: 입력 분류 및 라우팅 결정 ─────────────────────

def supervisor_node(state: SupervisorState) -> SupervisorState:
    """입력 데이터를 분석해 적절한 sub-graph를 결정합니다.

    분류 우선순위:
        Rule 1. contract_file 존재 → diagnosis
        Rule 2. category_id 존재   → defense
        Rule 3. 키워드 매칭         → diagnosis / legal / defense
        Rule 4. LLM 분류           → Ollama 호출
        Rule 5. Fallback           → legal
    """
    session_id = _safe_session_id(state)
    contract_file = state.get("contract_file")
    category_id = state.get("category_id")
    user_message = (state.get("user_message") or "").strip()

    print(f"\n[Supervisor] 세션: {session_id}")
    print(f"[Supervisor] 입력 분석 중...")

    # ── Rule 1: 계약서 파일이 있으면 무조건 진단 ────────────────────
    if contract_file:
        print(f"[Supervisor] Rule 1 적용 → 계약서 파일 감지: {contract_file}")
        return {
            **state,
            "session_id": session_id,
            "intent": "diagnosis",
            "next_agent": "diagnosis",
            "routing_reason": f"계약서 파일({contract_file})이 입력되어 진단 그래프로 라우팅합니다.",
            "classification_method": "rule_contract_file",
            "status": "routing",
            "errors": state.get("errors", []),
        }

    # ── Rule 2: category_id가 있으면 RPG 방어 훈련 ─────────────────
    if category_id:
        print(f"[Supervisor] Rule 2 적용 → 카테고리 ID 감지: {category_id}")
        return {
            **state,
            "session_id": session_id,
            "intent": "defense",
            "next_agent": "defense",
            "routing_reason": f"시나리오 카테고리({category_id})가 지정되어 RPG 방어 훈련 그래프로 라우팅합니다.",
            "classification_method": "rule_category_id",
            "status": "routing",
            "errors": state.get("errors", []),
        }

    # ── Rule 3: 메시지가 없으면 법률 상담 기본 ─────────────────────
    if not user_message:
        print("[Supervisor] Rule 5 적용 → 메시지 없음, 법률 상담으로 기본 라우팅")
        return {
            **state,
            "session_id": session_id,
            "intent": "legal",
            "next_agent": "legal",
            "routing_reason": "입력 메시지가 없어 법률 상담 그래프로 기본 라우팅합니다.",
            "classification_method": "default",
            "status": "routing",
            "errors": state.get("errors", []),
        }

    # ── Rule 3: 키워드 기반 분류 ──────────────────────────────────
    msg_lower = user_message.lower()

    defense_score = sum(1 for kw in _DEFENSE_KEYWORDS if kw in msg_lower)
    diagnosis_score = sum(1 for kw in _DIAGNOSIS_KEYWORDS if kw in msg_lower)
    legal_score = sum(1 for kw in _LEGAL_KEYWORDS if kw in msg_lower)

    print(f"[Supervisor] 키워드 점수 — 진단:{diagnosis_score} 법률:{legal_score} RPG:{defense_score}")

    # 명확한 RPG 키워드 우선
    if defense_score > 0 and defense_score >= legal_score:
        intent: AgentIntent = "defense"
        reason = f"RPG/방어훈련 키워드 감지 (점수: {defense_score})."
        method = "rule_keyword"

    # 계약서 파일 언급
    elif diagnosis_score > 0 and diagnosis_score >= legal_score:
        intent = "diagnosis"
        reason = f"계약서 분석 키워드 감지 (점수: {diagnosis_score}). contract_file 경로를 함께 전달해야 합니다."
        method = "rule_keyword"

    # 법률 키워드가 가장 높거나 모호한 경우
    elif legal_score > 0:
        intent = "legal"
        reason = f"법률/전세 키워드 감지 (점수: {legal_score})."
        method = "rule_keyword"

    # ── Rule 4: LLM 분류 (Ollama) ───────────────────────────────
    else:
        intent, reason, method = _classify_with_llm(user_message)

    print(f"[Supervisor] 분류 결과: {intent} ({method})")
    print(f"[Supervisor] 라우팅 이유: {reason}")

    return {
        **state,
        "session_id": session_id,
        "intent": intent,
        "next_agent": intent if intent != "unknown" else "legal",
        "routing_reason": reason,
        "classification_method": method,
        "status": "routing",
        "errors": state.get("errors", []),
    }


def _classify_with_llm(user_message: str) -> tuple[AgentIntent, str, str]:
    """Ollama LLM으로 입력 의도를 분류합니다. 실패 시 'legal'로 fallback.

    모델명·URL은 환경변수(OLLAMA_MODEL, OLLAMA_BASE_URL)를 공유합니다.
    common/tools/llm.py 의 기본값과 동일하게 gemma4:e2b / localhost:11434 사용.
    """
    import os

    try:
        import requests

        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "gemma4:e2b")

        prompt = f"""당신은 전세계약 서비스의 입력 분류기입니다.
사용자 입력을 읽고 아래 세 가지 카테고리 중 하나로만 분류하세요.

카테고리:
- diagnosis : 계약서 파일 분석/진단 요청
- legal     : 전세계약 관련 법률 질문, 법령/판례 검색, 권리관계 상담
- defense   : 전세사기 방어 RPG 게임/훈련 요청

응답 형식: 카테고리 이름만 한 단어로 출력 (diagnosis / legal / defense)

사용자 입력: {user_message}
분류:"""

        resp = requests.post(
            f"{ollama_base}/api/generate",
            json={"model": ollama_model, "prompt": prompt, "stream": False},
            timeout=10,
        )
        if resp.status_code == 200:
            raw = resp.json().get("response", "").strip().lower()
            for candidate in ("diagnosis", "legal", "defense"):
                if candidate in raw:
                    return (
                        candidate,  # type: ignore[return-value]
                        f"LLM 분류 결과: {candidate}",
                        "llm",
                    )
    except Exception as e:
        print(f"[Supervisor] LLM 분류 실패 ({e}), fallback → legal")

    return "legal", "분류 불가 — 법률 상담 그래프로 기본 라우팅합니다.", "default"


# ── 2. Sub-graph 실행 노드 ────────────────────────────────────────────

def diagnosis_node(state: SupervisorState) -> SupervisorState:
    """계약서 진단 sub-graph를 실행합니다."""
    print("\n[Supervisor → DiagnosisGraph] 계약서 진단 시작...")
    errors = list(state.get("errors", []))

    try:
        from common.graphs.diagnosis_graph import run_diagnosis

        result = run_diagnosis(
            contract_file=state.get("contract_file"),
            session_id=state.get("session_id", "supervisor-diag"),
        )
        diagnosis_result = _to_dict(result)
        print("[Supervisor ← DiagnosisGraph] 진단 완료.")
    except Exception as e:
        msg = f"DiagnosisGraph 실행 오류: {e}"
        print(f"[Supervisor] {msg}")
        errors.append(msg)
        diagnosis_result = {"error": msg}

    return {
        **state,
        "diagnosis_result": diagnosis_result,
        "status": "running",
        "errors": errors,
    }


def legal_node(state: SupervisorState) -> SupervisorState:
    """법률 상담 sub-graph를 실행합니다."""
    print("\n[Supervisor → LegalConsultationGraph] 법률 상담 시작...")
    errors = list(state.get("errors", []))
    user_message = state.get("user_message") or ""

    try:
        from common.graphs.legal_consultation_graph import run_legal_consultation

        result = run_legal_consultation(
            question=user_message,
            related_finding=None,
            contract_context=state.get("contract_context"),
            session_id=state.get("session_id", "supervisor-legal"),
        )
        legal_result = _to_dict(result)
        print("[Supervisor ← LegalConsultationGraph] 법률 상담 완료.")
    except Exception as e:
        msg = f"LegalConsultationGraph 실행 오류: {e}"
        print(f"[Supervisor] {msg}")
        errors.append(msg)
        legal_result = {"error": msg}

    return {
        **state,
        "legal_result": legal_result,
        "status": "running",
        "errors": errors,
    }


def defense_node(state: SupervisorState) -> SupervisorState:
    """RPG 방어 훈련 sub-graph를 실행합니다."""
    print("\n[Supervisor → DefenseSimulationGraph] RPG 방어 훈련 시작...")
    errors = list(state.get("errors", []))

    try:
        from common.graphs.defense_simulation_graph import run_defense_simulation

        result = run_defense_simulation(
            category_id=state.get("category_id") or "RIGHTS_CONCEALMENT",
            user_message=state.get("user_message") or "/도움말",
            current_stage_index=state.get("current_stage_index", 0),
            session_id=state.get("session_id", "supervisor-defense"),
            risk_exposure=state.get("risk_exposure", 0),
            failed_stage_count=state.get("failed_stage_count", 0),
            hint_used_count=state.get("hint_used_count", 0),
        )
        defense_result = _to_dict(result)
        print("[Supervisor ← DefenseSimulationGraph] RPG 방어 훈련 완료.")
    except Exception as e:
        msg = f"DefenseSimulationGraph 실행 오류: {e}"
        print(f"[Supervisor] {msg}")
        errors.append(msg)
        defense_result = {"error": msg}

    return {
        **state,
        "defense_result": defense_result,
        "status": "running",
        "errors": errors,
    }


# ── 3. Result Node: 결과 패키징 ──────────────────────────────────────

def result_node(state: SupervisorState) -> SupervisorState:
    """각 sub-graph의 결과를 하나의 통합 응답으로 패키징합니다."""
    print("\n[Supervisor] 결과 패키징 중...")

    intent = state.get("intent", "unknown")
    errors = state.get("errors", [])

    # ── 진단 결과 패키징 ─────────────────────────────────────────────
    if intent == "diagnosis":
        raw = state.get("diagnosis_result") or {}
        report = raw.get("report") or {}
        final_response: dict[str, Any] = {
            "type": "diagnosis",
            "session_id": state.get("session_id"),
            "routing_reason": state.get("routing_reason"),
            "risk_score": raw.get("risk_score", report.get("risk_score", 0)),
            "risk_level": raw.get("risk_level", report.get("risk_level", "UNKNOWN")),
            "risk_findings": raw.get("risk_findings", report.get("risk_findings", [])),
            "report": report or raw,
            "errors": errors,
        }

    # ── 법률 상담 결과 패키징 ────────────────────────────────────────
    elif intent == "legal":
        raw = state.get("legal_result") or {}
        report = raw.get("report") or {}
        final_response = {
            "type": "legal",
            "session_id": state.get("session_id"),
            "routing_reason": state.get("routing_reason"),
            "question": state.get("user_message", ""),
            "answer": raw.get("answer", report.get("answer", "")),
            "cited_cases": raw.get("cited_cases", report.get("cited_cases", [])),
            "cited_laws": raw.get("cited_laws", report.get("cited_laws", [])),
            "recommended_actions": raw.get("recommended_actions", report.get("recommended_actions", [])),
            "report": report or raw,
            "errors": errors,
        }

    # ── RPG 방어 훈련 결과 패키징 ────────────────────────────────────
    elif intent == "defense":
        raw = state.get("defense_result") or {}
        report = raw.get("report") or {}
        final_response = {
            "type": "defense",
            "session_id": state.get("session_id"),
            "routing_reason": state.get("routing_reason"),
            "roleplay_message": raw.get("roleplay_message", ""),
            "stage_status": raw.get("stage_status", ""),
            "game_status": raw.get("game_status", "PLAYING"),
            "feedback": raw.get("feedback_report", report.get("feedback_report", {})),
            "report": report or raw,
            "errors": errors,
        }

    # ── 알 수 없는 의도 ─────────────────────────────────────────────
    else:
        final_response = {
            "type": "unknown",
            "session_id": state.get("session_id"),
            "routing_reason": state.get("routing_reason", "의도를 분류하지 못했습니다."),
            "message": "입력을 처리할 수 없습니다. 계약서 파일 경로, 법률 질문, 또는 RPG 카테고리를 입력해주세요.",
            "errors": errors,
        }

    print(f"[Supervisor] 최종 응답 타입: {intent}")
    print(f"[Supervisor] 완료!\n")

    return {
        **state,
        "final_response": final_response,
        "status": "completed",
        "errors": errors,
    }


# ── 4. 조건부 라우팅 함수 ─────────────────────────────────────────────

def route_to_agent(
    state: SupervisorState,
) -> Literal["diagnosis", "legal", "defense", "result"]:
    """supervisor_node의 결정에 따라 다음 노드를 선택합니다."""
    next_agent = state.get("next_agent", "legal")
    intent = state.get("intent", "unknown")

    print(f"[Router] intent={intent} → {next_agent} 노드로 이동")

    if next_agent == "diagnosis":
        return "diagnosis"
    if next_agent == "defense":
        return "defense"
    if next_agent == "legal":
        return "legal"

    # unknown 등 예외 → result_node에서 에러 메시지 생성
    return "result"


# ── 5. 그래프 빌더 ────────────────────────────────────────────────────

def build_supervisor_graph():
    """Supervisor LangGraph StateGraph를 빌드하고 컴파일합니다."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(SupervisorState)

    # 노드 등록
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("diagnosis", diagnosis_node)
    graph.add_node("legal", legal_node)
    graph.add_node("defense", defense_node)
    graph.add_node("result", result_node)

    # 진입점 → Supervisor
    graph.add_edge(START, "supervisor")

    # Supervisor → 조건부 분기
    graph.add_conditional_edges(
        "supervisor",
        route_to_agent,
        {
            "diagnosis": "diagnosis",
            "legal": "legal",
            "defense": "defense",
            "result": "result",
        },
    )

    # 각 sub-graph 노드 → result 노드
    graph.add_edge("diagnosis", "result")
    graph.add_edge("legal", "result")
    graph.add_edge("defense", "result")

    # result → END
    graph.add_edge("result", END)

    return graph.compile()


# ── 6. 공개 실행 함수 ─────────────────────────────────────────────────

def run_supervisor(
    user_message: str | None = None,
    contract_file: str | None = None,
    category_id: str | None = None,
    current_stage_index: int = 0,
    risk_exposure: int = 0,
    failed_stage_count: int = 0,
    hint_used_count: int = 0,
    contract_context: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> SupervisorState:
    """Supervisor 그래프를 실행하는 메인 진입점.

    Args:
        user_message:        사용자 질문 또는 RPG 대응 메시지
        contract_file:       계약서 PDF/TXT 파일 경로 (진단 시 필수)
        category_id:         RPG 시나리오 카테고리 ID (방어 훈련 시)
        current_stage_index: RPG 현재 스테이지 인덱스
        risk_exposure:       RPG 누적 위험 노출 점수
        failed_stage_count:  RPG 실패 스테이지 수
        hint_used_count:     RPG 힌트 사용 횟수
        contract_context:    법률 상담 시 관련 계약 문맥 (선택)
        session_id:          세션 ID (자동 생성 가능)

    Returns:
        SupervisorState: 라우팅 결과 및 sub-graph 실행 결과 포함
    """
    sid = session_id or f"supervisor-{uuid.uuid4().hex[:8]}"

    initial_state: SupervisorState = {
        "session_id": sid,
        "user_message": user_message,
        "contract_file": contract_file,
        "category_id": category_id,
        "current_stage_index": current_stage_index,
        "risk_exposure": risk_exposure,
        "failed_stage_count": failed_stage_count,
        "hint_used_count": hint_used_count,
        "contract_context": contract_context,
        "errors": [],
    }

    try:
        graph = build_supervisor_graph()
        return graph.invoke(initial_state)
    except ModuleNotFoundError:
        # LangGraph 미설치 환경: 노드를 순서대로 직접 실행
        state = supervisor_node(initial_state)
        intent = state.get("next_agent", "legal")
        if intent == "diagnosis":
            state = diagnosis_node(state)
        elif intent == "defense":
            state = defense_node(state)
        else:
            state = legal_node(state)
        return result_node(state)


# ── 7. 인터랙티브 CLI ─────────────────────────────────────────────────

def run_interactive() -> None:
    """터미널에서 Supervisor를 대화형으로 테스트합니다."""
    print("\n" + "=" * 60)
    print("  전세계약 위험 진단 — Supervisor Agent")
    print("=" * 60)
    print("입력 유형에 따라 자동으로 적절한 에이전트로 라우팅됩니다.")
    print()
    print("  [1] 계약서 진단  : 계약서 파일 경로 입력")
    print("  [2] 법률 상담    : 전세계약 관련 질문 입력")
    print("  [3] RPG 방어 훈련: 카테고리 ID 입력")
    print("-" * 60)

    # 입력 모드 선택
    mode = input("모드 선택 (1/2/3, 기본=2): ").strip() or "2"

    if mode == "1":
        contract_file = input("계약서 파일 경로: ").strip() or None
        result = run_supervisor(contract_file=contract_file)

    elif mode == "3":
        print("\n카테고리 ID 예시: RIGHTS_CONCEALMENT, MULTIPLE_CONTRACT, PROXY_FRAUD")
        category_id = input("카테고리 ID: ").strip() or "RIGHTS_CONCEALMENT"
        user_message = input("대응 메시지 (기본=/도움말): ").strip() or "/도움말"
        result = run_supervisor(category_id=category_id, user_message=user_message)

    else:
        question = input("법률 질문을 입력하세요: ").strip()
        if not question:
            question = "보증금 반환은 다음 임차인 입주 이후에 한다는 특약이 위험한가요?"
        result = run_supervisor(user_message=question)

    # 결과 출력
    print("\n" + "=" * 60)
    print("  Supervisor 실행 결과")
    print("=" * 60)
    final = result.get("final_response", {})
    print(f"  라우팅 타입  : {final.get('type', '?')}")
    print(f"  라우팅 이유  : {result.get('routing_reason', '?')}")
    print(f"  분류 방법    : {result.get('classification_method', '?')}")
    print("-" * 60)
    print(json.dumps(final, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == "__main__":
    run_interactive()
