# 전세 사기 분석 — 안전계약 (Streamlit)

서울 종로구 한정 전세 사기 위험도 분석 챗봇 — 등기부등본/계약서를 업로드하면
사용자의 자료를 근거로 위험도를 진단하고 사례·판례·법령을 인용해 답변합니다.

## 실행

```bash
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

기본 포트는 8501. 브라우저에서 자동으로 열립니다.

## 구조

```
streamlit_app/
├─ app.py                 # 메인 라우터 + 사이드바 + 공통 CSS
├─ views/
│  ├─ chat.py             # 상담 챗 (메인) — 진단 결과 + RAG 챗봇
│  ├─ history.py          # 내 진단 기록 — 필터/즐겨찾기/비교
│  ├─ simulator.py        # 깡통전세 시뮬레이터
│  ├─ playbook.py         # 사례·판례 플레이북 + 변호사 상담 키트
│  └─ checklist.py        # 안전 체크리스트
├─ utils/
│  ├─ styles.py           # 공통 CSS (토스 스타일)
│  ├─ data.py             # 종로구 실거래가 CSV 로더
│  └─ components.py       # 재사용 위젯 (위험도 뱃지, 카드 등)
├─ assets/
└─ requirements.txt
```

## 데이터

- `../data/jongno_jeonse_2025.csv` — 2025 종로구 전세 실거래가 (국토부)
- 그 외 사례/판례/법령은 데모 데이터로 인라인되어 있습니다.

## 다음 단계

- 실제 RAG 파이프라인 연결 (사례·판례 PDF 임베딩)
- 국토부 실거래가 API 연동
- HUG / 렌트홈 임대인 검증
- PDF 리포트 생성
