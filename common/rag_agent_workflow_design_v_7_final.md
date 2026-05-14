# 부동산 법률 AI 주요 그래프 RAG 연동 설계서 v7

> 기준:
> - `rag_agent_workflow_design.md`
> - `rag_agent_workflow_design_v_6_final.md`
> - 현재 구현 현실: 단일 `rag_documents`/PGVector 기반 RAG, `references` 응답 사용, 일부 LangGraph MVP 구현
>
> v7 목표:
> - v6의 방향성은 유지한다.
> - 구현 충돌을 줄이기 위해 호환 규칙을 명확히 둔다.
> - RAG 저장소, Graph DB, Review Supervisor, Agent 책임 범위를 최종 구현 기준으로 확정한다.

---

# 0. v7 핵심 결정

```text
1. RAG 응답 표준 키는 results다.
2. 기존 구현 호환을 위해 references는 alias로 허용한다.
3. Agent 내부 근거 필드는 evidence_refs다.
4. 물리 RAG 테이블은 단일 rag_documents 구조를 허용한다.
5. 단, 논리 테이블명 table은 반드시 보존한다.
6. Graph DB는 graph_context 조회와 관계 검증에 사용한다.
7. Review Supervisor는 v7 구현의 필수 구조다.
8. legal_guardrail은 표현만 완화하며 claims/evidence/graph_context를 수정하지 않는다.
9. friendly_counselor_agent는 법률 판단과 근거 생성을 하지 않는다.
```

---

# 1. 전체 시스템 구조

```text
부동산 법률 AI
├─ 전세계약 진단 Graph
│  ├─ PDF 계약서 입력
│  ├─ 계약 필드 추출
│  ├─ Supervisor 기반 task routing
│  ├─ Agent별 RAG 검색
│  ├─ Review Supervisor 검증
│  ├─ 필요 시 추가 RAG / Graph Context 보강
│  ├─ Risk Judge
│  └─ 위험 진단 리포트 생성
│
└─ 법률상담 Graph
   ├─ 사용자 질문 입력
   ├─ Supervisor 기반 route 결정
   ├─ legal_rag_agent
   ├─ friendly_counselor_agent
   ├─ Review Supervisor 검증
   ├─ legal_guardrail
   └─ 상담 답변 생성
```

---

# 2. 역할 분리 원칙

```text
법률 판단
≠
사람다운 상담
≠
표현 안전화
≠
관계 검증
```

| 역할 | 담당 |
|---|---|
| 법률 근거 검색/claims 생성 | `legal_rag_agent`, 진단 task agents |
| 쉬운 설명/공감/후속 행동 안내 | `friendly_counselor_agent` |
| 품질 검증/재시도 판단 | `review_supervisor` |
| 법률 단정 표현 완화 | `legal_guardrail` |
| 관계 context 조회/논리 검증 | `graph_db` |
| 최종 위험 점수 계산 | `risk_judge` |

---

# 3. RAG 저장소 설계

## 3.1 물리 구조와 논리 구조

v7은 두 구현 방식을 모두 허용한다.

### 허용 A: 물리 테이블 10개

```text
law_documents
case_documents
public_guides
contract_checklists
special_clause_examples
registry_guides
insurance_guides
market_risk_guides
procedure_guides
faq_documents
```

### 허용 B: 단일 물리 테이블 + 논리 table 메타데이터

```text
rag_documents
```

단일 테이블을 사용할 경우 각 chunk는 반드시 아래 값을 가져야 한다.

```json
{
  "table": "law_documents",
  "doc_type": "법령",
  "source_type": "law",
  "domain": ["lease_contract", "tenant_protection"],
  "topic": ["대항력", "전입신고"],
  "jurisdiction": "KR",
  "authority_level": "official"
}
```

중요:

```text
물리 테이블이 rag_documents 하나여도,
Agent 입장에서는 law_documents, case_documents 같은 논리 table을 검색하는 것으로 동작해야 한다.
```

---

## 3.2 표준 논리 RAG 테이블

| 논리 table | 용도 |
|---|---|
| `law_documents` | 법령 원문 및 조문 |
| `case_documents` | 판례 / 결정례 / 분쟁조정례 |
| `public_guides` | 정부/공공기관 가이드 |
| `contract_checklists` | 계약 전후 체크리스트 |
| `special_clause_examples` | 특약 예시 및 위험 특약 데이터 |
| `registry_guides` | 등기부/권리관계 해석 자료 |
| `insurance_guides` | 보증보험 관련 기준 |
| `market_risk_guides` | 전세가율/깡통전세 판단 기준 |
| `procedure_guides` | 법적 절차 안내 |
| `faq_documents` | 쉬운 설명용 FAQ |

---

## 3.3 source_type 규칙

허용:

```text
law
case
dispute_case
public_guide
checklist
faq
market_data
form
insurance
policy
```

주의:

```text
official_policy는 v7 표준 source_type으로 쓰지 않는다.
필요하면 public_guide 또는 policy로 매핑한다.
```

`dispute_case`는 `case_documents`에 저장한다.

---

## 3.4 RAG 검색 요청 표준

```json
{
  "query": "사용자 질문 또는 Agent 생성 검색문",
  "filters": {
    "tables": ["law_documents", "case_documents"],
    "domain": ["deposit_return"],
    "source_type": ["law", "case"],
    "jurisdiction": "KR"
  },
  "top_k": 5,
  "include_graph_context": true
}
```

RAG 서버는 `filters.tables`를 반드시 실제 검색 필터로 반영해야 한다.

단일 `rag_documents` 구조라면:

```text
filters.tables
→ metadata.table 또는 table 컬럼 필터
```

기존 `doc_type` 기반 구현이라면 아래 매핑을 반드시 통과해야 한다.

| logical table | 허용 doc_type 예시 |
|---|---|
| `law_documents` | `법령` |
| `case_documents` | `판례`, `분쟁조정례`, `사례집` 중 판례성 자료 |
| `public_guides` | `가이드`, `사례집`, `정책자료` |
| `contract_checklists` | `체크리스트`, `서식` |
| `special_clause_examples` | `특약`, `서식`, `체크리스트` |
| `registry_guides` | `등기`, `권리관계`, `체크리스트` |
| `insurance_guides` | `보증보험`, `가이드`, `약관` |
| `market_risk_guides` | `시세데이터`, `보고서`, `시장분석` |
| `procedure_guides` | `절차`, `가이드`, `서식` |
| `faq_documents` | `FAQ`, `질의응답` |

---

# 4. RAG 응답 표준

## 4.1 표준 응답

v7 표준 키는 `results`다.

```json
{
  "query": "string",
  "results": [
    {
      "doc_id": "string",
      "title": "string",
      "table": "law_documents",
      "doc_type": "법령",
      "source_type": "law",
      "domain": ["lease_contract"],
      "authority_level": "official",
      "snippet": "검색된 근거 요약",
      "chunk_text": "검색된 원문 일부",
      "score": 0.87,
      "source_url": null,
      "metadata": {}
    }
  ],
  "graph_context": [
    {
      "node": "대항력",
      "relation": "requires",
      "target": "전입신고"
    }
  ]
}
```

---

## 4.2 기존 구현 호환

기존 구현이 `references`를 쓰는 경우를 위해 v7 구현 초기에는 아래를 허용한다.

```json
{
  "results": [...],
  "references": [...],
  "graph_context": [...]
}
```

단, 새 Agent 코드는 반드시 아래 방식으로 읽는다.

```python
raw_results = rag_result.get("results") or rag_result.get("references", [])
state["evidence_refs"] = normalize_evidence_refs(raw_results)
state["graph_context"] = rag_result.get("graph_context", [])
```

금지:

```text
Agent 내부에서 references라는 이름으로 상태를 유지하지 않는다.
```

Agent 내부 표준은 항상:

```text
evidence_refs
```

---

# 5. Evidence 표준

`evidence_refs`의 최소 필드:

```json
{
  "doc_id": "string",
  "title": "string",
  "table": "law_documents",
  "source_type": "law",
  "snippet": "string",
  "score": 0.0,
  "metadata": {}
}
```

`doc_id`가 없으면 다음 순서로 대체한다.

```text
doc_id
→ source_id
→ chunk_id
→ vector_id
→ generated hash
```

---

# 6. Evidence Merge 정책

## 6.1 NEED_MORE_EVIDENCE

추가 검색 결과는 기존 `evidence_refs`를 덮어쓰지 않는다.

```text
existing evidence_refs
+
additional results
→ append-merge
```

## 6.2 merge 규칙

```python
def merge_evidence_refs(existing, additional):
    merged = {}

    for item in existing:
        doc_id = item.get("doc_id") or item.get("source_id") or item.get("chunk_id")
        if doc_id:
            merged[doc_id] = item

    for item in additional:
        doc_id = item.get("doc_id") or item.get("source_id") or item.get("chunk_id")
        if not doc_id:
            continue

        if doc_id not in merged:
            merged[doc_id] = item
        else:
            if float(item.get("score", 0)) > float(merged[doc_id].get("score", 0)):
                merged[doc_id] = item

    return list(merged.values())
```

---

## 6.3 pruning 정책

Review 루프가 반복되면 `evidence_refs`와 `graph_context`가 계속 커질 수 있다.
따라서 merge 이후에는 반드시 pruning을 수행한다.

기본 제한:

```python
MAX_EVIDENCE_REFS = 30
MAX_GRAPH_CONTEXT = 20
```

원칙:

```text
1. current_task와 관련 있는 evidence/context를 우선 유지한다.
2. score가 높은 evidence를 우선 유지한다.
3. authority_level이 official/court/public_institution인 근거를 우선 유지한다.
4. 중복 doc_id/chunk_id/context triple은 제거한다.
5. 제한 수를 넘는 항목은 prompt에 넣지 않는다.
```

예시:

```python
def prune_evidence_refs(items, current_task, limit=30):
    ranked = sorted(
        items,
        key=lambda item: (
            current_task in str(item.get("metadata", {})),
            item.get("authority_level") in {"official", "court", "public_institution"},
            float(item.get("score", 0)),
        ),
        reverse=True,
    )
    return ranked[:limit]


def prune_graph_context(items, current_task, limit=20):
    seen = set()
    unique = []
    for item in items:
        key = (item.get("node"), item.get("relation"), item.get("target"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:limit]
```

금지:

```text
Review 루프마다 evidence_refs/graph_context를 무제한 append하지 않는다.
```

---

# 7. Graph DB 설계

## 7.1 역할

v7에서 Graph DB는 검증 전용으로 제한하지 않는다.

```text
Graph DB 역할:
1. graph_context 조회
2. 위험요소/법령/판례/절차 관계 조회
3. Agent claims의 관계적 타당성 검증
```

즉:

```text
Vector RAG
→ 문서 검색

Graph DB
→ 관계 context 조회 + 관계 검증
```

---

## 7.2 Graph Context 표준

```json
{
  "node": "근저당",
  "relation": "weakens",
  "target": "보증금회수안정성"
}
```

최소 필드:

```text
node
relation
target
```

선택 필드:

```text
severity
confidence
source
metadata
```

---

## 7.3 Neo4j 라벨 호환 정책

v7 문서의 추상 노드명과 기존 Neo4j 라벨은 매핑 가능해야 한다.

| v7 abstract node | Neo4j label 예시 |
|---|---|
| `risk` | `RiskFactor` |
| `legal_concept` | `LegalConcept` |
| `procedure` | `Procedure` |
| `document` | `Law`, `Case`, `DocumentCategory` |
| `requirement` | `LegalConcept`, `Procedure`, `CheckItem` |
| `contract_field` | `ContractField` 또는 metadata |
| `institution` | `Institution` 또는 metadata |

기존 Neo4j 라벨이 이미 존재한다면 무리하게 갈아엎지 않는다.

```text
Cypher 구현은 실제 Neo4j 라벨 기준으로 작성한다.
문서/Agent prompt에서는 v7 abstract node를 사용할 수 있다.
```

---

## 7.4 권장 Edge Types

v7 abstract edge:

```text
requires
precedes
blocks
strengthens
weakens
related_to
resolved_by
verified_by
regulated_by
evidenced_by
defined_in
belongs_to
```

Neo4j 실제 관계명이 대문자라면 아래처럼 매핑한다.

| v7 abstract edge | Neo4j relation 예시 |
|---|---|
| `requires` | `REQUIRES` |
| `related_to` | `RELATED_TO` |
| `regulated_by` | `REGULATED_BY` |
| `evidenced_by` | `EVIDENCED_BY` |
| `defined_in` | `DEFINED_IN` |
| `belongs_to` | `BELONGS_TO` |
| `verified_by` | `VERIFIED_BY` |
| `resolved_by` | `RESOLVED_BY` |

---

# 8. Review Supervisor

## 8.1 목적

Review Supervisor는 Agent 결과가 다음 조건을 만족하는지 검증한다.

```text
1. 질문/계약 task에 답했는가
2. evidence_refs가 충분한가
3. claims가 evidence와 충돌하지 않는가
4. graph_context가 필요한데 비어 있지 않은가
5. 법률 단정이 과하지 않은가
6. 상담 agent가 법률 판단을 새로 만들지 않았는가
```

---

## 8.2 ReviewStatus

```python
class ReviewStatus(str, Enum):
    PASS = "PASS"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    NEED_MORE_EVIDENCE = "NEED_MORE_EVIDENCE"
    NEED_GRAPH_CONTEXT = "NEED_GRAPH_CONTEXT"
    NEED_CLARIFICATION = "NEED_CLARIFICATION"
    NEED_COUNSELOR_REWRITE = "NEED_COUNSELOR_REWRITE"
    FAIL = "FAIL"
```

---

## 8.2.1 ReviewResult structured output

Review Supervisor는 반드시 structured output을 사용한다.

허용:

```python
with_structured_output(ReviewResult)
```

또는:

```python
PydanticOutputParser(ReviewResult)
```

금지:

```text
Review Supervisor의 자연어 응답을 직접 라우팅 조건으로 사용하지 않는다.
```

필수 스키마:

```python
class ReviewResult(BaseModel):
    status: ReviewStatus
    reason: str
    required_action: str | None = None
    missing_evidence_query: str | None = None
    graph_context_query: str | None = None
    target_agent: str | None = None
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
```

이유:

```text
Review Router는 PASS, NEED_MORE_EVIDENCE 같은 enum 값으로 분기한다.
자연어 출력이 섞이면 라우팅이 깨진다.
```

---

## 8.3 필수 State

진단 Graph와 상담 Graph는 Review를 쓰는 구간에서 최소한 아래 state를 가진다.

```python
{
    "current_task": "...",
    "current_agent": "...",
    "pending_tasks": [...],
    "completed_tasks": [...],
    "review_count": 0,
    "max_review_count": 2,
    "review_result": {},
    "claims": [],
    "legal_points": [],
    "evidence_refs": [],
    "graph_context": []
}
```

---

## 8.4 review_count 정책

```python
if review_result.status != "PASS":
    state["review_count"] += 1
```

`PASS`인 경우:

```python
state["review_count"] = 0
state["completed_tasks"].append(state["current_task"])
```

다음 task 진입 시:

```python
state["current_task"] = next_task
state["current_agent"] = agent_for(next_task)
state["review_count"] = 0
```

---

## 8.5 Review Router

```python
def route_after_review(state):
    status = state["review_result"]["status"]
    count = state.get("review_count", 0)
    max_count = state.get("max_review_count", 2)
    current_agent = state.get("current_agent")

    if status == "PASS":
        return "supervisor"

    if count >= max_count:
        return "safe_fallback"

    if status == "REVISION_REQUIRED":
        return current_agent

    if status == "NEED_MORE_EVIDENCE":
        return "extra_rag_search"

    if status == "NEED_GRAPH_CONTEXT":
        return "graph_context_node"

    if status == "NEED_CLARIFICATION":
        return "missing_input_report"

    if status == "NEED_COUNSELOR_REWRITE":
        return "friendly_counselor_agent"

    return "safe_fallback"
```

---

## 8.6 추가 RAG 이후 흐름

`NEED_MORE_EVIDENCE` 이후에는 반드시 원래 Agent를 재실행한다.

```text
review
→ NEED_MORE_EVIDENCE
→ extra_rag_search
→ merge_evidence_refs
→ current_agent 재실행
→ review
```

이유:

```text
추가 근거만 붙이고 final로 가면 claims가 새 evidence를 반영하지 못한다.
```

---

## 8.7 Graph Context 보강 이후 흐름

```text
review
→ NEED_GRAPH_CONTEXT
→ graph_context_node
→ current_agent 재실행 또는 review 재검증
```

기본값:

```text
graph_context가 claims 생성에 영향을 주는 task라면 current_agent 재실행
단순 관계 검증 누락이라면 review 재검증
```

---

# 9. 전세계약 진단 Graph

## 9.1 기본 흐름

```text
START
→ contract_intake
→ contract_parser
→ contract_field_extractor
→ contract_supervisor
→ task router
→ task agent
→ contract_review_node
→ retry / extra_rag_search / graph_context_node
→ contract_supervisor
→ risk_judge
→ report_writer
→ END
```

---

## 9.2 Task Agents

필수 Agent:

```text
special_clause_agent
ownership_risk_agent
market_risk_agent
insurance_risk_agent
required_check_agent
legal_basis_agent
```

초기 구현에서 모든 Agent가 완성되지 않아도 된다.

단, 미구현 Agent는 아래 중 하나를 명확히 반환해야 한다.

```json
{
  "status": "NOT_IMPLEMENTED",
  "task": "market_risk",
  "reason": "market_risk_agent is scheduled but not implemented"
}
```

미구현 Agent를 조용히 생략하지 않는다.

---

## 9.3 Diagnosis Task Queue

`contract_supervisor`는 boolean 플래그만 만들지 않고 task queue를 생성한다.

```python
pending_tasks = [
    "special_clause",
    "ownership_risk",
    "market_risk",
    "insurance_risk",
    "required_check",
    "legal_basis",
]
```

완료된 task는 `completed_tasks`에 들어간다.

```text
pending_tasks - completed_tasks = 남은 task
```

---

## 9.4 Agent별 RAG 범위

| Agent | tables |
|---|---|
| `special_clause_agent` | `special_clause_examples`, `law_documents`, `public_guides`, `case_documents` |
| `ownership_risk_agent` | `registry_guides`, `contract_checklists`, `law_documents`, `case_documents`, `public_guides` |
| `market_risk_agent` | `market_risk_guides`, `public_guides`, `case_documents` |
| `insurance_risk_agent` | `insurance_guides`, `public_guides`, `law_documents` |
| `required_check_agent` | `contract_checklists`, `public_guides`, `registry_guides`, `insurance_guides` |
| `legal_basis_agent` | `law_documents`, `case_documents`, `public_guides`, `procedure_guides` |

---

## 9.5 Risk Judge

`risk_judge`는 직접 RAG 검색을 하지 않는다.

입력:

```text
task_results: dict[str, AgentResult]
claims
evidence_refs
graph_context
review status
```

`task_results`는 반드시 Agent별 결과를 보존한다.

```python
task_results = {
    "special_clause": AgentResult(...),
    "ownership_risk": AgentResult(...),
    "market_risk": AgentResult(...),
}
```

표준 `AgentResult`:

```python
class AgentResult(BaseModel):
    task: str
    agent: str
    status: Literal["COMPLETE", "PARTIAL", "NOT_IMPLEMENTED", "FAILED"]
    claims: list[Claim] = []
    legal_points: list[str] = []
    evidence_refs: list[dict] = []
    graph_context: list[dict] = []
    risk_items: list[dict] = []
    recommendations: list[str] = []
    review_status: str | None = None
    metadata: dict = {}
```

출력:

```text
risk_score
risk_level
risk_factors
summary
```

조건:

```text
Review PASS 또는 safe_fallback 처리되지 않은 task는 최종 점수에 강하게 반영하지 않는다.
risk_judge는 claim/task 출처가 없는 위험 판단을 생성하지 않는다.
```

---

# 10. 법률상담 Graph

## 10.1 기본 흐름

```text
START
→ legal_intake
→ legal_supervisor
   ├─ legal_rag_agent
   ├─ friendly_counselor_agent
   └─ BOTH
→ legal_review_node
→ retry / extra_rag_search / graph_context_node / counselor_rewrite
→ legal_guardrail
→ consultation_report
→ END
```

---

## 10.2 Route

```text
LEGAL_RAG
COUNSELOR
BOTH
CLARIFICATION
```

`BOTH` 순서:

```text
legal_rag_agent
→ friendly_counselor_agent
→ legal_review_node
→ legal_guardrail
→ consultation_report
```

---

# 11. legal_rag_agent

## 11.1 역할

```text
- 법률 근거 검색
- claims 생성
- legal_points 생성
- answer_draft 생성
- evidence_refs 생성
- graph_context 요청
```

---

## 11.2 출력

```json
{
  "claims": [],
  "legal_points": [],
  "answer_draft": "string",
  "evidence_refs": [],
  "graph_context": [],
  "confidence": "LOW|MEDIUM|HIGH"
}
```

---

## 11.2.1 claims와 legal_points의 차이

`claims`와 `legal_points`는 서로 다른 목적을 가진다.

### claims

`claims`는 Review와 evidence 연결의 대상이 되는 최종 주장 단위다.

```json
{
  "claim_id": "claim_001",
  "task": "ownership_risk",
  "text": "선순위 근저당이 보증금 회수 안정성을 낮출 수 있다.",
  "evidence_ids": ["law_001", "case_003"],
  "graph_context_ids": ["graph_001"],
  "confidence": "MEDIUM"
}
```

규칙:

```text
1. Review Supervisor는 claims를 검증한다.
2. claims는 evidence_refs 또는 graph_context와 연결되어야 한다.
3. 근거 없는 claims는 PASS될 수 없다.
4. risk_judge는 claims를 위험 판단의 기본 단위로 사용한다.
```

### legal_points

`legal_points`는 사용자 설명/UI/상담 문장 생성을 위한 핵심 포인트다.

```json
[
  "전입신고는 대항력 취득에 중요합니다.",
  "확정일자는 우선변제권 판단에 필요합니다."
]
```

규칙:

```text
1. legal_points는 claims보다 짧고 설명 친화적이다.
2. friendly_counselor_agent는 legal_points를 받아 쉬운 말로 풀어쓴다.
3. legal_points만으로 법률 판단을 확정하지 않는다.
4. Review의 핵심 대상은 legal_points가 아니라 claims다.
```

---

## 11.3 질문 유형별 RAG 범위

| question_type | tables |
|---|---|
| `DEPOSIT_RETURN` | `law_documents`, `case_documents`, `procedure_guides`, `public_guides` |
| `REGISTRY_RISK` | `registry_guides`, `law_documents`, `case_documents`, `public_guides` |
| `DEPOSIT_INSURANCE` | `insurance_guides`, `public_guides`, `law_documents` |
| `PROCEDURE_GUIDE` | `procedure_guides`, `public_guides`, `law_documents` |
| `SIMPLE_EXPLANATION` | `faq_documents`, `public_guides` |
| `GENERAL` | `law_documents`, `case_documents`, `public_guides` |

---

# 12. friendly_counselor_agent

## 12.1 역할

```text
- 쉬운 말 재설명
- 감정 응대
- 사용자 상황 정리
- 후속 행동 안내
- 추가 질문 생성
```

---

## 12.2 금지

```text
- 새로운 법률 판단 생성
- 새로운 claims 생성
- 새로운 evidence_refs 생성
- RAG 재검색
- graph_context 수정
- risk_score 수정
```

---

## 12.3 입력 제한

`friendly_counselor_agent`에 전체 state를 넘기지 않는다.

허용 입력:

```json
{
  "user_question": "string",
  "intent": "string",
  "question_type": "string",
  "legal_points": [],
  "answer_draft": "string",
  "evidence_titles": [],
  "followup_questions": [],
  "conversation_history": []
}
```

이유:

```text
전체 state를 넘기면 counselor가 claims/evidence/graph_context를 실수로 수정할 위험이 있다.
```

---

## 12.4 Optional FAQ RAG

기본적으로 RAG를 사용하지 않는다.

예외:

```text
SIMPLE_EXPLANATION
FAQ 기반 설명
```

이 경우에도 `faq_documents`, `public_guides`만 허용한다.

---

# 13. legal_guardrail

## 13.1 역할

```text
- 법률 단정 표현 완화
- 과도한 확신 표현 완화
- 변호사/기관 상담 안내 추가
- disclaimer 추가
```

---

## 13.2 금지

```text
- claims 수정
- claims 삭제
- evidence_refs 수정
- evidence_refs 삭제
- graph_context 수정
- graph_context 삭제
- risk_score 수정
```

`legal_guardrail`은 Review PASS 이후 실행되므로 근거 구조를 바꾸면 안 된다.

---

# 14. Safe Fallback

Review 재시도 한도를 넘거나 필수 근거가 없으면 safe fallback을 반환한다.

```json
{
  "status": "SAFE_FALLBACK",
  "fallback_level": "LOW|MEDIUM|HIGH",
  "reason": "근거가 충분하지 않아 최종 판단을 제공하지 않습니다.",
  "recommended_next_step": "추가 문서 업로드 또는 전문가 상담 권장"
}
```

## 14.1 fallback_level

```text
LOW
→ 추가 자료 확인이 필요하지만 즉시 위험 단정은 어렵다.

MEDIUM
→ 근거 부족으로 판단 신뢰도가 낮다. 추가 자료 또는 재검색이 필요하다.

HIGH
→ 법률/금전 리스크가 클 수 있으므로 전문가 상담을 강하게 권장한다.
```

선택 기준:

```text
LOW: evidence 일부 존재, claims 일부만 불확실
MEDIUM: 핵심 evidence 부족, graph_context 불충분
HIGH: 보증금 회수/권리관계/소송 가능성 등 고위험 이슈인데 근거 검증 실패
```

금지:

```text
근거가 부족한 상태에서 확정적 법률 판단을 생성하지 않는다.
```

---

# 15. 구현 우선순위

## 15.1 즉시 구현

```text
1. RAG 응답 results/references 호환
2. evidence_refs normalize 함수
3. metadata.table 또는 table 컬럼 보존
4. filters.tables → 실제 검색 필터 적용
5. graph_context 표준 유지
```

## 15.2 다음 구현

```text
6. Review Supervisor node 추가
7. review_count/current_task/completed_tasks 상태 추가
8. extra_rag_search → current_agent 재실행 루프
9. graph_context_node 추가
10. legal_guardrail 불변성 보장
11. ReviewResult structured output 강제
12. evidence_refs/graph_context pruning 적용
```

## 15.3 확장 구현

```text
13. market_risk_agent
14. insurance_risk_agent
15. required_check_agent
16. legal_basis_agent
17. Graph DB claims 검증 고도화
```

---

# 16. 구현 체크리스트

```text
[ ] RAG 응답에 results가 존재한다.
[ ] 기존 references 응답도 호환된다.
[ ] Agent 내부 상태는 evidence_refs를 사용한다.
[ ] rag_documents를 쓰더라도 table 메타데이터가 보존된다.
[ ] filters.tables가 실제 검색 필터로 반영된다.
[ ] graph_context는 node/relation/target 형태다.
[ ] Review Supervisor가 PASS/재시도/추가근거/GraphContext/실패를 구분한다.
[ ] NEED_MORE_EVIDENCE 이후 current_agent를 재실행한다.
[ ] PASS 이후 completed_tasks에 현재 task를 기록한다.
[ ] friendly_counselor_agent는 claims/evidence를 만들지 않는다.
[ ] legal_guardrail은 근거 구조를 수정하지 않는다.
[ ] 미구현 Agent는 조용히 생략하지 않고 NOT_IMPLEMENTED를 반환한다.
[ ] claims와 legal_points가 분리되어 있다.
[ ] claims는 evidence_ids 또는 graph_context_ids와 연결된다.
[ ] Review Supervisor는 structured output을 강제한다.
[ ] evidence_refs는 MAX_EVIDENCE_REFS 이하로 pruning된다.
[ ] graph_context는 MAX_GRAPH_CONTEXT 이하로 pruning된다.
[ ] risk_judge는 task_results: dict[str, AgentResult]를 입력으로 받는다.
[ ] safe_fallback은 fallback_level을 포함한다.
```

---

# 17. 최종 요약

```text
v7은 v6의 방향을 유지하되,
현재 구현과 충돌하던 지점을 호환 가능한 구현 규칙으로 정리한다.

RAG는 results를 표준으로 사용한다.
references는 기존 구현 호환용 alias로 허용한다.

RAG 물리 구조는 rag_documents 단일 테이블이어도 된다.
하지만 논리 table 값은 반드시 보존해야 한다.

Graph DB는 검증 전용이 아니라,
graph_context 조회와 관계 검증을 모두 담당한다.

Review Supervisor는 Agent 결과를 검증하고,
필요하면 추가 RAG, Graph Context 보강, Agent 재실행을 유도한다.

claims는 검증 가능한 주장 단위이고,
legal_points는 사용자 설명용 핵심 포인트다.

법률 판단은 legal_rag_agent와 task agents가 담당한다.
friendly_counselor_agent는 설명과 공감만 담당한다.
legal_guardrail은 표현만 안전하게 만든다.

운영 안정성을 위해 structured output, pruning, fallback_level을 필수로 적용한다.
```

이 문서를 기준으로 구현한다.
