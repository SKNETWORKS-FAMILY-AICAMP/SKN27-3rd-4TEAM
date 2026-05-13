## rag/jm

PostgreSQL(pgvector) 기반 RAG 모듈입니다. 기존 `jeonse-rag` 컬렉션은 OpenAI 임베딩(1536차원)으로 적재되어 있고, 무료 로컬 임베딩은 별도 컬렉션으로 새로 적재해서 사용합니다.

### 주요 기능
- 문서 적재: PDF/TXT 문서를 정제하고 chunk로 나누어 PGVector에 저장
- 검색: 질문과 유사한 문서 chunk를 top-k로 반환
- 답변 생성: 검색 결과를 LLM에 넣어 최종 RAG 답변 생성
- 에이전트: LangGraph Supervisor가 검색 도구를 호출하는 구조

### 환경변수
- `RAG_COLLECTION`: 기본값 `jeonse-rag`
- `RAG_EMBEDDING_PROVIDER`: `openai` 또는 `local` (기존 `jeonse-rag`는 `openai`)
- `RAG_EMBEDDING_MODEL`: OpenAI 기본값 `text-embedding-3-small`, local 예시 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- `RAG_LLM_PROVIDER`: `openai` 또는 `ollama` (기본값 `openai`)
- `RAG_LLM_MODEL`: OpenAI는 `gpt-4o-mini`, Ollama는 예: `llama3.1`
- `OLLAMA_BASE_URL`: 기본값 `http://localhost:11434`
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`: PostgreSQL 접속 정보

### 실행 예시
기존 OpenAI 임베딩 컬렉션 검색:
```powershell
$env:RAG_COLLECTION="jeonse-rag"
$env:RAG_EMBEDDING_PROVIDER="openai"
$env:RAG_EMBEDDING_MODEL="text-embedding-3-small"
python -m rag.jm.cli search --query "전세보증금 반환 보증" --k 5
```

무료 로컬 임베딩 컬렉션 새로 적재:
```powershell
$env:RAG_COLLECTION="jeonse-rag-local"
$env:RAG_EMBEDDING_PROVIDER="local"
$env:RAG_EMBEDDING_MODEL="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
python -m rag.jm.cli ingest --path docs/pdf --glob "*.pdf" --clear
```

OpenAI 답변 생성:
```powershell
python -m rag.jm.cli generate --query "전세사기 예방 체크리스트 알려줘" --k 5
```

멀티에이전트 실행:
```powershell
python -m rag.jm.cli multi-agent --query "전세보증금 반환 보증 가입 전에 무엇을 확인해야 해?" --k 3
```

Ollama 무료 답변 생성:
```powershell
$env:RAG_LLM_PROVIDER="ollama"
$env:RAG_LLM_MODEL="llama3.1"
python -m rag.jm.cli generate --query "전세사기 예방 체크리스트 알려줘" --k 5
```
