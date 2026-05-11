# 전세계약 위험 진단 RAG 서버 — 팀원 가이드

> 작성자: 행 | 담당 역할: RAG 파이프라인 + FastAPI 백엔드

---

## 1. 내가 구현한 것

전세계약서를 분석해서 **전세사기 위험도를 진단**하고, 법령·판례·사례집 기반으로 답변을 제공하는 AI 서버예요.

팀원들이 만드는 챗봇, 멀티에이전트, 프론트엔드가 이 서버에 HTTP 요청을 보내면 됩니다.

---

## 2. 전체 구조

```
팀원 챗봇 / 프론트엔드 / 멀티에이전트
            ↓ HTTP 요청
    ┌──────────────────────┐
    │   FastAPI 서버        │  ← 내가 구현한 서버 (포트 8000)
    │   /api/v1/chat        │
    │   /api/v1/diagnosis   │
    └──────────┬───────────┘
               │
       ┌───────┴────────┐
       ↓                ↓
  pgvector DB        Neo4j
  (법령/판례/사례집    (위험요소-법령-판례
   4,920개 청크)       지식 그래프)
       ↓                ↓
       └───────┬────────┘
               ↓
          GPT-4o-mini
               ↓
          답변 / 진단 결과 반환
```

---

## 3. 사용 기술 스택

| 항목 | 기술 |
|------|------|
| API 서버 | FastAPI |
| 벡터 DB | PostgreSQL + pgvector |
| 그래프 DB | Neo4j |
| LLM | GPT-4o-mini (OpenAI) |
| 임베딩 | text-embedding-3-small (OpenAI) |
| RAG 프레임워크 | LangChain |
| 인프라 | Docker Compose |

---

## 4. RAG 방식

**Modular RAG + KAG(GraphRAG) 조합**을 사용했어요.

- **pgvector**: 질문과 의미적으로 유사한 법령/판례 문서를 검색 (Semantic Search)
- **Neo4j**: 위험요소 ↔ 법령 ↔ 판례 관계를 그래프로 추론 (Knowledge Graph)
- **LLM**: 두 검색 결과를 합쳐 최종 답변 또는 진단 결과 생성

---

## 5. API 사용법 (팀원용)

서버 주소: `http://localhost:8000`  
Swagger 문서: `http://localhost:8000/docs`

---

### 5-1. 헬스체크

서버와 DB가 정상인지 확인해요.

```
GET /api/v1/health
```

**응답 예시:**
```json
{
  "status": "ok",
  "services": {
    "pgvector": "ok (4920 docs)",
    "neo4j": "ok"
  }
}
```

---

### 5-2. 전세 질문 채팅

전세 관련 질문을 하면 법령·판례 기반 답변을 돌려줘요.

```
POST /api/v1/chat/query
Content-Type: application/json
```

**요청:**
```json
{
  "session_id": "user-001",
  "message": "전세금 반환 거부 시 어떻게 해야 하나요?",
  "history": []
}
```

**응답:**
```json
{
  "session_id": "user-001",
  "answer": "주택임대차보호법 제3조의3에 따라 임대차 종료 후 임차인은...",
  "references": [
    {
      "doc_type": "법령",
      "title": "주택임대차보호법 제3조의3",
      "chunk_text": "임대차 종료 후 보증금 반환...",
      "relevance_score": 0.91
    }
  ]
}
```

> `history`에 이전 대화를 넣으면 멀티턴 대화가 가능해요.

---

### 5-3. 계약서 텍스트 위험 진단

계약서 내용을 텍스트로 넣으면 위험도를 분석해줘요.

```
POST /api/v1/diagnosis/text
Content-Type: application/json
```

**요청:**
```json
{
  "session_id": "user-001",
  "contract_text": "임대인 홍길동, 임차인 김철수. 보증금 3억원. 계약기간 2024.03.01~2026.03.01. 근저당권 설정금액 2억 5천만원..."
}
```

**응답:**
```json
{
  "session_id": "user-001",
  "risk_score": 85.0,
  "risk_level": "위험",
  "risk_factors": [
    {
      "factor_id": "RF001",
      "category": "권리관계",
      "description": "근저당권 설정금액이 보증금 대비 과다",
      "severity": "HIGH",
      "legal_basis": "민법 제356조",
      "advice": "등기부등본 열람 후 선순위 권리 확인 필요"
    }
  ],
  "summary": "근저당권 설정으로 인해 보증금 회수 위험이 높습니다.",
  "references": [...]
}
```

**위험도 기준:**
| risk_score | risk_level |
|-----------|------------|
| 80 이상 | 위험 🔴 |
| 60 ~ 79 | 주의 🟡 |
| 60 미만 | 안전 🟢 |

---

### 5-4. PDF 계약서 업로드 진단

PDF 파일을 직접 업로드해서 진단받을 수 있어요.

```
POST /api/v1/diagnosis/upload
Content-Type: multipart/form-data
```

**요청:**
- `file`: PDF 파일 (최대 10MB)
- `session_id`: 세션 ID (선택)

**응답:** 5-3과 동일한 형식

---

## 6. 실행 방법

> 팀원이 처음 셋업할 때 아래 순서대로 실행하세요.

### 사전 조건
- Docker Desktop 설치 및 실행
- Python 3.11 이상
- `.env` 파일에 `OPENAI_API_KEY` 본인 키 입력

### STEP 1 — Docker 실행
```bash
docker compose up -d --build
```

### STEP 2 — 상태 확인
```bash
docker compose ps
# jeonse_db, jeonse_neo4j, jeonse_api 세 개가 running 이어야 함
```

### STEP 3 — 데이터 적재 (최초 1회만)
```bash
python rag/loader.py --step 1   # PDF → PostgreSQL
python rag/loader.py --step 2   # CSV → PostgreSQL
python rag/loader.py --step 3   # 청크 정제
python rag/loader.py --step 4   # 임베딩 → pgvector
python rag/loader.py --step 5   # Neo4j 그래프 구축
```

### STEP 4 — 서버 확인
```bash
curl http://localhost:8000/api/v1/health
# 브라우저: http://localhost:8000/docs
```

### 이후 실행 (매번)
```bash
docker compose up -d
# 데이터는 볼륨에 유지되므로 STEP 3은 다시 안 해도 됨
```

---

## 7. 포트 정보

| 서비스 | 포트 | 용도 |
|--------|------|------|
| FastAPI | 8000 | API 서버 (팀원이 호출하는 주소) |
| PostgreSQL | 5432 | 벡터 DB |
| Neo4j Browser | 7474 | 그래프 시각화 확인용 |
| Neo4j Bolt | 7687 | Python 연결용 |

---

## 8. 파일 구조

```
SKN27-3rd-4TEAM/
├── backend/
│   └── rag_server/
│       ├── main.py              # FastAPI 진입점
│       ├── config.py            # 환경변수 설정
│       ├── core/
│       │   ├── vector_store.py  # pgvector 검색
│       │   ├── graph_store.py   # Neo4j 검색
│       │   ├── llm.py           # 프롬프트 + LLM 체인
│       │   └── rag_pipeline.py  # RAG 실행 (Retrieve→Augment→Generate)
│       ├── services/
│       │   ├── diagnosis_service.py  # 진단 비즈니스 로직
│       │   └── contract_parser.py    # 계약서 파싱
│       └── api/routes/
│           ├── chat.py          # /chat 라우터
│           ├── diagnosis.py     # /diagnosis 라우터
│           └── health.py        # /health 라우터
├── rag/
│   ├── loader.py                # 데이터 파이프라인 진입점 (step 1~5)
│   └── ingestion/
│       ├── embed_to_pg.py       # 임베딩 적재
│       ├── build_graph.py       # Neo4j 그래프 구축
│       └── clean_chunks.py      # 청크 정제
├── database/
│   └── schema.sql               # DB 스키마
├── docker-compose.yml           # 전체 인프라 구성
├── backend/Dockerfile           # FastAPI 컨테이너
└── .env                         # 환경변수 (API 키 등)
```

---

## 9. 팀원 연동 시 주의사항

1. **포트 충돌**: 내 서버는 `8000`번 포트를 사용해요. 다른 서비스와 겹치면 `docker-compose.yml`의 포트를 변경해주세요.
2. **OPENAI_API_KEY**: `.env` 파일에 본인 키를 넣어야 해요.
3. **데이터 적재**: STEP 3은 팀원 PC에서도 최초 1회 실행이 필요해요.
4. **CORS**: 모든 출처(`*`) 허용으로 설정되어 있어서 프론트엔드에서 바로 호출 가능해요.

---

## 10. 문의

궁금한 점은 행에게 연락주세요.
