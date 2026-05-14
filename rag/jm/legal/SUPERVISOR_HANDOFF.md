# legal agent supervisor 전달 문서

전세사기 방지 프로젝트의 법률 전용 RAG 에이전트를 supervisor에 연결하기 위한 제출용 문서입니다. 이 에이전트는 PostgreSQL pgvector에 적재된 문서 중 법령, 판례, 표준계약서, 법률 절차 관련 chunk를 검색합니다.

## 목적

- 사용자 질문 중 법률 영역에 해당하는 질문을 처리합니다.
- 법령, 시행령, 민법, 특별법, 판례, 표준계약서, 법률 상담 절차 문서를 근거로 사용합니다.
- `docs/pdf/case`, 부동산 거래 테이블은 사용하지 않습니다.

## Supervisor 연동 계약

Supervisor는 법률 질문이라고 판단한 경우 아래 함수만 호출하면 됩니다.

```python
from rag.jm.legal import run_legal_agent

result = run_legal_agent(
    question="임차인이 대항력을 갖추려면 무엇이 필요해?",
    k=5,
)
```

## Input

```python
{
    "question": "사용자 질문 문자열",
    "k": 5
}
```

- `question`: 필수값입니다. 사용자의 법률 질문을 그대로 넘깁니다.
- `k`: 선택값입니다. 검색할 법률 문서 chunk 개수입니다. 기본값은 `5`입니다.

## Output

`run_legal_agent()`는 `LegalAgentResult`를 반환합니다.

```python
{
    "answer": "최종 법률 상담 보조 답변",
    "hits": [
        {
            "content": "검색된 법률 문서 chunk 내용",
            "metadata": {
                "source": "docs/pdf\\law\\주택임대차보호법...",
                "file_name": "주택임대차보호법...",
                "page": 1
            },
            "score": 0.41
        }
    ],
    "review_passed": True,
    "review_message": "PASS"
}
```

- `answer`: 사용자에게 전달할 수 있는 법률 상담 보조 답변입니다.
- `hits`: 답변 생성에 사용된 법률 문서 근거 목록입니다.
- `review_passed`: 답변이 최소 검토 기준을 통과했는지 여부입니다.
- `review_message`: `PASS` 또는 보완이 필요한 이유입니다.

## 법률 전용 Tools

Supervisor가 LangChain/LangGraph tool binding 방식으로 쓰고 싶다면 `LEGAL_TOOLS`를 사용하면 됩니다.

```python
from rag.jm.legal import LEGAL_TOOLS
```

현재 포함된 tool:

- `legal_document_search_tool`: 법령, 판례, 표준계약서, 절차 문서 전체에서 법률 근거를 검색합니다.
- `law_article_search_tool`: 사례집과 표준계약서를 제외하고 법령 조항 중심으로 검색합니다.
- `judgement_search_tool`: 판례 문서 중심으로 검색합니다.
- `standard_contract_search_tool`: 주택임대차표준계약서 중심으로 검색합니다.
- `legal_procedure_search_tool`: 임차권등기명령, 전세피해 신청 같은 법률 절차 중심으로 검색합니다.
- `legal_answer_review_tool`: 답변 초안에 근거, 확인 사항, 법률 자문 한계가 있는지 검토합니다.

## Supervisor 처리 흐름 예시

```python
from rag.jm.legal import run_legal_agent


def call_legal_agent(question: str) -> dict:
    """Supervisor에서 legal agent를 호출하고 다음 노드로 넘길 값을 정리합니다."""

    result = run_legal_agent(question=question, k=5)
    return {
        "agent": "legal_agent",
        "answer": result.answer,
        "review_passed": result.review_passed,
        "review_message": result.review_message,
        "sources": [
            {
                "source": hit.metadata.get("source"),
                "file_name": hit.metadata.get("file_name"),
                "page": hit.metadata.get("page"),
                "score": hit.score,
            }
            for hit in result.hits
        ],
    }
```

Supervisor 권장 처리:

- `review_passed == True`: `final_answer_writer`로 전달합니다.
- `review_passed == False`: 추가 검색, 재생성, 또는 사용자에게 추가 정보 요청을 선택합니다.

## 실행 방법

프로젝트 루트에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m rag.jm.legal.run_legal --question "임차인이 대항력을 갖추려면 무엇이 필요해?" --k 5
```

통합 CLI에서도 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m rag.jm.cli legal --query "임차인이 대항력을 갖추려면 무엇이 필요해?" --k 5
```

## 주의 사항

- OpenAI 모델을 사용할 경우 `.env`에 `OPENAI_API_KEY`가 필요합니다.
- 현재 검색 대상은 법령, 판례, 표준계약서, 법률 절차 문서로 제한됩니다.
- `docs/pdf/case`의 일반 사례/예방 문서는 검색하지 않습니다.
