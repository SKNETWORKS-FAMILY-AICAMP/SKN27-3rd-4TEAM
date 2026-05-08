# 전세계약 위험 진단 멀티 에이전트 설계

## 1. 설계 원칙

이 프로젝트는 **전세계약서 1개만 입력**으로 받아 전세사기 위험을 진단한다. 등기부등본, 중개대상물 확인설명서, 전입세대확인서 등은 직접 업로드 분석 대상이 아니라, 계약서만으로 확인할 수 없는 필수 확인 항목으로 리포트와 Q&A에서 안내한다.

```text
분석 리포트 생성 = 통제된 LangGraph 파이프라인
사용자 자유 질문 = ReAct Q&A Agent
RAG/시세 조회 = MCP로 분리 가능한 외부 도구
점수 계산 = 규칙 기반
LLM 역할 = 추출, 해석, 쉬운 말 설명
```

## 2. 전체 Graph 구조

### Analysis Graph

```text
START
→ Contract Intake
→ Contract Parser
→ Contract Field Extraction
→ Special Clause Analyzer
→ Market Analyzer
→ Risk Judge
→ Report Writer
→ END
```

현재는 Sequential Graph로 구현한다. 데이터 레이어와 노드 입출력이 안정되면 Controlled Supervisor Graph로 확장한다.

### Q&A Graph

```text
START
→ Context Loader
→ ReAct Q&A Agent
→ Citation Formatter
→ END
```

## 3. 에이전트 목록

| 에이전트 | 타입 | ReAct 여부 | MCP 사용 | 역할 |
|---|---|---:|---:|---|
| Contract Intake Agent | LangGraph Agent | X | X | 전세계약서 업로드 확인 |
| Contract Parser Agent | LangGraph Agent | X | X | 계약서 PDF/이미지 텍스트 추출, OCR fallback |
| Contract Field Extraction Agent | LangGraph Agent | X | X | 계약서 핵심 필드 구조화 |
| Special Clause Analyzer Agent | LangGraph Agent | X | O | 위험 특약 탐지, 방어 특약 누락 확인 |
| Market Analyzer Agent | LangGraph Agent | X | O | 실거래가 기반 시세 분석, 전세가율 산정 |
| Risk Judge Agent | LangGraph Agent | X | X | 특약, 시세, 확인 필요 항목을 종합해 규칙 기반 위험 점수 계산 |
| Report Writer Agent | LangGraph Agent | X | O | 최종 리포트와 체크리스트 생성 |
| ReAct Q&A Agent | ReAct Agent | O | O | 사용자 질문에 맞는 도구를 선택해 근거 기반 답변 생성 |

## 4. Agent별 상세 설계

### 4.1 Contract Intake Agent

**역할**

```text
전세계약서 업로드 여부 확인
분석 가능 여부 판단
```

**입력 데이터**

```text
전세계약서 PDF/이미지
```

**출력**

```text
documents
missing_documents
analysis_ready
```

### 4.2 Contract Parser Agent

**역할**

```text
계약서 PDF 텍스트 추출
스캔/이미지 OCR fallback
페이지별 raw text 생성
OCR 신뢰도 저장
```

**출력**

```text
parsed_texts
ocr_confidence
```

### 4.3 Contract Field Extraction Agent

**역할**

```text
계약서 원문에서 전세 위험 진단에 필요한 필드를 구조화한다.
```

**추출 필드**

```text
임대인
임차인
목적물 주소
보증금
계약기간
주택유형
특약사항
```

### 4.4 Special Clause Analyzer Agent

**역할**

```text
계약서 특약사항을 분석한다.
위험 특약을 탐지한다.
방어 특약이 있는지 확인한다.
누락된 방어 특약과 수정 권장 문구를 제안한다.
```

**가져오는 데이터**

```text
계약서 특약사항
위험 특약 패턴 RAG
방어 특약 패턴 RAG
전세사기 예방 A to Z
HUG 전세사기 예방자료
표준계약서/공공 가이드
```

**주요 판단 항목**

```text
보증금 반환 지연 특약
수리비 과도 전가 특약
전입신고/확정일자 지연 특약
추가 담보권 설정 허용 특약
권리변동 면책 특약
관리비 불명확 특약
근저당 말소 특약 누락
추가 권리설정 금지 특약 누락
```

### 4.5 Market Analyzer Agent

**역할**

```text
전세 실거래가와 매매 실거래가를 사용해 시세 위험을 분석한다.
전세가율을 계산하고 주택유형별 분석 신뢰도를 산정한다.
```

**가져오는 데이터**

```text
계약서 보증금
목적물 주소
주택유형
전세 실거래가
매매 실거래가
법정동 코드
```

**주택유형별 처리**

```text
연립다세대/오피스텔:
유사 면적, 유사 연식, 같은 동 기준으로 비교한다.

단독/다가구:
공개 데이터의 지번, 면적, 층 정보가 부족하므로 동 단위 보증금 분포만 참고한다.
분석 신뢰도를 낮음으로 표시한다.
```

### 4.6 Risk Judge Agent

**역할**

```text
특약 분석 결과, 시세 분석 결과, 계약서만으로 확인할 수 없는 필수 확인 항목을 종합한다.
규칙 기반으로 위험 점수와 위험 단계를 계산한다.
```

**계약서만으로 직접 판단하는 항목**

```text
보증금
주소
주택유형
계약기간
특약 위험
방어 특약 누락
시세 대비 보증금 위험
전세가율 추정
```

**계약서만으로 직접 판단하지 않는 항목**

```text
근저당권
압류/가압류/가처분
신탁 등기
임대인/소유자 일치 여부
선순위 임차인
전입세대확인서
확정일자 부여현황
국세/지방세 체납
위반건축물 여부
```

이 항목들은 위험 발생으로 단정하지 않고 `확인 필요 finding`으로 리포트에 표시한다.

**예시 규칙**

```text
위험 특약 존재 +15
높은 전세가율 +25
시세 분석 신뢰도 낮음 +5
등기부등본 확인 필요 +10
임대인/소유자 일치 여부 확인 필요 +10
단독/다가구 선순위 임차인 확인 필요 +10
```

### 4.7 Report Writer Agent

**역할**

```text
분석 결과를 사용자 친화적인 리포트로 변환한다.
법률 자문처럼 단정하지 않고, 위험 가능성과 확인 필요 사항을 설명한다.
```

**출력**

```text
report_summary
risk_cards
checklist
citations
disclaimer
```

### 4.8 ReAct Q&A Agent

**역할**

```text
사용자 질문을 보고 필요한 tool을 선택한다.
계약서 근거, RAG 지식, 시세 데이터를 조합해 답변한다.
계약서만으로 확인할 수 없는 등기부/권리관계 질문은 확인 불가와 필요 서류를 안내한다.
```

**사용 가능한 도구**

```text
RAG Search MCP
Market Data MCP
Contract Evidence MCP, 선택
get_risk_report
get_risk_findings
get_session_fields
```

## 5. MCP로 만들 항목

### 5.1 RAG Search MCP

```text
법령, 공공 가이드, 위험 특약, 방어 특약, 등기부 확인 체크리스트 검색
```

### 5.2 Market Data MCP

```text
전세/매매 실거래가 조회
전세가율 계산
주택유형별 시세 분석 신뢰도 반환
```

### 5.3 Contract Evidence MCP, 선택

```text
계약서 원문/특약사항 근거 검색
페이지/섹션 단위 citation 반환
```

## 6. 계약서 단일 입력 정책 반영 사항

MVP 입력은 전세계약서만 받는다.

계약서로 직접 분석하는 항목:

```text
보증금
주소
주택유형
계약기간
특약사항
방어 특약 누락
시세 대비 보증금 위험
전세가율 추정
```

계약서만으로 직접 판단하지 않는 항목:

```text
근저당권
압류/가압류/가처분
신탁 등기
임대인/소유자 일치 여부
선순위 임차인
전입세대확인서
확정일자 부여현황
국세/지방세 체납
위반건축물 여부
```

위 항목들은 위험 발생으로 단정하지 않고 `확인 필요 finding`으로 리포트에 표시한다.

## 7. 실제 데이터 연결 현황

현재 `Market Analyzer Agent`는 `data/` 폴더의 CSV를 직접 읽어 분석한다.

```text
전세 데이터:
data/2025_전세_종로구_통합_cleaned.csv

매매 데이터:
data/fixed_연립다세대(매매)_실거래가_20260507195717.csv
data/fixed_오피스텔(매매)_실거래가_20260507195801.csv
```

분석 방식:

```text
1. 계약서에서 주소, 보증금, 주택유형을 추출한다.
2. 주소에서 법정동 이름을 추출한다.
3. 주택유형과 동 이름 기준으로 전세 거래 샘플을 필터링한다.
4. 전세 보증금 중앙값과 사용자 보증금 분위수를 계산한다.
5. 매매 거래 중앙값이 있으면 전세가율을 계산한다.
6. 샘플 수와 주택유형에 따라 confidence를 low/medium/high로 표시한다.
```

`RAG Search MCP`는 DB가 설정되어 있으면 `rag_documents` 테이블을 우선 검색하고, DB가 없으면 `docs/pdf/pdf` 파일 목록과 내장 위험 패턴을 fallback으로 사용한다.

## 8. 로컬 LLM 연결 현황

현재 LLM은 로컬 Ollama HTTP API로 연결한다.

```text
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma4:e2b
```

LLM을 사용하는 노드:

```text
Contract Field Extraction Agent
- 계약서 텍스트에서 구조화 필드 JSON 추출
- 실패 시 regex fallback 사용

Special Clause Analyzer Agent
- 특약 문장을 위험 유형, severity, reason, recommendation으로 해석
- 점수 계산은 하지 않고 finding 설명을 보강

Report Writer Agent
- 규칙 기반 리포트에 사용자 친화적 LLM 요약을 추가

ReAct Q&A Agent
- 검색 근거와 분석 컨텍스트를 바탕으로 자유 질문 답변 생성
```

LLM이 직접 하지 않는 일:

```text
위험 점수 계산
전세가율 계산
시세 샘플 필터링
최종 위험 단계 산정
```

위 항목은 재현성과 안전성을 위해 코드/규칙 기반으로 유지한다.
