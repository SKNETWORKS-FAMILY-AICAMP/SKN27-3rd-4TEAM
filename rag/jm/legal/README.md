# rag/jm/legal

법률 상담 전용 RAG 에이전트입니다. PostgreSQL pgvector에 적재된 문서 중 `docs/pdf/law` 경로에서 온 chunk만 검색합니다.

## 역할

- 법령과 법률 상담 절차 문서만 근거로 사용
- `docs/pdf/judgement`, `docs/pdf/case`, 부동산 거래 테이블은 사용하지 않음
- 특약 작성과 표준계약서 해석은 별도 특약 에이전트 영역으로 분리
- 검색 근거가 부족하면 추가 검색을 한 번 더 수행
- 최종 답변에 참고한 법률 문서 출처와 법률 자문 한계를 함께 출력

## 법률 전용 Tools

- `legal_document_search_tool`: law 폴더의 법률 문서 전체에서 근거 검색
- `law_article_search_tool`: 사례집과 표준계약서를 제외하고 법령 조항 중심 검색
- `legal_answer_review_tool`: 답변 초안에 근거, 확인 사항, 법률 자문 한계가 들어갔는지 검토

## 실행

프로젝트 루트에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m rag.jm.legal.run_legal --question "임차인이 대항력을 갖추려면 무엇이 필요해?" --k 5
```

통합 CLI에서도 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m rag.jm.cli legal --query "임차인이 대항력을 갖추려면 무엇이 필요해?" --k 5
```
