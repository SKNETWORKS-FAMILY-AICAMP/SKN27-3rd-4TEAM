# 모델 에이전트 최종 구현 가이드

## 1. 최종 결정

모델 에이전트는 최종적으로 `24개월 LightGBM` 모델 하나만 사용합니다.

```text
최종 가격 예측 = 24개월 LightGBM
최종 가격 위험도 = 계약 전세 평당가 / 24개월 LightGBM 예측 매매 평당가
```

12개월 ExtraTrees 참고 예측은 더 이상 모델 에이전트에서 호출하지 않습니다. 현재 시세 위험도와 면적구간 최근 12개월 시세 위험도는 최종 등급을 바꾸지 않고, 챗봇이 사용자를 설득력 있게 설명하기 위한 근거로만 반환합니다.

## 2. 왜 24개월 LightGBM을 최종 모델로 쓰는가

전세계약은 보통 2년이므로 사용자가 알고 싶은 핵심은 계약 만기 시점의 보증금 회수 위험입니다. 따라서 1개월, 3개월, 6개월, 12개월보다 `24개월 뒤 매매가`를 예측하는 모델이 서비스 목적과 가장 직접적으로 연결됩니다.

24개월 horizon 후보 모델 중에서는 LightGBM이 가장 좋은 가격 예측 성능을 보였습니다.

| 모델 | Valid MAPE | Baseline MAPE | Baseline보다 개선 | ROC-AUC | F1 |
|---|---:|---:|---|---:|---:|
| LightGBM | 27.03% | 29.63% | 예 | 0.7946 | 0.6218 |
| Ensemble Mean | 28.46% | 29.63% | 예 | 0.7894 | 0.5607 |
| CatBoost | 30.00% | 29.63% | 아니오 | 0.7779 | 0.5701 |
| XGBoost | 30.42% | 29.63% | 아니오 | 0.7763 | 0.5973 |

그래서 최종 에이전트 연결은 앙상블이나 12개월 모델이 아니라 `growth_24m_best_model.joblib`에 저장된 24개월 LightGBM을 사용합니다.

## 3. Purge Gap 적용 여부와 의미

현재 학습/검증 코드에는 horizon별 purge gap이 적용되어 있습니다.

파일 위치:

```text
machine_learning/can_jeonse_forecast.py
build_purged_time_split()
```

purge gap은 train 데이터의 미래 정답월이 valid 구간과 겹치지 않도록 학습 구간 끝을 일부러 앞당기는 방식입니다. 예를 들어 24개월 예측 모델은 `현재 월 + 24개월`의 매매가를 정답으로 사용하므로, valid 시작월 이후의 가격이 train label에 섞이면 데이터 누수가 됩니다.

현재 저장된 best model 기준 검증 결과는 아래와 같습니다.

| Horizon | Best model | Purge gap | Train 종료월 | Valid 시작월 | Label overlap | Leakage safe |
|---:|---|---:|---|---|---:|---|
| 1개월 | ExtraTrees | 2개월 | 2023-12 | 2024-02 | 0 | True |
| 3개월 | ExtraTrees | 4개월 | 2023-09 | 2024-01 | 0 | True |
| 6개월 | RandomForest | 7개월 | 2023-03 | 2023-10 | 0 | True |
| 12개월 | ExtraTrees | 13개월 | 2022-04 | 2023-05 | 0 | True |
| 24개월 | LightGBM | 25개월 | 2020-07 | 2022-08 | 0 | True |

핵심은 아래 두 값입니다.

```text
train_label_overlap_into_valid_rows = 0
is_leakage_safe_for_validation = True
```

따라서 이전에 우려했던 “학습 라벨이 검증 구간의 미래 정답을 포함하는 데이터 누수”는 현재 구조에서 차단되어 있습니다.

단, purge gap은 데이터 누수를 막는 장치이지 과적합 자체를 없애는 장치는 아닙니다. 현재 24개월 LightGBM은 데이터 누수는 차단되었지만 overfit severe 경고가 있으므로, 결과 설명 시 이 한계를 함께 알려야 합니다.

## 4. 모델 에이전트 입력

Supervisor는 계약서 docx 또는 사용자 텍스트를 먼저 구조화한 뒤, 모델 에이전트에 아래 dict를 전달합니다. 모델 에이전트는 docx 파일 자체를 직접 파싱하지 않습니다.

```json
{
  "contract_id": "contract_001",
  "source_type": "docx",
  "address": "서울특별시 종로구 신영동 179-21",
  "dong_name": "신영동",
  "property_type": "villa",
  "contract_date": "2025-05-12",
  "deposit_amount_manwon": 28600,
  "exclusive_area_m2": 42.39,
  "floor": 3,
  "is_basement": false,
  "raw_text": "계약서에서 추출한 원문 일부"
}
```

필수값은 아래입니다.

```text
dong_name
property_type
contract_date 또는 base_month
deposit_amount_manwon
exclusive_area_m2 또는 exclusive_area_pyeong
```

필수값이 부족하면 모델을 억지로 실행하지 않고 `need_more_info`와 `required_input_request`를 반환합니다.

## 5. 모델 에이전트 처리 흐름

```text
1. contract_info 입력 수신
2. 주소/주택유형/보증금/면적/계약월 정규화
3. 필수값 부족 여부 확인
4. 반지하/지하층 여부 확인
5. 현재 시세 위험도 계산
6. 면적구간 최근 12개월 시세 위험도 계산
7. 24개월 LightGBM 예측 실행
8. 최종 가격 위험도 계산
9. price_evidence로 Supervisor에 계산 근거 반환
```

반지하 또는 지하층은 현재 지상층 기준 모델의 적용 대상이 아니므로 `excluded_case`를 반환합니다.

## 6. 위험도 계산 방식

계약 전세 평당가는 아래처럼 계산합니다.

```text
계약 전세 평당가 = 보증금 / 전용면적 평수
```

최종 가격 위험도는 아래 하나의 공식으로 산정합니다.

```text
최종 가격 위험비율 = 계약 전세 평당가 / 24개월 LightGBM 예측 매매 평당가
```

위험비율 등급은 아래 기준을 사용합니다.

| 위험비율 | 위험도 |
|---:|---|
| 0.70 미만 | 안전 |
| 0.70 이상 0.80 미만 | 주의 |
| 0.80 이상 0.90 미만 | 위험 |
| 0.90 이상 1.00 미만 | 고위험 |
| 1.00 이상 | 깡통 가능성 매우 높음 |

`final_market_risk`와 `price_evidence.risk`는 항상 24개월 LightGBM 예측 위험도와 동일합니다.

## 7. 보조 설명으로만 사용하는 값

아래 값들은 최종 위험등급을 바꾸지 않습니다.

| 항목 | 용도 |
|---|---|
| 현재 시세 위험도 | 계약 전세가가 현재 시장 매매가 대비 높은지 설명 |
| 면적구간 최근 12개월 시세 위험도 | 사용자의 전용면적대 기준으로 전세가가 높은지 설명 |
| 저전세가율/저가 이상치 탐지 | 보증금이 낮아 보이는 계약에서 별도 비용, 권리관계, 하자 가능성 안내 |

12개월 ExtraTrees 예측은 최종 구조에서 제거했습니다.

## 8. 모델 에이전트 성공 Output 핵심 구조

```json
{
  "status": "success",
  "agent_name": "model_agent",
  "risk_type": "market_price_risk",
  "current_market_check": {},
  "area_bucket_check": {},
  "price_position_check": {},
  "low_jeonse_ratio_check": {},
  "forecast_check": {
    "primary": {
      "horizon_months": 24,
      "model_name": "lightgbm",
      "forecast_sale_per_pyeong": 2347.0,
      "forecast_risk_ratio": 0.95,
      "forecast_risk_level": "고위험"
    }
  },
  "price_evidence": {
    "final_prediction_model": "24m_lightgbm",
    "final_risk_basis": "contract_jeonse_per_pyeong / forecast_sale_per_pyeong_24m",
    "sale_price": 2347.0,
    "sale_price_type": "24개월 LightGBM 예측 매매 평당가",
    "jeonse_price": 2230.0,
    "jeonse_price_type": "계약 전세 평당가",
    "jeonse_ratio": 0.95,
    "risk": "고위험",
    "calculation_basis": "계약 전세 평당가를 24개월 LightGBM 예측 매매 평당가로 나눈 값입니다.",
    "supporting_evidence": {
      "current_market": {},
      "area_bucket_recent_12m": {}
    }
  },
  "model_quality": {
    "leakage_safe": true,
    "overfit_warning": true,
    "overfit_severe": true
  },
  "final_market_risk": "고위험"
}
```

Supervisor는 `price_evidence`를 가격 판단 근거로 사용하면 됩니다.

## 9. Supervisor에게 전달할 요약

```text
모델 에이전트는 계약서 또는 사용자 입력에서 추출된 동, 주택유형, 계약일, 보증금, 전용면적, 층수 정보를 받아 가격 기반 전세 위험도를 계산합니다. 최종 예측 모델은 24개월 LightGBM 하나이며, 최종 가격 위험도는 계약 전세 평당가를 24개월 예측 매매 평당가로 나누어 산정합니다. 현재 시세 위험도와 면적구간 최근 12개월 시세 위험도는 최종 등급을 바꾸지 않고 설명 근거로만 사용합니다. 반지하/지하층은 모델 적용 대상에서 제외하고, 필수값이 부족하면 사용자에게 추가 정보를 요청합니다. 모델 검증에는 horizon별 purge gap을 적용해 train label과 valid 구간의 미래 정답이 겹치는 데이터 누수를 차단했습니다.
```

## 10. 실행 방법

모델 에이전트 단독 테스트:

```powershell
cd E:\dev\SKN27-3rd-4TEAM
.\.venv\Scriptsctivate
python .\machine_learning\model_agent.py --demo
```

전체 모델 재학습/평가:

```powershell
python .\machine_learning\can_jeonse_forecast.py
```

24개월 모델만 재학습/평가:

```powershell
python .\machine_learning\can_jeonse_forecast_24m.py
```
