## rag/jm

PostgreSQL(pgvector) 기반 OpenAI RAG 모듈입니다. 기존 OpenAI 임베딩 기반 `jeonse-rag` PGVector 컬렉션을 조회하고, OpenAI 임베딩/채팅 모델로 검색과 답변 생성을 수행합니다.

### 주요 기능

- 문서 적재: PDF/TXT 문서를 정제하고 chunk 단위로 PGVector에 저장
- 검색: 질문과 유사한 문서 chunk를 top-k로 반환
- 답변 생성: 검색 결과를 OpenAI 모델에 전달해 최종 RAG 답변 생성
- 에이전트: DB 분석 결과와 RAG 근거를 결합해 전세 위험 설명 생성

### 환경변수

- `OPENAI_API_KEY`: OpenAI API 키
- `OPENAI_MODEL`: 기본값 `gpt-4o-mini`
- `RAG_LLM_MODEL`: 설정하면 `OPENAI_MODEL`보다 우선 사용
- `RAG_EMBEDDING_MODEL`: 기본값 `text-embedding-3-small`
- `RAG_COLLECTION`: 기본값 `jeonse-rag`
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`: PostgreSQL 접속 정보

### 실행 예시

```powershell
$env:OPENAI_API_KEY="sk-..."
python -m rag.jm.cli search --query "전세보증금 반환 보증" --k 5
```

```powershell
$env:OPENAI_API_KEY="sk-..."
python -m rag.jm.cli generate --query "전세사기 예방 체크리스트 알려줘" --k 5
```

```powershell
$env:OPENAI_API_KEY="sk-..."
python -m rag.jm.cli multi-agent --query "전세보증금 반환 보증 가입 전에 무엇을 확인해야 해?" --k 3
```
