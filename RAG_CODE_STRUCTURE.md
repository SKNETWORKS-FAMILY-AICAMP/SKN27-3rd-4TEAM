# RAG 서버 코드 구조 문서

> **담당**: RAG 파이프라인 / 백엔드 API  
> **기술 스택**: FastAPI · PostgreSQL (pgvector) · Neo4j · LangChain · OpenAI

---

## 전체 아키텍처

```
사용자 요청 (계약서 텍스트 / PDF / DOCX)
        │
        ▼
  [FastAPI 서버] ──────────── /api/v1/diagnosis
        │                      /api/v1/chat
        │                      /api/v1/health
        ▼
  [DiagnosisService]
    ├── ContractParser          계약서 파싱 (주소, 보증금, 특약 등 추출)
    └── RAGPipeline
          ├── VectorStore       pgvector 유사도 검색 (법령/판례)
          ├── GraphStore        Neo4j 위험 요인 조회
          └── LLM               GPT-4o 진단 및 요약 생성
        │
        ▼
  DiagnosisResponse (risk_score, risk_level, risk_factors, summary)
```

---

## 폴더 구조

```
SKN27-3rd-4TEAM/
├── backend/
│   └── rag_server/              ← 실제 서비스 코드 (여기가 핵심)
│       ├── main.py              FastAPI 진입점
│       ├── config.py            환경변수 설정
│       ├── api/routes/
│       │   ├── health.py        헬스체크 엔드포인트
│       │   ├── chat.py          일반 RAG 채팅 엔드포인트
│       │   └── diagnosis.py     계약서 진단 엔드포인트
│       ├── core/
│       │   ├── vector_store.py  pgvector 벡터 검색
│       │   ├── graph_store.py   Neo4j 그래프 조회
│       │   ├── llm.py           LangChain 체인 빌더
│       │   └── rag_pipeline.py  RAG 오케스트레이터 (핵심)
│       ├── services/
│       │   ├── contract_parser.py     계약서 파싱 서비스
│       │   ├── diagnosis_service.py   진단 오케스트레이터
│       │   └── market_price_service.py  ⚠️ 미사용 (아래 참고)
│       └── models/
│           └── schemas.py       Pydantic 모델 정의
│
├── rag/
│   └── ingestion/               ← 데이터 적재 스크립트 (1회성 실행)
│       ├── embed_to_pg.py       문서 → 임베딩 → pgvector 저장
│       ├── build_graph.py       위험요인 → Neo4j 적재
│       ├── clean_chunks.py      청크 정제
│       ├── load_market_data.py  ⚠️ 미사용 (아래 참고)
│       └── test_market_price.py ⚠️ 미사용 (아래 참고)
│
├── database/
│   ├── schema.sql               PostgreSQL 테이블 정의 (초기화 시 자동 실행)
│   └── migration_market.sql     ⚠️ 미사용 (아래 참고)
│
├── frontend/
│   └── app.py                   Streamlit UI
│
└── docker-compose.yml           컨테이너 구성
```

---

## 핵심 파일 상세 설명

### `backend/rag_server/main.py` — FastAPI 진입점

서버 시작 시 `VectorStore`와 `GraphStore`를 초기화하고 `app.state`에 저장합니다.  
라우터 3개를 `/api/v1` 아래에 등록하고, LangSmith 트레이싱 환경변수를 설정합니다.

```
서버 시작 (lifespan)
  → VectorStore 초기화 (pgvector 연결)
  → GraphStore 초기화 (Neo4j 연결)
  → 라우터 등록: /health, /chat, /diagnosis
```

---

### `backend/rag_server/services/diagnosis_service.py` — 진단 오케스트레이터

계약서 진단의 전체 흐름을 조율하는 서비스입니다.

**흐름:**
```
1. ContractParser로 계약서 파싱
   → lessor_name, lessee_name, address, deposit_amount, special_terms 등 추출

2. RAG 텍스트 조합
   → [특약사항] + 계약서 본문
   (특약사항을 앞에 두어 LLM이 중요 조항을 먼저 읽도록 배치)

3. RAGPipeline.diagnose() 호출
   → 벡터 검색 + 그래프 조회 + LLM 분석

4. DiagnosisResponse 반환 후 diagnosis_logs 테이블에 저장
```

---

### `backend/rag_server/core/rag_pipeline.py` — RAG 파이프라인 (핵심)

VectorStore, GraphStore, LLM을 조합해서 실제 진단을 수행합니다.

**`diagnose()` 흐름:**
```
계약서 키워드 추출
  → VectorStore 유사도 검색 (법령/판례 문서 k건 조회)
  → GraphStore 키워드 기반 위험요인 조회 (Neo4j)
  → LLM 호출: context + risk_factors + contract_text[:4000]
  → JSON 응답 파싱 → RiskFactor 리스트 생성
  → references (참조 문서 목록) 추가
```

**LLM 응답 파싱 전략:**
- JSON 코드블록 추출 시도 → 중괄호 객체 추출 시도 → 둘 다 실패 시 `_fallback_diagnosis()` 사용
- Neo4j 연결 실패 시 하드코딩된 fallback 위험요인 2개로 대체

---

### `backend/rag_server/services/contract_parser.py` — 계약서 파서

계약서 텍스트에서 구조화된 정보를 추출합니다.

**지원 입력 형식:** 텍스트, PDF (pdfplumber + OCR 폴백), DOCX

**추출 항목 (GPT-4o 사용):**

| 필드 | 설명 |
|------|------|
| `lessor_name` | 임대인 이름 |
| `lessee_name` | 임차인 이름 |
| `address` | 계약 대상 주소 |
| `deposit_amount` | 전세금 (만원) |
| `monthly_rent` | 월세 (만원, 전세=0) |
| `contract_start` | 임대차 시작일 |
| `contract_end` | 임대차 종료일 |
| `special_terms` | 특약사항 전문 |

**위험 키워드 추출:** `RISK_KEYWORDS` 리스트와 계약서 텍스트를 비교해서 위험 관련 단어를 뽑아 벡터 검색 쿼리로 활용합니다.

---

### `backend/rag_server/core/vector_store.py` — 벡터 스토어

`langchain_postgres.PGVector`를 사용해 PostgreSQL에 임베딩을 저장하고 검색합니다.

- **임베딩 모델**: `text-embedding-3-small` (OpenAI)
- **컬렉션**: `jeonse_docs` (환경변수 `PG_VECTOR_COLLECTION`)
- **검색**: `similarity_search_with_relevance_scores()` → `(Document, score)` 리스트
- **저장 테이블**: `langchain_pg_embedding` (LangChain이 자동 생성)

---

### `backend/rag_server/core/graph_store.py` — 그래프 스토어

Neo4j에서 위험요인 노드를 키워드로 검색합니다.

**그래프 구조:**
```
(RiskFactor) -[:REGULATED_BY]→ (Law)
(RiskFactor) -[:EVIDENCED_BY]→ (Case)
```

**조회 방식:** 계약서에서 추출한 키워드가 `rf.keywords` 또는 `rf.description`에 포함된 `RiskFactor` 노드를 조회, `severity` 기준(HIGH → MEDIUM → LOW)으로 정렬해서 반환합니다.

---

### `backend/rag_server/models/schemas.py` — 데이터 모델

**주요 모델:**

| 모델 | 용도 |
|------|------|
| `ContractInfo` | 파싱된 계약서 정보 |
| `RiskFactor` | 위험 요인 1건 (factor_id, category, severity, advice) |
| `DiagnosisResponse` | 진단 결과 전체 (risk_score 0~100, risk_level, risk_factors, summary) |
| `RagReference` | 참조된 법령/판례 문서 1건 |
| `ChatRequest/Response` | 일반 RAG 채팅용 |

`risk_level` 기준: `안전` (0~59) / `주의` (60~79) / `위험` (80~100)

---

## 데이터베이스 구조 (`database/schema.sql`)

```
jeonse_transactions     전세 실거래가 (housing_type, dong_name, deposit_amount ...)
sale_transactions       매매 실거래가 (housing_type, sigungu, deal_amount ...)
price_ratio             전세가율 요약 (dong_name, jeonse_ratio, risk_level ...)
rag_documents           RAG용 문서 청크 (doc_type, title, chunk_text, vector_id ...)
diagnosis_logs          진단 요청/결과 로그 (session_id, risk_score, risk_factors JSONB ...)
langchain_pg_embedding  pgvector 임베딩 (LangChain 자동 생성)
```

---

## 인프라 구성 (`docker-compose.yml`)

| 컨테이너 | 이미지 | 역할 | 포트 |
|----------|--------|------|------|
| `jeonse_db` | pgvector/pgvector:pg16 | PostgreSQL + pgvector | 5432 |
| `jeonse_api` | backend/Dockerfile | FastAPI 서버 | 8000 |
| `jeonse_neo4j` | neo4j:5.18 | 지식 그래프 | 7474, 7687 |
| `jeonse_pipeline` | 루트 Dockerfile | 최초 CSV 적재 (1회) | — |
| `jeonse_batch` | 루트 Dockerfile | 정기 배치 (매주 월 6시) | — |

**개발 환경:** `jeonse_api`는 `./backend:/app/backend` 볼륨 마운트로 코드 변경이 즉시 반영됩니다.

---

## 데이터 파이프라인 (`rag/ingestion/`)

최초 1회 실행하는 적재 스크립트들입니다. 서버 운영 중에는 실행하지 않아도 됩니다.

```
docs/ (PDF 문서들)
  │
  ▼
clean_chunks.py     → 텍스트 청크 정제 → rag_documents 테이블 저장
  │
  ▼
embed_to_pg.py      → rag_documents에서 미임베딩 청크 조회
                    → OpenAI 임베딩 생성
                    → langchain_pg_embedding 저장
                    → rag_documents.vector_id 업데이트
  │
  ▼
build_graph.py      → 위험요인 데이터 → Neo4j RiskFactor 노드 생성
```

**재실행 안전성:** `embed_to_pg.py`는 `vector_id IS NULL`인 청크만 처리하므로 중복 임베딩 없음.

---

## API 엔드포인트 요약

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/health` | 서버 상태, DB/Neo4j 연결 확인 |
| POST | `/api/v1/chat` | 일반 RAG 채팅 (법령/판례 Q&A) |
| POST | `/api/v1/diagnosis` | 계약서 텍스트 진단 |
| POST | `/api/v1/diagnosis/pdf` | PDF 계약서 진단 |
| POST | `/api/v1/diagnosis/docx` | DOCX 계약서 진단 |

---

## ⚠️ 미사용 파일 (향후 참고용)

금액 기반 위험 판단을 딥러닝 파트에서 담당하기로 분리되면서 현재는 연결이 끊겨 있습니다. 나중에 RAG 파이프라인에 시세 분석을 다시 붙이고 싶을 때 참고하세요.

| 파일 | 역할 |
|------|------|
| `backend/rag_server/services/market_price_service.py` | 전세가율 계산, 시장가 이상 탐지, 추세 분석 서비스 |
| `rag/ingestion/load_market_data.py` | 매매·전세 실거래가 CSV → PostgreSQL 적재 |
| `rag/ingestion/test_market_price.py` | market_price_service 기능 검증 테스트 |
| `database/migration_market.sql` | sale_transactions에 dong_name 컬럼 추가 마이그레이션 |

**재활성화 방법:**
1. `migration_market.sql` 실행
2. `data/market/` 에 CSV 12개 배치 후 `load_market_data.py` 실행
3. `diagnosis_service.py`에 아래 코드 복원:
```python
from rag_server.services.market_price_service import MarketPriceService
# __init__에 추가:
self._market = MarketPriceService(settings)
# diagnose_text()에 추가 (rag_text 조합 전):
dong = MarketPriceService.extract_dong(contract_info.address)
market_context = self._market.build_context_text(dong, deposit_amount, htype)
rag_text = market_context + "\n\n" + rag_text
```

---

## 환경변수 (`.env`)

```env
OPENAI_API_KEY=           # GPT-4o, text-embedding-3-small 사용
LANGCHAIN_API_KEY=        # LangSmith 트레이싱 (선택)
LANGCHAIN_TRACING_V2=     # true / false
LANGCHAIN_PROJECT=        # LangSmith 프로젝트명

DB_HOST=db                # docker-compose 내부 서비스명
DB_PORT=5432
DB_NAME=jeonse_risk
DB_USER=postgres
DB_PASSWORD=risk1234

NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=jeonse1234

PG_VECTOR_COLLECTION=jeonse_docs
RAG_TOP_K=5               # 유사도 검색 결과 수
```
