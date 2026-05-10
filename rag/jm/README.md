## rag/jm

PostgreSQL(pgvector) 기반 RAG 모듈입니다.

### 목표
- PDF/텍스트 문서를 청킹해서 PostgreSQL(pgvector)에 적재
- 질의어로 관련 chunk를 벡터 유사도 검색(top-k)해서 반환

### 준비 사항
- 환경변수:
  - `OPENAI_API_KEY` (필수: 임베딩 생성)
  - `RAG_COLLECTION` (선택, 기본값 `jeonse-rag`)
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (Postgres 접속 정보)
- DB 확장:
  - `CREATE EXTENSION IF NOT EXISTS vector;`

### 실행
문서 적재:
```powershell
python -m rag.jm.cli ingest --path docs --glob "*.pdf"
```

검색:
```powershell
python -m rag.jm.cli search --query "전세보증금 반환 보증" --k 5
```

