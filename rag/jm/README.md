## rag/jm

PostgreSQL(pgvector)과 OpenAI LLM을 기반으로 한 RAG(Retrieval-Augmented Generation) 모듈입니다.

### 🎯 주요 기능
- **문서 적재 (Ingest)**: PDF/텍스트 문서를 정제 및 청킹하여 pgvector에 적재 (강화된 텍스트 전처리 포함)
- **벡터 검색 (Search)**: 사용자의 질문과 유사한 문서 조각(Chunk)을 유사도 기반으로 검색
- **답변 생성 (Generate)**: 검색된 컨텍스트를 바탕으로 LLM(GPT)이 최종 RAG 응답 생성

### ⚙️ 준비 사항
- **환경 변수 (.env)**:
  - `OPENAI_API_KEY`: 임베딩 생성 및 답변 생성용
  - `RAG_COLLECTION`: 벡터 DB 컬렉션 이름 (기본값: `jeonse-rag`)
  - `RAG_LLM_MODEL`: 답변 생성에 사용할 모델 (기본값: `gpt-4o-mini`)
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`: PostgreSQL 접속 정보
- **DB 필수 설정**:
  - `CREATE EXTENSION IF NOT EXISTS vector;` (pgvector 확장 활성화)

### 🚀 실행 방법

#### 1. 문서 적재 (Ingest)
문서에서 텍스트를 추출하고 벡터화하여 DB에 저장합니다. 텍스트 전처리가 적용됩니다.
```powershell
# 기본 적재
python -m rag.jm.cli ingest --path "docs/pdf" --glob "*.pdf"

# 기존 데이터를 모두 삭제하고 새로 적재할 때 (--clear)
python -m rag.jm.cli ingest --path "docs/pdf" --glob "*.pdf" --clear
```

#### 2. 관련 문서 검색 (Search)
질문과 관련된 상위 K개의 문서 조각을 JSON 형식으로 반환합니다.
```powershell
python -m rag.jm.cli search --query "전세보증금 반환 보증" --k 5
```

#### 3. 최종 답변 생성 (Generate)
DB 검색 결과와 LLM을 결합하여 최종 답변을 생성합니다.
```powershell
python -m rag.jm.cli generate --query "전세사기 예방을 위한 체크리스트 알려줘"
```

### 🛠️ 파일 구성
- `ingest.py`: 문서 로드, 정제(Cleaning), 벡터 적재 로직
- `search.py`: 벡터 유사도 검색 엔진
- `generate.py`: 프롬프트 구성 및 LLM 답변 생성
- `cli.py`: 명령행 인터페이스 (리모컨)
- `config.py` & `index.py`: 설정 로드 및 벡터 스토어 초기화
