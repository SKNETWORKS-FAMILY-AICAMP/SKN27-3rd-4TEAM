# 머신러닝 모델 및 모델 에이전트 최종 정리

작성 기준: `E:\dev\SKN27-3rd-4TEAM\machine_learning`

이 문서는 지금까지 구현한 머신러닝 분석, 전처리 방식, 모델별 평가 결과, 최종 선택 모델, 모델 에이전트 연결 구조, 사용/미사용 파일 검토 결과를 정리한 최종 인수인계 문서입니다.

## 1. 현재 폴더 기준

현재 실제로 사용하는 머신러닝 폴더는 아래 하나입니다.

```text
E:\dev\SKN27-3rd-4TEAM\machine_learning
```

이전에 혼동을 만들던 아래 폴더는 제거했습니다.

```text
E:\dev\SKN27-3rd-4TEAM\frontend\machine_learning
```

해당 폴더에는 오래된 wrapper 파일인 `train_model.py`만 있었고, 현재 존재하지 않는 `machine_learning/train_models.py`를 찾고 있었기 때문에 제거했습니다.

## 2. 전체 파일 역할

| 경로 | 역할 | 유지 여부 |
|---|---|---|
| `can_jeonse_forecast.py` | 전체 horizon 모델 학습, 평가, 결과 저장 메인 코드 | 유지 |
| `can_jeonse_forecast_1m.py` | 1개월 horizon만 단독 학습/평가하는 실행 파일 | 유지 |
| `can_jeonse_forecast_3m.py` | 3개월 horizon만 단독 학습/평가하는 실행 파일 | 유지 |
| `can_jeonse_forecast_6m.py` | 6개월 horizon만 단독 학습/평가하는 실행 파일 | 유지 |
| `can_jeonse_forecast_12m.py` | 12개월 horizon만 단독 학습/평가하는 실행 파일 | 유지 |
| `can_jeonse_forecast_24m.py` | 24개월 horizon만 단독 학습/평가하는 실행 파일 | 유지 |
| `model_agent.py` | Supervisor가 호출할 모델 에이전트 인터페이스 | 유지 |
| `requirements.txt` | 머신러닝 실행 의존성 | 유지 |
| `README_modeling.md` | 모델 실행/산출물 설명 문서 | 유지 |
| `docs/` | 모델 설명, 에이전트 입출력, 최종 정리 문서 | 유지 |
| `artifacts/can_jeonse/` | 학습 결과, 모델 파일, 평가 지표 저장 | 유지 |

정리하면서 제거한 파일/폴더는 아래와 같습니다.

| 제거 대상 | 제거 이유 |
|---|---|
| `frontend/machine_learning/` | 현재 구조와 맞지 않는 오래된 wrapper 폴더 |
| `machine_learning/__pycache__/` | Python 실행 중 자동 생성되는 캐시 |
| `machine_learning/visualize_results.py` | 한글 인코딩이 깨져 있었고, 과거 `modeling` 경로를 참조하던 미사용 시각화 스크립트 |

## 3. 사용한 원천 데이터

원천 데이터 위치는 아래입니다.

```text
E:\dev\SKN27-3rd-4TEAM\data
```

사용 데이터는 서울 종로구의 연도별 매매/전세 CSV입니다.

```text
2016~2025년 매매 연립다세대
2016~2025년 매매 오피스텔
2016~2025년 전세 연립다세대
2016~2025년 전세 오피스텔
```

즉 현재 모델의 공간적 범위는 `서울특별시 종로구`이며, 주택유형은 `연립다세대(villa)`와 `오피스텔(officetel)`입니다.

## 4. 데이터 전처리 방식

전처리는 `can_jeonse_forecast.py`에서 수행합니다.

### 4.1 거래 유형과 주택유형 구분

파일명 기준으로 거래 유형과 주택유형을 구분합니다.

```text
파일명에 매매 포함 → trade_type = sale
파일명에 전세 포함 → trade_type = jeonse
파일명에 오피스텔 포함 → property_type = officetel
그 외 연립다세대 → property_type = villa
```

### 4.2 반전세 제외

전세 데이터 중 `monthly_rent > 0`인 경우는 순수 전세가 아니라 반전세/월세 성격이 있으므로 제외했습니다.

```text
monthly_rent == 0 인 전세만 사용
```

### 4.3 반지하/지하층 제외

모델은 지상층 기준 시장 가격을 학습하도록 설계했습니다. 따라서 `floor < 0`인 거래는 전처리 단계에서 제외했습니다.

```text
floor < 0  → 지하/반지하층으로 보고 제외
floor >= 0 → 학습 및 시세 산출에 사용
floor 결측 → 데이터 손실 방지를 위해 유지
```

최종 산출물 검토 결과:

```text
transactions_normalized.csv 행 수: 21,329건
floor < 0 거래 수: 0건
monthly_panel.csv 행 수: 4,604행
```

따라서 현재 학습 결과에는 반지하/지하층 거래가 포함되어 있지 않습니다.

### 4.4 면적 보정 방식

현재 모델은 총액을 그대로 학습하지 않고 평당가로 변환합니다.

```text
exclusive_area_pyeong = exclusive_area_m2 / 3.3058
price_per_pyeong = price_amount / exclusive_area_pyeong
```

따라서 면적 차이가 완전히 무시되는 것은 아닙니다. 다만 모델 학습 단위 자체는 `동 + 주택유형 + 월`이므로, 같은 동/주택유형 안에서 면적구간을 직접 feature로 학습하지는 않습니다.

이를 보완하기 위해 모델 에이전트 단계에서 `면적구간별 최근 12개월 시세 비교`를 추가했습니다.

### 4.5 월별 패널 데이터 생성

모델 학습 단위는 아래입니다.

```text
dong_name + property_type + month
```

예시는 아래와 같습니다.

```text
신영동 + villa + 2025-05
숭인동 + officetel + 2024-12
```

월별로 아래 값을 집계합니다.

```text
매매 평당가 평균
전세 평당가 평균
매매 거래 수
전세 거래 수
평균 층수
평균 건물연식
전세가율
```

## 5. Feature 구성

모델에 들어가는 주요 변수는 아래와 같습니다.

| 구분 | 변수 |
|---|---|
| 범주형 | `dong_name`, `property_type` |
| 시점 | `month_num`, `year` |
| 현재 시장값 | `sale_per_pyeong`, `jeonse_per_pyeong`, `jeonse_to_sale_ratio` |
| 거래량 | `sale_count`, `jeonse_count` |
| 과거 매매가 | `sale_lag_1`, `sale_lag_2`, `sale_lag_3`, `sale_lag_6`, `sale_lag_12` |
| 과거 매매 이동평균 | `sale_roll_mean_3`, `sale_roll_mean_6`, `sale_roll_mean_12` |
| 과거 전세 이동평균 | `jeonse_roll_mean_3`, `jeonse_roll_mean_6`, `jeonse_roll_mean_12` |
| 변화율 | `sale_mom_change` |
| 건물/층 정보 | `avg_building_age`, `avg_floor` |

주의할 점은 `avg_floor`는 개별 계약 매물의 층수가 아니라, 해당 월/동/주택유형 거래들의 평균 층수입니다. 그래서 개별 매물이 반지하인지, 1층인지, 고층인지까지는 모델이 직접 학습하지 못합니다. 이 한계 때문에 반지하/지하층은 아예 모델 적용 제외 케이스로 처리했습니다.

## 6. 예측 목표

모델은 현재 월 기준 미래 매매 평당가의 성장률을 예측합니다.

```text
target_growth_1m
 target_growth_3m
 target_growth_6m
 target_growth_12m
 target_growth_24m
```

각 horizon의 의미는 아래와 같습니다.

| Horizon | 의미 |
|---:|---|
| 1개월 | 현재 월 기준 1개월 뒤 매매가 흐름 예측 |
| 3개월 | 현재 월 기준 3개월 뒤 매매가 흐름 예측 |
| 6개월 | 현재 월 기준 6개월 뒤 매매가 흐름 예측 |
| 12개월 | 현재 월 기준 12개월 뒤 매매가 흐름 예측 |
| 24개월 | 현재 월 기준 24개월 뒤 매매가 흐름 예측 |

전세 위험도는 아래 방식으로 계산합니다.

```text
현재 위험비율 = 계약 전세 평당가 / 현재 시장 매매 평당가
예측 위험비율 = 계약 전세 평당가 / 예측 미래 매매 평당가
```

## 7. 데이터 누수 방지

이전 문제점은 시계열 검증에서 미래 정답 구간이 검증 구간과 겹칠 수 있다는 점이었습니다. 이를 보완하기 위해 horizon별 purge gap을 적용했습니다.

| Horizon | Purge gap | 검증 시작월 | 학습 종료월 | label overlap |
|---:|---:|---|---|---:|
| 1개월 | 2개월 | 2024-02 | 2023-12 | 0 |
| 3개월 | 4개월 | 2024-01 | 2023-09 | 0 |
| 6개월 | 7개월 | 2023-10 | 2023-03 | 0 |
| 12개월 | 13개월 | 2023-05 | 2022-04 | 0 |
| 24개월 | 25개월 | 2022-08 | 2020-07 | 0 |

검토 결과 모든 horizon에서 아래 값이 0입니다.

```text
train_label_overlap_into_valid_rows = 0
```

또한 target 컬럼은 feature에서 제외했습니다.

```text
target_growth_* 제외
actual_future_sale_per_pyeong_* 제외
actual_risk_ratio_* 제외
actual_risk_label_* 제외
```

결론적으로 현재 validation 기준에서는 데이터 누수 차단 처리가 되어 있습니다.

## 8. 학습한 모델 후보

각 horizon마다 아래 모델을 개별 학습하고 평가했습니다.

```text
LightGBM
XGBoost
CatBoost
HistGradientBoostingRegressor
RandomForestRegressor
ExtraTreesRegressor
Ensemble Mean
```

개별 모델 결과는 아래 폴더에 저장됩니다.

```text
machine_learning/artifacts/can_jeonse/models/{horizon}m/
machine_learning/artifacts/can_jeonse/horizon_metrics/{horizon}m/
```

예시:

```text
models/24m/lightgbm.joblib
models/24m/xgboost.joblib
models/24m/random_forest.joblib
horizon_metrics/24m/lightgbm_metrics.json
horizon_metrics/24m/all_model_metrics.json
```

즉 단순히 앙상블만 돌린 것이 아니라, 각 모델별 단독 성능과 앙상블 성능을 모두 저장하도록 구성되어 있습니다. 현재 `ensemble_mean`은 전체 후보 평균이 아니라 `LightGBM + CatBoost + XGBoost` 세 모델의 예측값만 평균내는 방식입니다.

## 9. 최종 best model 결과

최종 best model은 horizon별로 `best_models.csv`에 저장됩니다.

| Horizon | Best model | Valid MAPE | Baseline MAPE | Baseline보다 개선 | ROC-AUC | F1 |
|---:|---|---:|---:|---|---:|---:|
| 1개월 | ExtraTrees | 16.31% | 14.40% | 아니오 | 0.8938 | 0.8125 |
| 3개월 | ExtraTrees | 21.37% | 20.29% | 아니오 | 0.8460 | 0.7530 |
| 6개월 | RandomForest | 23.84% | 26.16% | 예 | 0.8175 | 0.7331 |
| 12개월 | ExtraTrees | 24.95% | 29.73% | 예 | 0.8155 | 0.6876 |
| 24개월 | LightGBM | 27.03% | 29.63% | 예 | 0.7946 | 0.6218 |

해석은 아래와 같습니다.

```text
1개월, 3개월 모델은 baseline보다 MAPE가 나쁘므로 가격 예측용 최종 모델로는 약합니다.
6개월, 12개월, 24개월 모델은 baseline보다 MAPE가 개선되었습니다.
전세계약 기간이 보통 24개월이라는 점을 고려하면, 서비스/에이전트에서는 24개월 모델을 primary로 쓰는 것이 가장 자연스럽습니다.
다만 24개월 모델은 overfit severe=True이므로 최종 가격 위험도는 24개월 LightGBM으로 산정하되, 현재 시세와 면적구간 시세를 함께 설명해야 합니다.
```


### 9.1 24개월 주요 모델 비교

CatBoost 설치 후 `ensemble_mean`은 아래 세 모델만 평균내도록 수정했습니다.

```text
LightGBM + CatBoost + XGBoost
```

24개월 기준 주요 결과는 아래와 같습니다.

| 모델 | Valid MAPE | Baseline MAPE | Baseline보다 개선 | ROC-AUC | F1 | 비고 |
|---|---:|---:|---|---:|---:|---|
| LightGBM | 27.03% | 29.63% | 예 | 0.7946 | 0.6218 | 24개월 best model |
| Ensemble Mean | 28.46% | 29.63% | 예 | 0.7894 | 0.5607 | LightGBM + CatBoost + XGBoost 평균 |
| CatBoost | 30.00% | 29.63% | 아니오 | 0.7779 | 0.5701 | 단독 기준 baseline보다 낮음 |
| XGBoost | 30.42% | 29.63% | 아니오 | 0.7763 | 0.5973 | 단독 기준 baseline보다 낮음 |

따라서 앙상블 구조는 요청한 방향대로 수정되었지만, 성능 기준 최종 24개월 best model은 여전히 LightGBM입니다.
## 10. 과적합 검토

과적합 검토 결과는 아래와 같습니다.

| Horizon | Overfit warning | Overfit severe | 해석 |
|---:|---|---|---|
| 1개월 | True | False | 경고는 있으나 severe 아님 |
| 3개월 | True | False | 경고는 있으나 severe 아님 |
| 6개월 | True | False | 경고는 있으나 severe 아님 |
| 12개월 | True | False | 경고는 있으나 severe 아님 |
| 24개월 | True | True | train/valid 성능 차이가 커서 과적합 가능성 있음 |

따라서 최종 답변에서는 24개월 모델 결과를 다음처럼 표현해야 합니다.

```text
24개월 모델은 전세계약 기간과 맞고 baseline보다 성능은 좋기 때문에 최종 가격 위험도 산정에 사용합니다. 다만 과적합 severe 경고가 있으므로 법률/특약/권리관계 검토와 현재 시세 설명을 함께 제시해야 합니다.
```

## 11. 최종 에이전트 연결 모델

Supervisor와 연결되는 실제 파일은 아래입니다.

```text
machine_learning/model_agent.py
```

Supervisor는 아래 함수만 호출하면 됩니다.

```python
from machine_learning.model_agent import analyze_contract

result = analyze_contract(contract_info)
```

현재 모델 에이전트는 아래 모델을 사용합니다.

| 역할 | 모델 |
|---|---|
| Primary forecast | 24개월 LightGBM |
| 현재 위험도 | 현재 계약 전세 평당가 / 현재 시장 매매 평당가 |
| 면적 참고 지표 | 동 + 주택유형 + 면적구간 기준 최근 12개월 시세 비교 |

## 12. 모델 에이전트 Input

Supervisor 또는 계약서 파싱 담당자는 아래 형태의 dict를 모델 에이전트에 전달하면 됩니다.

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

## 13. 모델 에이전트 Output

모델 에이전트는 세 가지 상태를 반환합니다.

### 13.1 성공

```json
{
  "status": "success",
  "current_market_check": {},
  "area_bucket_check": {},
  "forecast_check": {},
  "model_quality": {},
  "final_market_risk": "깡통 가능성 매우 높음"
}
```

### 13.2 정보 부족

```json
{
  "status": "need_more_info",
  "missing_fields": [
    "property_type",
    "deposit_amount_manwon"
  ]
}
```

### 13.3 반지하/지하층 제외

```json
{
  "status": "excluded_case",
  "reason": "basement_or_underground_unit"
}
```

반지하/지하층은 현재 지상층 기준 모델의 적용 대상이 아니므로 위험도 계산을 하지 않고 제외 케이스로 반환합니다.

## 14. 실제 실행 방법

전체 horizon 모델을 다시 학습/평가하려면 아래 명령을 사용합니다.

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

모델 에이전트를 테스트하려면 아래 명령을 사용합니다.

```powershell
python .\machine_learning\model_agent.py --demo
python .\machine_learning\model_agent.py --json .\machine_learning\docs\model_agent_sample_input.json
```

## 15. 주요 산출물

| 산출물 | 설명 |
|---|---|
| `transactions_normalized.csv` | 전처리 완료 거래 단위 데이터 |
| `monthly_panel.csv` | 동 + 주택유형 + 월 단위 학습 패널 데이터 |
| `metrics.csv` | 모든 horizon/모델 후보의 평가 결과 |
| `metrics.json` | 모든 평가 결과 JSON |
| `best_models.csv` | horizon별 최종 best model 요약 |
| `best_models.json` | horizon별 최종 best model JSON |
| `growth_24m_best_model.joblib` | 에이전트 primary forecast에 사용되는 24개월 LightGBM 모델 |
| `growth_12m_best_model.joblib` | 12개월 horizon 비교/평가용 best model 산출물 |
| `can_jeonse_risk_24m.csv` | 최신 월 기준 24개월 예측 위험도 결과 |

`growth_{horizon}m_model.joblib` 파일은 `growth_{horizon}m_best_model.joblib`와 같은 내용을 복사해 둔 호환용 파일입니다. 현재 모델 에이전트는 명시적으로 `growth_{horizon}m_best_model.joblib`를 사용합니다.

## 16. Supervisor 연결 시 권장 흐름

```text
1. 사용자가 계약서 docx 업로드 또는 텍스트 입력
2. 계약서 파싱/입력 정리 단계에서 구조화 데이터 생성
3. 모델 에이전트 analyze_contract(contract_info) 호출
4. status 확인
   - success → 법률/특약 에이전트 결과와 종합
   - need_more_info → 사용자에게 부족 정보 요청
   - excluded_case → 반지하/지하층 모델 제외 안내 및 법률/특약 검토 강화
5. Supervisor가 최종 답변 생성
```

## 17. 최종 결론

현재 머신러닝 파트는 아래 상태입니다.

```text
데이터 전처리 완료
반전세 제외 완료
반지하/지하층 거래 제외 완료
데이터 누수 방지 purge gap 적용 완료
모델별 개별 학습/평가 완료
앙상블 평가 완료
horizon별 best model 저장 완료
모델 에이전트 연결 파일 구현 완료
Supervisor 전달용 Input/Output 문서 작성 완료
불필요한 frontend 머신러닝 폴더 및 캐시 제거 완료
```


```text
본 모델은 서울 종로구의 연립다세대/오피스텔 매매 및 전세 실거래 데이터를 바탕으로 동·주택유형·월 단위의 매매 평당가 흐름을 학습했다. 1/3/6/12/24개월 horizon별로 LightGBM, XGBoost, CatBoost, HistGradientBoosting, RandomForest, ExtraTrees, LightGBM+CatBoost+XGBoost 앙상블을 비교했고, 전세계약 기간과 가장 잘 맞는 24개월 LightGBM 모델을 모델 에이전트의 primary forecast로 사용한다. 다만 24개월 모델은 과적합 경고가 있으므로, 최종 가격 위험도는 24개월 LightGBM으로 산정하되 현재 전세가율, 면적구간, 법률/특약 에이전트 결과를 함께 설명하도록 설계했다.
```

## 최종 가격 위험도 산정 기준

현재 서비스 연결 기준은 아래처럼 고정합니다.

```text
최종 가격 예측: 24개월 LightGBM
최종 가격 위험도: 계약 전세 평당가 / 24개월 LightGBM 예측 매매 평당가
보조 설명: 현재 시세 위험도, 면적구간 최근 12개월 시세 위험도
챗봇 전달: price_evidence에 계산 근거를 정리해서 Supervisor에게 반환
```

따라서 `final_market_risk`와 `price_evidence.risk`는 24개월 LightGBM 예측 위험도와 동일합니다. 현재 시세 위험도와 면적구간 최근 12개월 시세 위험도는 사용자가 결과를 이해하도록 돕는 설명 근거이며 최종 등급을 직접 바꾸지 않습니다.

이렇게 정한 이유는 전세계약의 일반적인 만기 시점이 24개월이므로, 사용자가 실제로 알고 싶은 “계약 만기 시점의 보증금 회수 위험”과 가장 직접적으로 연결되는 모델이 24개월 예측 모델이기 때문입니다. 다만 24개월 LightGBM은 baseline보다 성능이 좋지만 overfit severe 경고가 있으므로, 챗봇 답변에서는 현재 시세와 면적구간 시세를 함께 보여주고 법률/특약 에이전트 결과와 종합해야 합니다.
