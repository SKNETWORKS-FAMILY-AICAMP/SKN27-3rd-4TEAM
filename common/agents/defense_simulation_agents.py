"""LLM/ReAct agents used by the jeonse fraud defense simulation graph."""
from __future__ import annotations

import json
from typing import Any

from common.agents.react_agent_factory import invoke_react_agent
from common.tools.adaptive_rag import adaptive_rag_tool
from common.tools.llm import extract_json_object, ollama_generate


def run_defense_roleplay_agent(stage: dict[str, Any], last_user_message: str | None) -> str | None:
    """Generate the scammer/NPC pressure message for the current scenario stage."""
    return invoke_react_agent(
        name="defense_roleplay_react_agent",
        system_prompt=(
            "너는 전세사기 예방 교육용 롤플레이의 악역 NPC다. "
            "임대인 또는 중개인 역할로 사용자를 서두르게 만들고 위험 신호를 별일 아닌 것처럼 축소한다. "
            "사기 방법을 구체적으로 가르치지 말고, 사용자가 확인해야 할 위험 신호를 간접적으로 드러내는 수준에서만 압박한다. "
            "문서 위조, 법망 회피, 범죄 실행 방법은 절대 설명하지 않는다. "
            "말투는 능글맞고 교묘하며, 대사 끝에 가끔 '끌끌...'이라고 웃는다."
        ),
        user_prompt=(
            f"상황: {stage.get('scenario')}\n"
            f"역할 지시: {stage.get('roleplay_prompt')}\n"
            f"이전 사용자 대응: {last_user_message or '아직 없음'}\n"
            "사용자 대응이 있으면 그 말에 반응해 다시 압박해. 짧은 대사 2~3문장으로 작성해."
        ),
        tools=[adaptive_rag_tool],
        temperature=0.4,
    )


def run_action_interpreter_agent(message: str, stage: dict[str, Any]) -> dict[str, Any]:
    """Interpret a user's natural-language defense action as structured JSON."""
    defenses = [
        {
            "id": defense.get("id"),
            "label": defense.get("label"),
            "keywords": defense.get("keywords", []),
        }
        for defense in stage.get("critical_defenses", [])
    ]
    prompt = f"""
너는 전세사기 방어 훈련의 사용자 행동 해석 에이전트다.
사용자의 자연어 대응을 아래 JSON schema로만 반환해.

필드:
- normalized_actions: critical_defenses의 id 배열. 사용자가 전문용어를 쓰지 않아도 같은 의도면 매핑한다.
- intent_summary: 사용자 의도를 한국어 한 문장으로 요약.
- normalized_user_action: 사용자의 말을 전세사기 방어 행동 용어로 정리.
- unsafe_behavior: 폭행, 협박, 감금, 문서 위조, 허위신고, 절도, 주거침입, 개인정보 탈취, 명백히 비현실 행동이면 true.
- unsafe_reason: unsafe_behavior가 true일 때 이유. 아니면 null.
- abusive_language: 욕설, 모욕, 감정적 폭언이면 true.
- abusive_reason: abusive_language가 true일 때 이유. 아니면 null.
- dangerous_acceptance: 확인 없이 계약/입금/진행/수락하려는 의도면 true.
- confidence: 0.0~1.0

중요:
- 경찰 신고, 계약 중단, 증거 확보, 공식 서류 확인, 전문가 상담은 unsafe가 아니다.
- 위험 수락과 불법/폭력 행동은 분리한다.

현재 단계:
{json.dumps({"title": stage.get("title"), "scenario": stage.get("scenario"), "critical_defenses": defenses, "danger_keywords": stage.get("danger_keywords", [])}, ensure_ascii=False)}

사용자 대응:
{message}
""".strip()
    raw = ollama_generate(prompt, system="JSON만 반환한다.", temperature=0.0)
    data = extract_json_object(raw)
    if not isinstance(data, dict):
        raise ValueError("action interpreter returned non-object JSON")
    return data
