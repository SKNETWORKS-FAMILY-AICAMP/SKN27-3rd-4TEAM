# 전세계약 위험 진단 에이전트 — 설치 가이드

## 1. 사전 준비

- **Python 3.12+**
- **Docker Desktop** (Neo4j, PostgreSQL 실행용)

## 2. 설치 순서

```bash
# 1) 가상환경 생성 + 활성화
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

# 2) 패키지 설치
pip install -r requirements.txt

# 3) 환경변수 설정
copy .env.example .env
# .env 파일 열어서 OPENAI_API_KEY 입력

# 4) Docker 서비스 시작
docker compose up -d

# 5) Neo4j 판례 그래프 빌드 (최초 1회)
python scripts/build_graph.py

# 6) Streamlit 실행
streamlit run frontend/app.py
```

## 3. 필수 환경변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `LLM_PROVIDER` | 사용할 LLM | `openai` |
| `OPENAI_API_KEY` | OpenAI API 키 | `sk-proj-...` |
| `NEO4J_PASSWORD` | Neo4j 비밀번호 | `jeonse1234` |

## 4. 폴더 구조

```
data/          → 종로구 전세/매매 CSV (2016~2025)
docs/pdf/      → 판례 PDF 파일
reports/       → 진단 결과 JSON (자동 생성)
backend/       → 에이전트 + 워크플로우
frontend/      → Streamlit UI
```

## 5. 주의사항

- Docker Desktop이 실행 중이어야 Neo4j/PostgreSQL 접속 가능
- `data/` 폴더의 CSV 파일이 없으면 가격 분석 불가
- `docs/pdf/` 폴더의 판례 PDF가 없으면 그래프 빌드 불가 (이미 빌드된 Neo4j 볼륨 사용 가능)
- OpenAI API 키에 잔액이 있어야 진단 가능
