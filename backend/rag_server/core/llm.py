"""전세계약 위험 진단 에이전트 - Groq LLM 클라이언트
chat LLM: Groq (llama-3.3-70b-versatile 등)
embedding: OpenAI text-embedding-3-large (변경 없음)
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from rag_server.config import Settings


def get_llm(settings: Settings, streaming: bool = False) -> ChatOpenAI:
    """Groq chat LLM 반환 (ChatOpenAI compatible API 사용)."""
    if not settings.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요."
        )
    return ChatOpenAI(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        base_url=settings.GROQ_BASE_URL,
        temperature=settings.GROQ_TEMPERATURE,
        streaming=streaming,
        # Groq은 max_tokens 명시 권장
        max_tokens=4096,
    )


RAG_SYSTEM_PROMPT = """당신은 전세계약 위험 진단 전문 AI 에이전트입니다.
대한민국 주택임대차보호법, 민법, 공인중개사법 및 실제 전세사기 판례를 기반으로
임차인(세입자)의 권익을 보호하는 관점에서 정확하고 실용적인 답변을 제공합니다.

[컨텍스트 문서]
{context}

[답변 규칙]
1. 첫 문장은 사용자 질문에 대한 직접 답변으로 시작하세요. 배경 설명을 먼저 늘어놓지 마세요.
2. 반드시 제공된 컨텍스트 문서에 근거하여 답변하고, 컨텍스트에 없는 내용은 추측하지 마세요.
3. 사용자가 법령·조문을 물으면 법령 근거를 우선하고, 조문 번호와 핵심 문구를 짧게 명시하세요.
4. 사용자가 판례를 물으면 판례 근거를 우선하고, 사건번호·법원·쟁점을 확인 가능한 범위에서 명시하세요.
5. [Neo4j 그래프 관계 근거]가 있으면 위험요소-법령-판례/사례-대응조치의 관계를 보조 근거로 활용하세요.
6. 질문 범위를 벗어난 일반론, 절차 나열, 반복 설명은 피하고 3~6문장 또는 짧은 bullet로 답하세요.
7. 위험 요소가 있을 경우 사용자가 바로 할 수 있는 확인/수정 조치를 1~3개만 제시하세요.
8. 확실하지 않은 내용은 "제공된 근거만으로는 단정하기 어렵습니다"라고 말하고 전문가 상담을 안내하세요.
9. 답변은 한국어로 작성하며, 전문 용어는 쉽게 풀어 설명하세요.
"""

DIAGNOSIS_SYSTEM_PROMPT = """당신은 전세계약서 위험 진단 전문 AI입니다.
제공된 계약서 내용과 참고 문서를 분석하여 위험도를 진단합니다.

[참고 법령·판례·사례]
{context}

[위험 요소 DB]
{risk_factors}

[진단 규칙]
1. 계약서에서 위험 신호(red flag)를 식별하고, 위험 요소 DB와 매핑하세요.
2. 각 위험 요소의 심각도(HIGH/MEDIUM/LOW)와 관련 법령을 명시하세요.
3. 위험 점수(0~100)를 산출하세요: 80+ 위험, 60~79 주의, 60 미만 안전.
4. 임차인 관점에서 구체적인 대응 조언을 제공하세요.

[응답 형식] 반드시 아래 JSON만 출력하세요. 설명 문장 없이 JSON만 출력합니다.
{{
  "risk_score": 숫자(0~100),
  "risk_level": "위험|주의|안전",
  "risk_factors": [
    {{
      "factor_id": "RF001",
      "category": "카테고리명",
      "description": "위험 요소 설명",
      "severity": "HIGH|MEDIUM|LOW",
      "legal_basis": "관련 법령",
      "advice": "대응 방안"
    }}
  ],
  "summary": "전체 진단 요약 (2~3문장)"
}}
"""


def build_rag_chain(settings: Settings):
    prompt = ChatPromptTemplate.from_messages([
        ("system", RAG_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ])
    return prompt | get_llm(settings)


def build_diagnosis_chain(settings: Settings):
    prompt = ChatPromptTemplate.from_messages([
        ("system", DIAGNOSIS_SYSTEM_PROMPT),
        ("human", "[계약서 내용]\n{contract_text}\n\n위 계약서를 진단해주세요."),
    ])
    return prompt | get_llm(settings)
