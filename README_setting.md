# 전세계약 위험 진단 에이전트 - 개발 환경 세팅 가이드

## 1. 환경변수 설정

`.env.example`을 복사해서 `.env` 파일 만들고 값 채우기

```bash
cp .env.example .env
```

`.env` 파일 열어서 아래 값 채우기:

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=jeonse_risk
DB_USER=postgres
DB_PASSWORD=팀장한테 받은 비밀번호
PUBLIC_DATA_API_KEY=팀장한테 받은 API 키
```

> ⚠️ `.env` 파일은 절대 깃에 올리면 안 돼요!

---

## 2. 패키지 설치

```bash
uv pip install -r requirements.txt
```

---

## 3. VSCode Python 인터프리터 설정

패키지 설치 후 VSCode에서 가상환경으로 인터프리터 설정해야 해요.

```
Ctrl + Shift + P
→ Python: Select Interpreter 입력
→ .venv 선택
```

> ⚠️ 이 설정을 안 하면 Run Python File 버튼이 시스템 Python으로 실행돼서 패키지를 못 찾아요!

---

## 4. Docker로 DB + 파이프라인 실행

```bash
docker-compose up --build
```

처음 실행하면 자동으로

1. PostgreSQL DB 컨테이너 시작
2. 테이블 5개 자동 생성 (`database/schema.sql`)
3. CSV 데이터 적재 (`rag/scripts/preprocess_load.py`)
4. 배치 컨테이너 시작 (매주 월요일 6시 자동 실행)

---

## 5. DB 데이터 확인

DBeaver 또는 psql로 연결해서 확인

```
Host: localhost
Port: 5432
Database: jeonse_risk
Username: postgres
Password: .env에 설정한 비밀번호
```

확인 쿼리:

```sql
SELECT COUNT(*) FROM jeonse_transactions;  -- 전세 실거래
SELECT COUNT(*) FROM sale_transactions;    -- 매매 실거래
SELECT COUNT(*) FROM price_ratio;          -- 전세가율
SELECT COUNT(*) FROM rag_documents;        -- RAG 문서
SELECT COUNT(*) FROM diagnosis_logs;       -- 진단 로그
```

---

## 6. PDF 문서 적재 (RAG용)

PDF 파일들을 `docs/pdf/` 폴더에 넣고 실행:

```bash
python rag/scripts/pdf_pipeline.py
```

---

## 7. 디렉토리 구조

```
SKN27-3rd-4TEAM/
├── backend/            ← 백엔드 API
├── data/               ← CSV 실거래가 데이터
├── database/
│   └── schema.sql      ← PostgreSQL 테이블 DDL
├── docs/
│   └── pdf/            ← RAG용 PDF 파일
├── frontend/           ← 프론트엔드
├── rag/
│   └── scripts/
│       ├── fetch_data.py       ← API 자동 수집
│       ├── preprocess_load.py  ← CSV 전처리 + 적재
│       └── pdf_pipeline.py     ← PDF 추출 + 적재
├── logs/               ← 배치 실행 로그
├── .env.example        ← 환경변수 템플릿
├── .gitignore
├── batch.sh            ← 정기 배치 스크립트
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 8. 자주 묻는 것들

**Q. Docker 컨테이너 완전히 초기화하고 싶어요**
```bash
docker-compose down -v
docker-compose up --build
```

**Q. 배치 수동으로 실행하고 싶어요**
```bash
bash batch.sh
```

**Q. DB에 데이터가 안 들어왔어요**
```bash
docker logs jeonse_pipeline
```

**Q. `.env` 파일 어디서 받아요?**

데이터 엔지니어한테 직접 받아요. (카톡/슬랙으로 공유)

**Q. Run Python File 눌렀는데 패키지를 못 찾아요**

VSCode 인터프리터가 시스템 Python으로 설정된 거예요.
`Ctrl + Shift + P` → `Python: Select Interpreter` → `.venv` 선택하면 돼요.
