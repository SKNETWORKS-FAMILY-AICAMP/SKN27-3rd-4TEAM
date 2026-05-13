"""LLM/ReAct agents used by the jeonse diagnosis graph."""
from __future__ import annotations

from common.agents.react_agent_factory import invoke_react_agent
from common.tools.adaptive_rag import adaptive_rag_tool
from common.tools.llm import extract_json_object, ollama_generate


def run_special_clause_react_agent(query: str) -> str | None:
    """Analyze contract special clauses with a ReAct agent and RAG tool access."""
    return invoke_react_agent(
        name="special_clause_react_agent",
        system_prompt=(
            "너는 전세계약 특약 위험을 판단하는 LangGraph ReAct Agent다. "
            "반드시 adaptive_rag_tool을 사용해 체크리스트/법령/사례 근거를 확인하고, "
            "위험 특약, 빠진 방어 특약, 수정 권장 방향을 간단히 정리한다."
        ),
        user_prompt=f"계약서 특약을 분석해줘.\n특약:\n{query[:2500]}",
        tools=[adaptive_rag_tool],
        temperature=0.1,
    )


def analyze_special_clauses_with_llm(terms: list[object], context_text: str) -> dict:
    """Return structured special-clause analysis JSON from the diagnosis LLM agent."""
    prompt = f"""
다음 전세계약 특약을 RAG 근거에 기반해 분석하고 JSON 객체만 반환해.
단순 키워드가 아니라 조항의 의미를 판단해.
위험하지 않으면 findings는 빈 배열로 둬.
점수는 HIGH=15, MEDIUM=10, LOW=5 범위에서 보수적으로 정해.

반환 형식:
{{
        "findings": [
            {{
              "code": "CLAUSE_...",
              "title": "짧은 제목",
      "severity": "HIGH|MEDIUM|LOW",
      "score_delta": 15,
      "description": "왜 위험한지",
      "evidence": ["문제 특약 원문"],
      "required_action": "사용자가 요청할 조치"
            }}
          ],
          "missing_defensive_clauses": [
            {{
              "code": "MISSING_...",
              "title": "빠진 방어 특약 제목",
              "severity": "HIGH|MEDIUM|LOW",
              "score_delta": 10,
              "description": "왜 필요한 방어 특약인지",
              "required_action": "추가 또는 수정 요청할 문구"
            }}
          ],
          "recommended_revisions": ["수정 권장 문구 또는 방향"]
        }}

특약:
{chr(10).join(str(term) for term in terms)[:3000]}

RAG 근거:
{context_text[:5000]}
""".strip()
    raw = ollama_generate(
        prompt,
        system="너는 전세계약 특약 위험을 RAG 근거로 구조화하는 분석기다. JSON만 반환한다.",
        temperature=0.0,
    )
    data = extract_json_object(raw)
    if not isinstance(data, dict):
        raise ValueError("special clause agent returned non-object JSON")
    return data
