## standard

DB 조회나 RAG 문서 검색 없이 LLM만 사용해 일반적인 전세 관련 질문에 답하는 독립 모듈입니다.

### 폴더만 따로 전달할 때 포함되는 파일
- `answer.py`: 표준 LLM 답변 생성 로직
- `config.py`: 환경변수 설정 로드
- `run_standard.py`: 단독 실행 CLI
- `.env.sample`: 환경변수 예시
- `requirements.txt`: 최소 의존성

### 설치
```powershell
pip install -r requirements.txt
```

### 실행
standard 폴더 안에서 실행:

```powershell
python run_standard.py --question "전세 계약할 때 꼭 확인해야 하는 기본 사항 알려줘"
```

프로젝트 루트에서 실행:

```powershell
python rag/jm/standard/run_standard.py --question "전세 계약할 때 꼭 확인해야 하는 기본 사항 알려줘"
```

### 주의
- 이 모듈은 DB/RAG 근거 검색을 하지 않습니다.
- 일반 설명용 모듈이므로 실제 계약서 검토나 법률 판단은 전문가 확인이 필요합니다.
