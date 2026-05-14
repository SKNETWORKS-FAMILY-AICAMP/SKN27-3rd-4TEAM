# 모델 에이전트 구현 체크리스트

이 문서는 모델 에이전트 담당자가 확인하면서 구현해야 할 내용을 정리한 작업용 문서입니다. 현재 모델은 `동(dong_name) + 주택유형(property_type) + 월(month)` 단위의 시장 흐름을 학습하고, 계약서 또는 사용자 입력으로부터 가격 기반 전세 위험도를 계산합니다.

## 1. 현재 전처리 기준

현재 머신러닝 모델은 지상층 기준 시세 산출을 위해 `floor < 0`인 지하/반지하층 거래를 제외합니다.

```text
floor < 0  → 지하/반지하층으로 보고 제외
floor >= 0 → 학습 및 시세 산출에 사용
floor 결측 → 데이터 손실 방지를 위해 일단 유지
```

지하/반지하층 제외 후 현재 산출물 기준은 아래와 같습니다.

```text
거래 데이터: 21,329건
지하 층수 거래: 0건
월별 패널 데이터: 4,604행
```

## 2. 현재 모델의 한계

모델은 가격을 총액이 아니라 평당가로 변환해 사용합니다.

```text
매매가 / 평수 = 매매 평당가
전세가 / 평수 = 전세 평당가
```

따라서 면적 차이가 완전히 무시된 것은 아니지만, 모델 학습 단위에 면적구간이 직접 들어가 있지는 않습니다.

```text
현재 학습 단위: 동 + 주택유형 + 월
부족한 부분: 동 + 주택유형 + 면적구간 + 월
```

## 3. 최종 수정 방향

모델 자체는 지상층 기준 horizon 모델을 유지하고, 모델 에이전트 단계에서 보조 판단을 추가합니다.

```text
1. 기존 horizon 모델 유지
2. 지하/반지하층 거래는 학습 데이터에서 제외
3. 사용자 계약이 지하/반지하층이면 모델 적용 제외 케이스로 반환
4. 면적구간별 최근 12개월 시세 비교 추가
5. 낮은 전세가 이상치 탐지 추가
6. current risk + forecast risk + area_bucket risk를 함께 반환
```

## 4. 입력 처리

모델 에이전트는 두 가지 입력을 받을 수 있어야 합니다.

```text
1. docx 계약서 파일
2. 텍스트로 입력된 계약 정보
```

최종적으로 아래 형태의 구조화 데이터로 만들어야 합니다.

```json
{
  "address": "서울특별시 종로구 신영동 179-21",
  "dong_name": "신영동",
  "property_type": "villa",
  "contract_date": "2025-05-12",
  "base_month": "2025-05",
  "deposit_amount_manwon": 28600,
  "exclusive_area_m2": 42.39,
  "exclusive_area_pyeong": 12.82,
  "floor": 3,
  "is_basement": false,
  "source_type": "docx"
}
```

## 5. 필수 입력값

아래 값이 없으면 모델을 돌리지 않고 추가 정보를 요청해야 합니다.

| 필드 | 설명 |
|---|---|
| `dong_name` | 동 이름, 예: 신영동 |
| `property_type` | 주택유형, `villa` 또는 `officetel` |
| `contract_date` 또는 `base_month` | 계약일 또는 계약월 |
| `deposit_amount_manwon` | 보증금, 만원 단위 |
| `exclusive_area_m2` 또는 `exclusive_area_pyeong` | 전용면적 |

## 6. 지하/반지하 계약 처리

계약서 또는 사용자 입력에서 아래 조건이 확인되면 일반 모델 위험도 산출을 하지 않습니다.

```text
floor < 0
is_basement = true
raw_text에 반지하, 지하, B1, basement 표현 포함
```

이 경우 모델 에이전트는 `excluded_case`를 반환하고, 법률 에이전트와 특약 에이전트의 별도 검토를 요청합니다.

```json
{
  "status": "excluded_case",
  "agent_name": "model_agent",
  "reason": "basement_or_underground_unit",
  "message": "반지하 또는 지하층 매물은 현재 지상층 기준 모델의 위험도 산출 대상에서 제외됩니다.",
  "recommended_next_agents": ["legal_agent", "special_terms_agent"]
}
```

## 7. 면적구간 계산

계약서에서 면적을 뽑으면 평수로 변환합니다.

```text
전용면적㎡ / 3.3058 = 평수
```

면적구간은 아래처럼 계산합니다.

| 면적 | area_bucket |
|---:|---|
| 10평 미만 | `10평 미만` |
| 10평 이상 20평 미만 | `10~20평` |
| 20평 이상 30평 미만 | `20~30평` |
| 30평 이상 | `30평 이상` |

## 8. 면적구간별 최근 12개월 시세 비교

기존 horizon 모델은 유지하되, 모델 에이전트에서 아래 보조 지표를 추가합니다.

```text
동 + 주택유형 + 면적구간 기준 최근 12개월 평균 매매 평당가
동 + 주택유형 + 면적구간 기준 최근 12개월 평균 전세 평당가
```

## 9. 낮은 전세가 이상치 탐지

계약 전세가가 낮다고 무조건 안전하다고 판단하지 않습니다. 아래 조건이면 저가 이상치로 표시합니다.

```text
계약 전세 평당가 < 면적구간 전세 평당가 × 0.85
```

## 10. 위험 등급 기준

| 위험비율 | 등급 |
|---:|---|
| 0.70 미만 | 안전 |
| 0.70 이상 0.80 미만 | 주의 |
| 0.80 이상 0.90 미만 | 위험 |
| 0.90 이상 1.00 미만 | 고위험 |
| 1.00 이상 | 깡통 가능성 매우 높음 |

## 11. 구현 순서

```text
1. model_agent.py 생성
2. docx 계약서 파싱 함수 작성
3. 텍스트 입력 파싱 함수 작성
4. 필수값 검증 함수 작성
5. 지하/반지하 제외 케이스 판별 함수 작성
6. 면적구간 계산 함수 작성
7. 면적구간별 최근 12개월 시세 계산 함수 작성
8. 낮은 전세가 이상치 탐지 함수 작성
9. current risk + forecast risk + area_bucket risk output 작성
10. 샘플 계약서로 테스트
```

## 12. 현재 구현된 연결 파일

현재 Supervisor 연결용 모델 에이전트는 아래 파일에 구현되어 있습니다.

```text
machine_learning/model_agent.py
```

Supervisor 또는 다른 Python 코드에서는 아래처럼 호출하면 됩니다.

```python
from machine_learning.model_agent import analyze_contract

result = analyze_contract({
    "contract_id": "contract_001",
    "dong_name": "신영동",
    "property_type": "villa",
    "contract_date": "2025-05-12",
    "deposit_amount_manwon": 28600,
    "exclusive_area_m2": 42.39,
    "floor": 3,
    "is_basement": False,
})
```

터미널에서 단독 테스트할 때는 아래 명령을 사용합니다.

```powershell
cd E:\dev\SKN27-3rd-4TEAM
.\.venv\Scripts\activate
python .\machine_learning\model_agent.py --demo
python .\machine_learning\model_agent.py --json .\machine_learning\docs\model_agent_sample_input.json
```

현재 구현은 24개월 LightGBM 모델을 primary forecast로 사용하고, 12개월 ExtraTrees 모델을 supporting forecast로 함께 반환합니다. 현재 시장 위험도, 면적구간 최근 12개월 비교, 예측 위험도를 함께 계산합니다.
