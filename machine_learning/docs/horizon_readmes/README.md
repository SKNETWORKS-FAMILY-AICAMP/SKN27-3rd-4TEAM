# 전세 위험 예측 모델 Horizon별 결과 요약

이 문서는 `E:\dev\SKN27-3rd-4TEAM\machine_learning` 폴더의 모델 결과를 설명합니다. 현재 모델은 개별 주택 한 채의 실제 매매가를 직접 예측하는 것이 아니라, `동(dong_name) + 주택유형(property_type) + 월(month)` 단위의 시장 흐름을 학습합니다.

## 전처리 기준

- 순전세 데이터 중심으로 사용합니다.
- `floor < 0`인 지하/반지하층 거래는 학습 및 시세 산출 대상에서 제외했습니다.
- 지하/반지하 제외 후 거래 데이터는 21,329건, 월별 패널 데이터는 4,604행입니다.
- 저장된 `transactions_normalized.csv` 기준 음수 층수 거래는 0건입니다.

## 모델 에이전트에서의 역할

모델 에이전트는 계약서 또는 사용자 입력에서 `동`, `주택유형`, `계약월`, `보증금`, `전용면적`을 받아 가격 기반 전세 위험도를 계산합니다. 법률 판단, 판례 판단, 특약 문구 평가는 다른 에이전트가 담당하고, 이 모델은 시장 가격 위험만 담당합니다.

## 사용 모델

각 horizon마다 `lightgbm`, `xgboost`, `catboost`, `hist_gradient_boosting`, `random_forest`, `extra_trees`, `ensemble_mean`을 각각 평가했습니다. `ensemble_mean`은 `lightgbm + catboost + xgboost` 세 모델의 평균 앙상블입니다.

## Horizon별 Best Model

| Horizon | Best model | Valid MAPE | Baseline MAPE | ROC-AUC | F1 | Baseline 대비 MAPE 개선 | 누수 안전 | 과적합 경고 | Severe |
|---|---|---:|---:|---:|---:|---|---|---|---|
| 1개월 | `extra_trees` | 16.31% | 14.40% | 0.8938 | 0.8125 | 아니오 | 예 | 예 | 아니오 |
| 3개월 | `extra_trees` | 21.37% | 20.29% | 0.8460 | 0.7530 | 아니오 | 예 | 예 | 아니오 |
| 6개월 | `random_forest` | 23.84% | 26.16% | 0.8175 | 0.7331 | 예 | 예 | 예 | 아니오 |
| 12개월 | `extra_trees` | 24.95% | 29.73% | 0.8155 | 0.6876 | 예 | 예 | 예 | 아니오 |
| 24개월 | `lightgbm` | 27.03% | 29.63% | 0.7946 | 0.6218 | 예 | 예 | 예 | 예 |

## 해석

- 지하/반지하층 거래를 제외하면서 모델 결과는 지상층 기준 시세에 더 가까워졌습니다.
- 1개월, 3개월은 best model 기준으로도 baseline보다 MAPE가 낮지 않아 단기 참고 지표로만 보는 것이 좋습니다.
- 6개월, 12개월, 24개월은 baseline보다 MAPE가 개선되었습니다.
- 전세계약 기간 2년과 가장 잘 맞는 핵심 horizon은 24개월이며, 현재 best model은 `lightgbm`입니다.
- 24개월 모델은 개선은 되었지만 overfit severe가 있어 현재 전세가율, 면적구간 최근 12개월 시세, 법률/특약 에이전트 결과와 함께 해석해야 합니다.

## 실행 방법

```powershell
cd E:\dev\SKN27-3rd-4TEAM
.\.venv\Scripts\activate
python .\machine_learning\can_jeonse_forecast.py
```
