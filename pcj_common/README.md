# pcj_common - PDF 검토 에이전트

전세 계약서(docx/pdf)에서 필수 항목을 추출하고, 누락된 항목을 supervisor에 반환하는 서브 에이전트 패키지입니다.

---

## 파일 구조

```
pcj_common/
├── agents/
│   └── pdf_review_agent.py     # 에이전트 진입점
├── tools/
│   └── contract_tools.py       # @tool 함수 정의
└── tests/
    ├── test_pdf_review_agent.py # 단위 테스트 (mock)
    ├── test_real_contract.py    # 실제 계약서 테스트
    ├── fixtures.py              # 테스트용 가상 계약서 텍스트
    ├── valid_contract.docx      # 필수 항목 전체 포함 테스트 파일
    └── missing_deposit_period.docx  # 전세금·기간 누락 테스트 파일
```

---

## 핵심 파일 설명

### `tools/contract_tools.py`

에이전트가 사용하는 `@tool` 함수 2개가 정의되어 있습니다.

#### `parse_contract_document(file_path)`
계약서 파일을 읽어 구조화된 텍스트로 반환합니다.

- docx의 경우 테이블 구조를 코드로 직접 분석해 각 필드를 정확한 섹션에서 추출합니다.
- LLM이 다른 섹션의 값을 혼동하지 않도록 섹션별로 명확하게 레이블링합니다.
- 항목이 없으면 `"없음"`으로 표시합니다.

반환 예시:
```
=== 계약서 구조화 정보 (코드 추출) ===

[ 계약 당사자 ]
임대사업자(임대인) 이름 : 오성호
임차인 이름             : 최유진

[ 임대 목적물 ]
주택 소재지 : 서울특별시 종로구 평창동 329-2 럭키평창빌라 제101호
주택 유형   : 다세대주택
전용면적    : 84.84

[ 계약 조건 ]
전세금(임대보증금) : 400000000
임대 기간          : 2025-02-25 ~ 2027-02-24

[ 특약사항 ]
1. 본 주택에는 ○○저축은행 명의의 근저당권...
2. 임대인은 본 보증금 중 일부...
```

추출 필드와 소스 테이블:

| 필드 | 소스 |
|---|---|
| 임대인 이름 | TABLE 0 - `임대사업자 \| 성명(법인명) \| 이름` |
| 임차인 이름 | TABLE 0 - `임차인 \| 성명(법인명) \| 이름` |
| 주택 소재지 | TABLE 2 - `주택 소재지 \| 주소` |
| 주택 유형 | TABLE 2 - `주택 유형 \| ...[■]...` |
| 전용면적 | TABLE 2 - `민간임대주택면적 \| 주거전용면적: XX ㎡` |
| 전세금 | TABLE 3 - `금액 \| ...(₩XXX,XXX,XXX)` |
| 임대 기간 | TABLE 3 - `임대차계약기간 \| YYYY-MM-DD ∼ YYYY-MM-DD` |
| 특약사항 | TABLE 6 - 번호가 붙은 항목들 |

---

#### `check_required_fields(extracted_json)`
LLM이 구조화 텍스트를 읽고 만든 JSON을 받아 필수 항목 누락 여부를 검증합니다.

필수 항목 (없으면 fail):

| JSON 키 | 한국어 |
|---|---|
| `landlord` | 임대인 |
| `tenant` | 임차인 |
| `address` | 주소 |
| `area` | 주택 면적 |
| `housing_type` | 주택 유형 |
| `deposit` | 전세금 |
| `period` | 계약 기간 |

선택 항목 (없어도 됨):

| JSON 키 | 설명 |
|---|---|
| `special_terms` | 특약사항 문자열 리스트, 없으면 `[]` |

반환 형식:
```json
// 성공
{"status": "success", "data": {...}, "message": "..."}

// 실패 (supervisor로 반환)
{"status": "fail", "missing_fields": ["임대인", "주소"], "message": "..."}
```

---

### `agents/pdf_review_agent.py`

supervisor가 호출하는 에이전트 팩토리입니다.

```python
# supervisor에서 이렇게 사용
from pcj_common.agents.pdf_review_agent import run_pdf_review_agent

result_str = run_pdf_review_agent("docs/계약서.docx")
result = json.loads(result_str)

if result["status"] == "fail":
    # 누락 항목 목록: result["missing_fields"]
    # 다음 노드로 넘어가지 않음
else:
    # 추출 데이터: result["data"]
    # 다음 노드로 진행
```

내부 동작 순서:
1. `parse_contract_document` 툴로 계약서를 구조화 텍스트로 변환
2. LLM이 구조화 텍스트를 읽고 JSON 생성
3. `check_required_fields` 툴로 필수 항목 검증
4. 결과 반환

---

### `tests/`

| 파일 | 설명 |
|---|---|
| `test_pdf_review_agent.py` | `parse_contract_document`, `check_required_fields` 단위 테스트 (16개, mock 기반) |
| `test_real_contract.py` | `docs/가상계약서.docx` 기반 통합 테스트 (19개 mock + 9개 live) |
| `fixtures.py` | 테스트용 가상 계약서 텍스트 픽스처 |
| `valid_contract.docx` | 7개 필수 항목 전부 포함된 테스트용 docx |
| `missing_deposit_period.docx` | 전세금·임대기간 누락 테스트용 docx |

테스트 실행:
```powershell
# mock 테스트만 (LLM 불필요)
$env:PYTHONPATH = "."; python -m pytest pcj_common/tests/ -v -m "not live"

# 실제 LLM 포함 전체 테스트
$env:PYTHONPATH = "."; python -m pytest pcj_common/tests/ -v -m live
```
