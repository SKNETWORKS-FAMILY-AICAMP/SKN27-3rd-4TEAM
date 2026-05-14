# Modeling Horizon Forecasts

이 폴더는 전세 위험도 판단을 위해 `동(dong_name) + 주택유형(property_type) + 월(month)` 단위의 월별 패널 데이터를 만들고, horizon별 미래 매매 평당가를 예측합니다.

## 예측 단위

기본 예측 단위는 다음과 같습니다.

```text
동 + 주택유형 + 월
예: 숭인동 + officetel + 2025-12
```

각 월별로 매매 평당가, 전세 평당가, 매매/전세 거래 수, 평균 층수, 평균 건물연식, 전세가율, 과거 lag/rolling 변수를 생성합니다. `sale_roll_mean_12`, `jeonse_roll_mean_12` 같은 rolling 변수는 `shift(1)`을 적용해 현재 월 이후 데이터가 들어가지 않도록 했습니다.

## Horizon 의미

각 horizon은 현재 월 기준 몇 개월 뒤의 매매가 상승률을 예측할지 의미합니다.

| horizon | 의미 |
|---:|---|
| 1m | 1개월 뒤 매매가 예측 |
| 3m | 3개월 뒤 매매가 예측 |
| 6m | 6개월 뒤 매매가 예측 |
| 12m | 12개월 뒤 매매가 예측 |
| 24m | 24개월 뒤 매매가 예측 |

최종 위험도는 다음 방식으로 계산합니다.

```text
현재 전세 평당가 / 예측 미래 매매 평당가
```

## 사용 모델

각 horizon마다 아래 모델을 각각 따로 학습하고 평가합니다.

| model_name | 설명 |
|---|---|
| lightgbm | LightGBM Regressor |
| xgboost | XGBoost Regressor |
| hist_gradient_boosting | scikit-learn HistGradientBoostingRegressor |
| random_forest | RandomForestRegressor |
| extra_trees | ExtraTreesRegressor |
| catboost | CatBoostRegressor, 설치되어 있을 때만 자동 포함 |
| ensemble_mean | `lightgbm + catboost + xgboost` 세 모델의 예측 평균 앙상블 |

즉 이제는 “대체 모델 하나”만 쓰는 구조가 아니라, `horizon x model_name` 단위로 성능을 비교합니다.

## 검증 방식

모든 모델에 동일한 검증 기준을 적용합니다.

- horizon별 purged time split 적용
- validation 시작월과 train label 기간이 겹치지 않도록 `horizon + 1`개월 gap 적용
- target/future 컬럼은 feature에서 제외
- train metrics와 validation metrics를 모두 저장
- naive baseline 저장: 미래 매매가를 현재 매매가와 같다고 보는 기준선
- leakage audit 저장
- overfit audit 저장

## 실행 방법

전체 horizon과 전체 모델을 한 번에 실행합니다.

```powershell
cd E:\dev\SKN27-3rd-4TEAM
.\.venv\Scripts\activate
python .\machine_learning\can_jeonse_forecast.py
```

특정 horizon만 실행하려면 아래처럼 실행합니다.

```powershell
python .\machine_learning\can_jeonse_forecast_1m.py
python .\machine_learning\can_jeonse_forecast_3m.py
python .\machine_learning\can_jeonse_forecast_6m.py
python .\machine_learning\can_jeonse_forecast_12m.py
python .\machine_learning\can_jeonse_forecast_24m.py
```

## 주요 결과 파일

```text
machine_learning/artifacts/can_jeonse/metrics.csv
machine_learning/artifacts/can_jeonse/metrics.json
machine_learning/artifacts/can_jeonse/best_models.csv
machine_learning/artifacts/can_jeonse/best_models.json
machine_learning/artifacts/can_jeonse/can_jeonse_risk_24m.csv
machine_learning/artifacts/can_jeonse/summary.json
```

`metrics.csv`는 모든 horizon과 모든 model_name의 성능표입니다. `best_models.csv`는 horizon별로 validation MAPE가 가장 낮은 모델만 모은 요약표입니다.

## 모델별 저장 위치

각 horizon별 모델 파일은 아래처럼 저장됩니다.

```text
machine_learning/artifacts/can_jeonse/models/1m/lightgbm.joblib
machine_learning/artifacts/can_jeonse/models/1m/xgboost.joblib
machine_learning/artifacts/can_jeonse/models/1m/hist_gradient_boosting.joblib
machine_learning/artifacts/can_jeonse/models/1m/random_forest.joblib
machine_learning/artifacts/can_jeonse/models/1m/extra_trees.joblib
machine_learning/artifacts/can_jeonse/models/1m/ensemble_mean.joblib
```

동일한 구조가 `3m`, `6m`, `12m`, `24m`에도 생성됩니다.

## 모델별 평가 저장 위치

각 horizon별 모델 평가 JSON은 아래처럼 저장됩니다.

```text
machine_learning/artifacts/can_jeonse/horizon_metrics/1m/lightgbm_metrics.json
machine_learning/artifacts/can_jeonse/horizon_metrics/1m/xgboost_metrics.json
machine_learning/artifacts/can_jeonse/horizon_metrics/1m/hist_gradient_boosting_metrics.json
machine_learning/artifacts/can_jeonse/horizon_metrics/1m/random_forest_metrics.json
machine_learning/artifacts/can_jeonse/horizon_metrics/1m/extra_trees_metrics.json
machine_learning/artifacts/can_jeonse/horizon_metrics/1m/ensemble_mean_metrics.json
machine_learning/artifacts/can_jeonse/horizon_metrics/1m/all_model_metrics.json
```

각 JSON에는 train/valid 지표, baseline 지표, leakage audit, overfit audit이 함께 들어갑니다.



## 지하/반지하층 제외 기준

현재 머신러닝 전처리에서는 `floor < 0`인 거래를 지하/반지하층으로 보고 학습 및 시세 산출 대상에서 제외합니다. 따라서 모델 결과는 지상층 거래를 기준으로 한 동별·주택유형별 평당가 및 예측 위험도입니다.

계약서 또는 사용자 입력에서 반지하/지하층이 확인되는 경우, 모델 에이전트는 해당 계약을 일반 모델 위험도 산출 대상에서 제외하거나 `excluded_case`로 반환하고, 법률/특약 에이전트의 별도 검토를 요청해야 합니다.


## 서비스/에이전트 최종 사용 모델

최종 서비스 연결 모델은 `24개월 LightGBM` 하나로 고정합니다.

- 최종 가격 예측: 24개월 LightGBM
- 최종 가격 위험도: 계약 전세 평당가 / 24개월 LightGBM 예측 매매 평당가
- 현재 시세 위험도와 면적구간 최근 12개월 시세 위험도는 설명 근거로만 사용
- 12개월 모델은 더 이상 모델 에이전트에서 호출하지 않음

24개월 LightGBM을 선택한 이유는 전세계약의 일반적인 만기인 2년과 가장 직접적으로 연결되고, 24개월 horizon 후보 중 Valid MAPE가 가장 낮았기 때문입니다. 다만 overfit severe 경고가 있으므로 모델 결과만 단독 결론으로 쓰지 않고, 현재 시세/면적구간 시세/법률/특약 검토와 함께 설명해야 합니다.
