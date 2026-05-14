# RAG Backend Update Spec for v7 Common Integration

작성일: 2026-05-14

대상:
- v7 설계 문서: `C:\Users\cubix\Downloads\rag_agent_workflow_design_v_7_final.md`
- 수정된 common 패키지: `C:\Users\cubix\Downloads\common\common`
- 현재 기준 브랜치 RAG 구현: `backend/rag_server`

목적:
v7 설계와 수정된 `common` 파일이 RAG 서버와 정상적으로 맞물리도록 RAG 백엔드에서 수정 또는 업데이트해야 할 항목을 구현 명세 수준으로 정리한다.

---

## 1. 최종 결론

현재 RAG 서버는 기본적인 pgvector 검색, `/api/v1/rag/retrieve`, `/api/v1/chat/query`, Neo4j `graph_context` 반환 골격은 존재한다.

하지만 v7 `common`과 100% 안정적으로 맞추려면 아래 항목은 반드시 업데이트해야 한다.

필수 수정:
1. `/api/v1/rag/retrieve` 응답에 `results`를 표준 키로 추가한다.
2. `references`는 당분간 alias로 유지한다.
3. `RetrieveRequest`에 `include_graph_context`를 명시 필드로 추가한다.
4. `RetrieveResponse`에 `graph_context`를 추가한다.
5. RAG 결과 item마다 `table` 또는 `metadata.table`을 반드시 포함한다.
6. `filters.tables`, `filters.doc_type`, `filters.domain`, `filters.source_type`를 실제 검색 필터로 반영한다.
7. `doc_type`이 list일 때도 정상 동작하도록 VectorStore 필터를 확장한다.
8. Graph DB 결과는 항상 `[{node, relation, target}]` 형태로 반환한다.
9. 검색 결과의 `score`와 `relevance_score`를 둘 다 호환되게 반환한다.
10. RAG 테스트를 v7 계약 기준으로 새로 작성한다.

권장 수정:
1. `rag_documents.metadata.table` 백필 migration을 추가한다.
2. `metadata.domain`, `metadata.source_type`, `metadata.authority_level`을 보강한다.
3. `langchain_pg_embedding.cmetadata`에도 동일 metadata가 들어가도록 ingestion을 수정한다.
4. `/api/v1/chat/query`도 `results` alias를 반환하게 맞춘다.
5. Graph DB relation 이름을 v7 abstract relation과 매핑하는 normalization 함수를 둔다.

---

## 2. common이 RAG 서버에 기대하는 계약

수정된 `common`은 RAG 서버를 다음 순서로 호출한다.

1. 우선 호출:

```http
POST /api/v1/rag/retrieve
```

2. 실패 시 fallback 호출:

```http
POST /api/v1/chat/query
```

`common.tools.adaptive_rag._retrieve_body()`가 보내는 요청 body는 아래 구조다.

```json
{
  "task_type": "legal_basis",
  "query": "검색 질의",
  "top_k": 5,
  "filters": {
    "tables": ["law_documents", "case_documents", "public_guides"],
    "doc_type": ["law", "case", "public_guide"],
    "domain": ["lease_contract", "tenant_protection"],
    "source_type": ["law", "case", "public_guide"],
    "include_graph_context": true,
    "session_id": "diag-..."
  },
  "include_graph_context": true
}
```

`common`이 받기를 기대하는 표준 응답은 아래다.

```json
{
  "task_type": "legal_basis",
  "query": "검색 질의",
  "results": [
    {
      "doc_id": "law-001-3",
      "source_id": "law-001",
      "title": "주택임대차보호법 제3조",
      "table": "law_documents",
      "doc_type": "law",
      "source_type": "law",
      "domain": ["tenant_protection"],
      "authority_level": "official",
      "snippet": "짧은 인용/요약",
      "chunk_text": "실제 근거 chunk",
      "score": 0.87,
      "relevance_score": 0.87,
      "source_url": null,
      "metadata": {
        "table": "law_documents",
        "doc_type": "law",
        "source_type": "law",
        "domain": ["tenant_protection"],
        "authority_level": "official",
        "chunk_index": 3
      }
    }
  ],
  "references": [
    "results와 동일한 배열. 초기 호환용 alias"
  ],
  "graph_context": [
    {
      "node": "대항력",
      "relation": "requires",
      "target": "전입신고"
    }
  ],
  "doc_types_searched": ["law", "case", "public_guide"],
  "total_retrieved": 1
}
```

중요:
- v7 표준은 `results`다.
- `references`는 기존 구현 호환을 위한 alias다.
- Agent 내부 상태에는 `references`라는 이름을 쓰지 않는다. `common`은 이를 `evidence_refs`로 normalize한다.

---

## 3. 현재 RAG 서버에서 확인된 차이

### 3.1 `/api/v1/rag/retrieve`가 `references`만 반환

현재 파일:

```text
backend/rag_server/api/routes/retrieve.py
```

현재 `RetrieveResponse`는 대략 아래 구조다.

```python
class RetrieveResponse(BaseModel):
    task_type: str
    query: str
    references: list[dict[str, Any]]
    doc_types_searched: list[str]
    total_retrieved: int
```

v7/common 기준으로는 아래처럼 바뀌어야 한다.

```python
class RetrieveResponse(BaseModel):
    task_type: str
    query: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    references: list[dict[str, Any]] = Field(default_factory=list)
    graph_context: list[dict[str, Any]] = Field(default_factory=list)
    doc_types_searched: list[str] = Field(default_factory=list)
    total_retrieved: int = 0
```

반환 시:

```python
items = [normalize_reference(ref) for ref in references]

return RetrieveResponse(
    task_type=body.task_type,
    query=body.query,
    results=items,
    references=items,
    graph_context=graph_context,
    doc_types_searched=doc_types,
    total_retrieved=len(items),
)
```

---

### 3.2 `include_graph_context` 요청 필드가 명시되어 있지 않음

`common`은 요청 body top-level에 `include_graph_context`를 보낸다.

현재 `RetrieveRequest`에는 이 필드가 없다. Pydantic 설정에 따라 무시될 수 있으므로 명시적으로 추가해야 한다.

수정:

```python
class RetrieveRequest(BaseModel):
    task_type: str
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict[str, Any] = Field(default_factory=dict)
    session_id: str = "rag-retrieve"
    include_graph_context: bool = True
```

그리고 실제 graph 조회 조건은 아래처럼 잡는다.

```python
include_graph = bool(
    body.include_graph_context
    and body.filters.get("include_graph_context", True)
)
```

---

### 3.3 RAG 결과 item에 `table`/`metadata.table` 보장이 필요

v7 설계는 물리 테이블이 단일 `rag_documents`여도 logical table을 반드시 보존한다.

즉 RAG 결과 item에는 아래 둘 중 최소 하나가 있어야 한다.

```json
{
  "table": "law_documents"
}
```

또는:

```json
{
  "metadata": {
    "table": "law_documents"
  }
}
```

현재 common은 `normalize_evidence_refs()`에서 아래 순서로 table을 찾는다.

```python
item.table
metadata.table
fallback_table
doc_type 기반 추론
```

doc_type 기반 추론은 안전망일 뿐이다. RAG DB/ingestion 단계에서 `metadata.table`을 넣어주는 것이 정답이다.

---

## 4. logical table 표준

v7/common 기준으로 RAG가 지원해야 하는 logical table은 아래다.

| logical table | 용도 |
|---|---|
| `law_documents` | 법령, 조문, 공식 법률 근거 |
| `case_documents` | 판례, 분쟁조정례, 사례집 |
| `public_guides` | 공공기관 가이드, 설명자료 |
| `contract_checklists` | 계약 전 체크리스트, 확인 서류 |
| `special_clause_examples` | 특약 예시, 표준계약서, 서식 |
| `registry_guides` | 등기부, 권리관계, 선순위 권리 |
| `insurance_guides` | HUG/HF/SGI 보증보험 관련 자료 |
| `market_risk_guides` | 시세, 깡통전세, 시장 위험 자료 |
| `procedure_guides` | 내용증명, 임차권등기명령, 지급명령 등 절차 |
| `faq_documents` | 쉬운 설명/FAQ |

RAG ingestion 시 각 chunk metadata에 최소 아래 값을 넣는다.

```json
{
  "table": "law_documents",
  "doc_type": "law",
  "source_type": "law",
  "domain": ["lease_contract", "tenant_protection"],
  "authority_level": "official"
}
```

---

## 5. doc_type 매핑 정책

현재 RAG 서버는 `doc_type` 중심으로 검색한다. 이것은 유지 가능하다.

단, `filters.tables`가 들어오면 `doc_type`으로 변환하거나 `metadata.table`로 직접 필터링해야 한다.

권장 매핑:

```python
LOGICAL_TABLE_DOC_TYPES = {
    "law_documents": ["law", "법령"],
    "case_documents": ["case", "dispute_case", "판례", "분쟁조정례", "사례집"],
    "public_guides": ["public_guide", "guide", "공공자료", "가이드"],
    "contract_checklists": ["checklist", "form", "체크리스트", "서식"],
    "special_clause_examples": ["special_clause", "standard_contract", "form", "특약", "표준계약서"],
    "registry_guides": ["registry", "rights", "등기", "권리관계"],
    "insurance_guides": ["insurance", "guarantee", "보증보험"],
    "market_risk_guides": ["market_data", "market_report", "시장분석", "시세데이터"],
    "procedure_guides": ["procedure", "guide", "절차"],
    "faq_documents": ["faq", "FAQ", "질의응답"]
}
```

중요:
- 현재 브랜치의 일부 한글 문자열은 깨져 보이는 상태라 정확한 기존 `doc_type` 값은 DB 실제 값으로 확인해야 한다.
- DB에 이미 들어간 값이 `법령`, `판례`, `사례집`이면 그대로 매핑에 포함한다.
- 새 ingestion은 영문 canonical 값을 권장한다. 예: `law`, `case`, `public_guide`.

---

## 6. VectorStore 수정 명세

현재 파일:

```text
backend/rag_server/core/vector_store.py
```

현재 함수:

```python
def similarity_search(
    self,
    query: str,
    k: int | None = None,
    filter_doc_type: str | None = None,
) -> list[dict]:
```

v7 대응을 위해 아래처럼 확장한다.

```python
def similarity_search(
    self,
    query: str,
    k: int | None = None,
    filter_doc_type: str | list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict]:
```

필터 생성 규칙:

```python
filter_dict = {}

if filter_doc_type:
    if isinstance(filter_doc_type, list):
        filter_dict["doc_type"] = {"$in": filter_doc_type}
    else:
        filter_dict["doc_type"] = filter_doc_type

if filters:
    if filters.get("tables"):
        filter_dict["table"] = {"$in": filters["tables"]}
    if filters.get("domain"):
        filter_dict["domain"] = {"$in": filters["domain"]}
    if filters.get("source_type"):
        filter_dict["source_type"] = {"$in": filters["source_type"]}
```

주의:
- `langchain_postgres.PGVector` JSONB filter 연산 지원 형태는 설치 버전에 따라 다를 수 있다.
- `$in`이 동작하지 않으면 doc_type별 반복 검색 후 merge/dedupe하는 방식으로 구현한다.
- 이미 `RAGPipeline._search_with_plan()`이 doc_type별 반복 검색 구조이므로 최소 수정은 그쪽에서 해결해도 된다.

---

## 7. RAGPipeline 수정 명세

현재 파일:

```text
backend/rag_server/core/rag_pipeline.py
```

### 7.1 `_search_with_plan()`이 filters를 받도록 수정

현재 search_plan은 대략 아래 형태다.

```python
search_plan = {
    "question_type": body.task_type.upper(),
    "query": search_query,
    "doc_types": doc_types
}
```

v7에서는 아래를 포함해야 한다.

```python
search_plan = {
    "question_type": body.task_type.upper(),
    "query": search_query,
    "doc_types": doc_types,
    "filters": body.filters,
    "include_graph_context": body.include_graph_context
}
```

`_search_with_plan()` 안에서:

```python
filters = search_plan.get("filters") or {}
doc_types = filters.get("doc_type") or search_plan.get("doc_types") or []
tables = filters.get("tables") or []
domain = filters.get("domain") or []
source_type = filters.get("source_type") or []
```

반드시 적용해야 하는 필터:
- `doc_type`
- `tables` 또는 `metadata.table`
- `domain`
- `source_type`

### 7.2 `_build_references()`를 v7 evidence item으로 확장

현재 `RagReference`에는 `table`, `source_type`, `domain`, `authority_level`, `score`, `snippet`이 없다.

수정 방향:

```python
def _build_evidence_items(self, results: list[dict]) -> list[dict[str, Any]]:
    items = []
    for index, result in enumerate(results, 1):
        metadata = dict(result.get("metadata") or {})
        score = float(result.get("score", 0.0))
        table = metadata.get("table") or infer_table_from_doc_type(metadata.get("doc_type"))
        doc_id = (
            metadata.get("doc_id")
            or metadata.get("source_id")
            or metadata.get("chunk_id")
            or metadata.get("rag_doc_id")
            or f"rag-ref-{index}"
        )
        metadata["table"] = table
        items.append({
            "doc_id": str(doc_id),
            "source_id": str(metadata.get("source_id") or doc_id),
            "title": str(metadata.get("title") or metadata.get("file_name") or "제목 없음"),
            "table": table,
            "doc_type": str(metadata.get("doc_type") or ""),
            "source_type": str(metadata.get("source_type") or ""),
            "domain": metadata.get("domain") or [],
            "authority_level": str(metadata.get("authority_level") or ""),
            "snippet": result.get("content", "")[:500],
            "chunk_text": result.get("content", "")[:1200],
            "score": score,
            "relevance_score": score,
            "source_url": metadata.get("source_url"),
            "metadata": metadata,
        })
    return items
```

기존 `RagReference`는 유지하되, `/rag/retrieve` 응답에서는 dict 기반 `results`를 우선 반환하는 것을 권장한다.

---

## 8. `/api/v1/rag/retrieve` 수정 예시

아래는 핵심 흐름 예시다.

```python
@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(body: RetrieveRequest, pipeline: RAGPipeline = Depends(_get_pipeline)) -> RetrieveResponse:
    doc_types = resolve_doc_types(body.task_type, body.filters)

    search_plan = {
        "question_type": body.task_type.upper(),
        "query": _build_task_query(body.task_type, body.query, doc_types, body.filters),
        "doc_types": doc_types,
        "filters": body.filters,
        "include_graph_context": body.include_graph_context,
    }

    raw_results = pipeline._search_with_plan(search_plan)
    items = pipeline._build_evidence_items(raw_results[: body.top_k])

    graph_context = []
    include_graph = bool(body.include_graph_context and body.filters.get("include_graph_context", True))
    if include_graph:
        keywords = _extract_keywords(body.query)
        graph_context = pipeline.get_graph_context(
            keywords=keywords,
            task_type=body.task_type,
            filters=body.filters,
        )

    return RetrieveResponse(
        task_type=body.task_type,
        query=body.query,
        results=items,
        references=items,
        graph_context=graph_context,
        doc_types_searched=doc_types,
        total_retrieved=len(items),
    )
```

---

## 9. Graph DB 연동 수정 명세

현재 `GraphStore.get_full_graph_context()`는 이미 아래 형태를 반환한다.

```json
[
  {
    "node": "...",
    "relation": "...",
    "target": "..."
  }
]
```

이 구조는 v7과 맞다.

다만 `/api/v1/rag/retrieve`에서도 이 값을 반환해야 한다. 현재는 chat/diagnosis 쪽에는 들어가지만 retrieve 응답에는 없다.

추가 필요:

```python
graph_context = graph_store.get_full_graph_context(keywords)
```

그리고 반환 전 normalization:

```python
def normalize_graph_context(items: list[dict]) -> list[dict]:
    normalized = []
    seen = set()
    for item in items:
        node = str(item.get("node") or "").strip()
        relation = str(item.get("relation") or "").strip()
        target = str(item.get("target") or "").strip()
        if not node or not relation or not target:
            continue
        key = (node, relation, target)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            "node": node,
            "relation": relation,
            "target": target,
            "severity": item.get("severity"),
            "confidence": item.get("confidence"),
            "source": item.get("source"),
            "metadata": item.get("metadata") or {}
        })
    return normalized[:20]
```

v7 relation normalization 권장:

| Neo4j relation | v7 relation |
|---|---|
| `REGULATED_BY` | `regulated_by` |
| `EVIDENCED_BY` | `evidenced_by` |
| `RELATED_TO` | `related_to` |
| `REQUIRES` | `requires` |
| `DEFINED_IN` | `defined_in` |
| `BELONGS_TO` | `belongs_to` |
| `DETECTED_BY` | `detected_by` |

---

## 10. DB / ingestion 업데이트 명세

현재 `database/schema.sql`에는 `rag_documents`가 존재한다.

v7에서는 단일 `rag_documents`를 허용한다. 따라서 물리 테이블 10개를 만들 필요는 없다.

대신 logical table metadata를 반드시 채운다.

### 10.1 rag_documents metadata 백필

추가 migration 예시:

```sql
UPDATE rag_documents
SET metadata = COALESCE(metadata, '{}'::jsonb)
    || jsonb_build_object(
        'table',
        CASE
            WHEN doc_type IN ('law', '법령') THEN 'law_documents'
            WHEN doc_type IN ('case', '판례', '분쟁조정례', '사례집') THEN 'case_documents'
            WHEN doc_type IN ('public_guide', 'guide', '공공자료', '가이드') THEN 'public_guides'
            WHEN doc_type IN ('checklist', 'form', '체크리스트', '서식') THEN 'contract_checklists'
            WHEN doc_type IN ('special_clause', 'standard_contract', '특약', '표준계약서') THEN 'special_clause_examples'
            WHEN doc_type IN ('registry', '등기', '권리관계') THEN 'registry_guides'
            WHEN doc_type IN ('insurance', 'guarantee', '보증보험') THEN 'insurance_guides'
            WHEN doc_type IN ('market_data', 'market_report', '시장분석', '시세데이터') THEN 'market_risk_guides'
            WHEN doc_type IN ('procedure', '절차') THEN 'procedure_guides'
            WHEN doc_type IN ('faq', 'FAQ', '질의응답') THEN 'faq_documents'
            ELSE 'public_guides'
        END,
        'doc_type', doc_type
    )
WHERE metadata IS NULL OR NOT metadata ? 'table';
```

### 10.2 권장 컬럼 추가

물리 컬럼으로도 관리하고 싶다면 아래를 추가한다.

```sql
ALTER TABLE rag_documents
ADD COLUMN IF NOT EXISTS logical_table VARCHAR(80),
ADD COLUMN IF NOT EXISTS source_type VARCHAR(80),
ADD COLUMN IF NOT EXISTS authority_level VARCHAR(80),
ADD COLUMN IF NOT EXISTS domain TEXT[];

CREATE INDEX IF NOT EXISTS idx_rag_logical_table ON rag_documents(logical_table);
CREATE INDEX IF NOT EXISTS idx_rag_source_type ON rag_documents(source_type);
CREATE INDEX IF NOT EXISTS idx_rag_authority_level ON rag_documents(authority_level);
```

단, 최소 구현은 `metadata.table`만으로도 충분하다.

### 10.3 embedding metadata에도 동일 값 저장

현재 `rag/scripts/embed_to_pgvector.py`는 metadata에 일부 값만 넣는다.

수정 전:

```python
metadata={
    "rag_doc_id": c["id"],
    "doc_type": c["doc_type"],
    "title": c["title"],
    "file_name": c["file_name"],
    "chunk_index": c["chunk_index"],
    "source_law": source_law,
}
```

수정 후:

```python
logical_table = infer_table_from_doc_type(c["doc_type"])

metadata={
    "rag_doc_id": c["id"],
    "doc_id": c.get("chunk_id") or c["id"],
    "source_id": c.get("source_id") or c["id"],
    "table": logical_table,
    "doc_type": canonical_doc_type(c["doc_type"]),
    "source_type": infer_source_type(c["doc_type"]),
    "domain": infer_domain(c),
    "authority_level": infer_authority_level(c["doc_type"]),
    "title": c["title"],
    "file_name": c["file_name"],
    "chunk_index": c["chunk_index"],
    "source_law": source_law,
}
```

이렇게 해야 pgvector 검색 결과 `doc.metadata`에서 바로 `metadata.table`이 나온다.

---

## 11. `/api/v1/chat/query` 업데이트

`common`은 `/rag/retrieve` 실패 시 `/chat/query`로 fallback한다.

현재 `ChatResponse`는 `references`와 `graph_context`를 반환한다. v7 안정성을 위해 `results`도 alias로 추가한다.

수정:

```python
class ChatResponse(BaseModel):
    session_id: str
    answer: str
    results: list[RagReference] = Field(default_factory=list)
    references: list[RagReference] = Field(default_factory=list)
    graph_context: list[GraphContextItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

반환:

```python
items = result.get("results") or result.get("references", [])
return ChatResponse(
    session_id=body.session_id,
    answer=result["answer"],
    results=items,
    references=items,
    graph_context=result.get("graph_context", []),
)
```

---

## 12. task_type 지원 범위 업데이트

수정된 `common`에서 쓰는 diagnosis task_type은 아래다.

| common function | task_type |
|---|---|
| `search_special_clause_rag` | `special_clause_analysis` |
| `search_registry_rag` | `registry_risk_analysis` |
| `search_market_rag` | `market_risk_analysis` |
| `search_insurance_rag` | `insurance_risk_analysis` |
| `search_required_check_rag` | `required_check_analysis` |
| `search_legal_basis_rag` | `legal_basis` |
| `search_legal_rag` | `legal_basis` |

현재 RAG 서버 `_TASK_SOURCE_MAP`에 없는 항목:
- `registry_risk_analysis`
- `market_risk_analysis`
- `insurance_risk_analysis`

반드시 추가한다.

예시:

```python
_TASK_SOURCE_MAP = {
    "special_clause_analysis": ["special_clause", "standard_contract", "law", "case", "public_guide"],
    "registry_risk_analysis": ["registry", "checklist", "law", "case", "public_guide"],
    "market_risk_analysis": ["market_data", "market_report", "public_guide", "case"],
    "insurance_risk_analysis": ["insurance", "public_guide", "law"],
    "required_check_analysis": ["checklist", "public_guide", "registry", "insurance"],
    "legal_basis": ["law", "case", "public_guide", "procedure"],
}
```

---

## 13. 품질/상태 기준

`common.tools.legal_rag_tools._rag_status()`는 아래 기준으로 동작한다.

```python
if not references:
    return "RAG_UNAVAILABLE"
if score < 0.45:
    return "RAG_LOW_QUALITY"
return "RAG_OK"
```

따라서 RAG 서버는:
- 최소 1개 이상 근거를 반환해야 `RAG_UNAVAILABLE`을 피한다.
- 평균 score가 너무 낮으면 review loop에서 추가 검색 또는 fallback으로 갈 수 있다.
- score는 0~1 범위로 normalize하는 것이 좋다.

---

## 14. 테스트 명세

RAG 백엔드 수정 후 아래 테스트를 추가한다.

### 14.1 retrieve contract test

```python
def test_retrieve_v7_contract():
    payload = {
        "task_type": "legal_basis",
        "query": "전입신고와 대항력 관계",
        "top_k": 5,
        "filters": {
            "tables": ["law_documents", "case_documents"],
            "domain": ["tenant_protection"],
            "source_type": ["law", "case"],
            "include_graph_context": True,
        },
        "include_graph_context": True,
    }
    res = requests.post("/api/v1/rag/retrieve", json=payload)
    data = res.json()

    assert "results" in data
    assert "references" in data
    assert data["results"] == data["references"]
    assert "graph_context" in data

    for item in data["results"]:
        assert item.get("table") or item.get("metadata", {}).get("table")
        assert item.get("doc_id") or item.get("source_id")
        assert item.get("chunk_text") or item.get("snippet")
        assert "score" in item or "relevance_score" in item

    for item in data["graph_context"]:
        assert item.get("node")
        assert item.get("relation")
        assert item.get("target")
```

### 14.2 common integration smoke test

RAG 서버 실행 후:

```powershell
$env:PYTHONPATH='C:\Users\cubix\Downloads\common'
$env:RAG_PROVIDER='remote'
$env:RAG_SERVER_URL='http://localhost:8000'
py -3 -c "from common.tools.legal_rag_tools import search_legal_rag; r=search_legal_rag('전입신고와 대항력 관계','REGISTRY_RISK'); print(r.keys()); print(len(r['results']), len(r['graph_context']))"
```

기대:

```text
results >= 1
graph_context key exists
rag_status is RAG_OK or RAG_LOW_QUALITY
```

### 14.3 diagnosis graph smoke test

```powershell
$env:PYTHONPATH='C:\Users\cubix\Downloads\common'
$env:RAG_PROVIDER='remote'
$env:RAG_SERVER_URL='http://localhost:8000'
py -3 -c "from common.graphs.diagnosis_graph import run_diagnosis; r=run_diagnosis(None,'smoke'); print(sorted(r.get('task_results',{}).keys())); print(r.get('report',{}).get('diagnosis_status'))"
```

기대:

```text
special_clause
ownership_risk
market_risk
insurance_risk
required_check
legal_basis
```

6개 task가 모두 실행되어야 한다.

---

## 15. 수정 우선순위

### P0: 반드시 먼저

1. `RetrieveRequest.include_graph_context` 추가
2. `RetrieveResponse.results`, `references`, `graph_context` 추가
3. `/rag/retrieve`에서 `results == references` alias 반환
4. 결과 item에 `table` 또는 `metadata.table` 포함
5. `_TASK_SOURCE_MAP`에 v7 task_type 추가

### P1: 실제 품질 안정화

1. `filters.tables`/`doc_type`/`domain`/`source_type` 실제 검색 반영
2. `doc_type` list 검색 지원
3. `rag_documents.metadata.table` 백필
4. embedding metadata에 table/domain/source_type/authority_level 저장

### P2: 운영 안정성

1. score normalization
2. graph_context dedupe/pruning
3. relation normalization
4. v7 contract tests 추가

---

## 16. 완료 기준

아래 조건을 모두 만족하면 v7 common과 RAG 서버는 정상 연동 가능하다고 본다.

- `/api/v1/rag/retrieve`가 HTTP 200을 반환한다.
- 응답에 `results`, `references`, `graph_context`가 모두 있다.
- `results`와 `references`는 동일 배열이다.
- 각 result에는 `doc_id`, `title`, `table`, `doc_type`, `chunk_text`, `score`, `metadata.table`이 있다.
- `filters.tables`로 `law_documents`만 요청하면 법령 계열 문서만 나온다.
- `filters.tables`로 `case_documents`만 요청하면 판례/사례 계열 문서만 나온다.
- `include_graph_context=true`일 때 `graph_context` key가 항상 존재한다.
- graph item은 `node`, `relation`, `target`을 가진다.
- `common.tools.legal_rag_tools.search_legal_rag()`가 `results`를 정상 반환한다.
- `common.graphs.diagnosis_graph.run_diagnosis()`에서 6개 task가 모두 실행된다.

---

## 17. 최종 검토 의견

RAG 백엔드는 완전히 새로 만들 필요 없다.

현재 구조:
- PostgreSQL `rag_documents`
- LangChain PGVector `langchain_pg_embedding`
- Neo4j `GraphStore`
- FastAPI `/api/v1/rag/retrieve`
- FastAPI `/api/v1/chat/query`

이 구조는 v7과 양립 가능하다.

핵심은 테이블을 10개로 물리 분리하는 것이 아니라, 단일 `rag_documents`와 pgvector metadata 안에 `table`, `domain`, `source_type`, `authority_level`을 정확히 보존하는 것이다.

따라서 이번 업데이트의 본질은:

```text
RAG 검색 결과를 v7 evidence contract로 정규화하고,
logical table 필터를 실제 검색에 반영하고,
Graph DB context를 retrieve 응답에도 포함하는 것
```

이다.

이 세 가지만 맞으면 수정된 `common`은 RAG 서버와 정상적으로 연결된다.
