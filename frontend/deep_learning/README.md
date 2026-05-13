# 전세 위험 딥러닝 분석 결과 해석 가이드

이 문서는 `frontend/chatbot/deep_learning` 모듈에서 생성되는 전처리/딥러닝 분석 결과를 어떻게 읽어야 하는지 정리한 README입니다.

## 1. 분석 흐름

```text
PostgreSQL 또는 CSV
→ preprocess.py
→ artifacts/processed/*.csv
→ TabNet 이상거래 탐지
→ LSTM 평당가 흐름 예측
→ risk_inference.py 개별 매물 위험 해석
```

현재 DB 기준 전처리 확인 결과는 다음과 같습니다.

```text
jeonse_transactions: 11,333건
sale_transactions: 20,833건
jeonse_labeled.csv: 11,333건
jeonse_monthly.csv: 5,492건
sale_monthly.csv: 531건
jeonse_building_monthly.csv: 9,850건
```

## 2. 실행 방법

프로젝트 루트에서 실행합니다.

```powershell
cd E:\dev\SKN27-3rd-4TEAM
.\.venv\Scripts\activate
docker compose up -d db
```

전처리만 실행:

```powershell
python .\frontend\chatbot\deep_learning\preprocess.py --source db
```

전체 분석 실행:

```powershell
python .\frontend\chatbot\deep_learning\run_analysis.py --source db
```

시간이 오래 걸리면 단계별로 실행합니다.

```powershell
python .\frontend\chatbot\deep_learning\run_analysis.py --source db --skip-lstm
python .\frontend\chatbot\deep_learning\run_analysis.py --source db --skip-tabnet --skip-lstm
```

## 3. 주요 산출물

산출물은 아래 폴더에 생성됩니다.

```text
frontend/chatbot/deep_learning/artifacts/
```

| 파일 | 의미 |
|---|---|
| `processed/load_summary.json` | 원천 데이터와 전처리 결과 건수 요약 |
| `processed/jeonse_monthly.csv` | 동/주택유형/면적구간/월별 전세 평당가 통계 |
| `processed/sale_monthly.csv` | 주택유형/면적구간/월별 매매 평당가 통계 |
| `processed/jeonse_building_monthly.csv` | 건물명/면적구간/층구간 기준 월별 전세 통계 |
| `processed/jeonse_labeled.csv` | TabNet 학습용 이상거래 라벨 데이터 |
| `models/tabnet_metadata.json` | TabNet 학습 결과와 성능 지표 |
| `models/lstm_metadata.json` | LSTM 학습 결과와 예측 가능 그룹 요약 |
| `analysis_summary.json` | 전체 분석 실행 결과 요약 |

## 4. 컬럼 해석

### `jeonse_monthly.csv`

지역과 조건별 전세 평당가의 월별 기준선입니다.

| 컬럼 | 해석 |
|---|---|
| `sido`, `sigungu`, `dong_name` | 지역 |
| `housing_type` | 주택유형, 예: 연립다세대, 오피스텔 |
| `area_bucket` | 면적 구간 |
| `contract_month` | 계약 월 |
| `median_deposit_per_pyeong` | 해당 조건의 월별 대표 전세 평당가 |
| `count` | 해당 월 거래 건수 |
| `std` | 평당가 표준편차 |
| `q25`, `q75` | 평당가 25%, 75% 분위값 |
| `agg_method` | 평균 또는 중앙값 중 사용한 집계 방식 |

`median_deposit_per_pyeong`이 사용자의 입력 보증금 평당가와 비교되는 핵심 기준입니다.

### `sale_monthly.csv`

매매 평당가 기준선입니다. 전세가율 계산에 사용됩니다.

| 컬럼 | 해석 |
|---|---|
| `median_sale_per_pyeong` | 해당 조건의 월별 대표 매매 평당가 |
| `count` | 매매 거래 건수 |
| `std`, `q25`, `q75` | 매매 평당가 분포 |

전세가율은 대략 다음 방식으로 해석합니다.

```text
전세가율 = 전세 평당가 / 매매 평당가 * 100
```

값이 높을수록 매매가 대비 보증금 비중이 큰 상태입니다.

### `jeonse_building_monthly.csv`

동일 건물 또는 유사 조건의 최근 전세가를 비교하기 위한 데이터입니다.

| 컬럼 | 해석 |
|---|---|
| `property_name` | 건물명 |
| `floor_bucket` | 저층, 중층, 고층, 지하/반지하 등 |
| `building_median_deposit` | 해당 건물의 월별 대표 보증금 |
| `building_median_deposit_per_pyeong` | 해당 건물의 대표 평당 전세가 |
| `building_count` | 해당 조건의 거래 건수 |

건물명이 입력된 경우, 같은 건물의 최근 평균보다 입력 보증금이 과하게 높은지 판단하는 데 사용합니다.

### `jeonse_labeled.csv`

TabNet 이상거래 탐지 모델의 학습 데이터입니다.

| 컬럼 | 해석 |
|---|---|
| `deposit_per_pyeong` | 해당 거래의 전세 평당가 |
| `region_price` | 같은 지역/유형/면적대의 기준 평당가 |
| `z_score` | 기준 평당가 대비 얼마나 벗어났는지 나타내는 값 |
| `sale_price` | 매매 평당가 기준선 |
| `jeonse_ratio` | 매매 평당가 대비 전세 평당가 비율 |
| `is_price_anomaly` | 지역 기준보다 비정상적으로 높거나 낮은 가격 여부 |
| `is_ratio_anomaly` | 전세가율 기준 이상 여부 |
| `is_anomaly` | 최종 이상거래 라벨 |

`is_anomaly = 1`은 모델 학습상 이상 신호가 있는 거래라는 뜻입니다. 무조건 사기라는 의미는 아니며, 추가 확인이 필요한 신호로 해석합니다.

## 5. 모델 결과 해석

### TabNet

TabNet은 개별 거래가 이상가격 패턴에 가까운지 분류합니다.

주요 입력 변수:

```text
housing_type_enc
동 이름 인코딩
area_pyeong
floor
building_age
deposit_per_pyeong
z_score
jeonse_ratio
q25
q75
```

`tabnet_metadata.json`에서 확인할 값:

| 항목 | 해석 |
|---|---|
| `rows` | 학습에 사용된 라벨 데이터 수 |
| `anomaly_rate` | 이상 라벨 비율 |
| `auc` | 분류 성능. 1에 가까울수록 좋음 |
| `classification_report` | precision, recall, f1-score 등 |
| `feature_importances` | 어떤 변수가 판단에 크게 작용했는지 |

AUC는 대략 이렇게 봅니다.

```text
0.5 근처: 구분력이 낮음
0.7 이상: 어느 정도 구분 가능
0.8 이상: 비교적 양호
```

### LSTM

LSTM은 지역/주택유형/면적구간별 전세 평당가 흐름을 학습해 향후 24개월 변화를 예측합니다.

`lstm_metadata.json`에서 확인할 값:

| 항목 | 해석 |
|---|---|
| `trained_models` | 실제 학습된 지역/조건 그룹 |
| `mae` | 평균 절대 오차. 낮을수록 좋음 |
| `rmse` | 큰 오차에 더 민감한 지표. 낮을수록 좋음 |
| `months` | 학습에 사용된 월 수 |
| `skipped` | 데이터 월수가 부족해서 학습하지 못한 그룹 |

LSTM은 최소 월별 데이터가 부족하면 해당 조건을 건너뜁니다. `skipped`가 많다면 데이터 기간이나 거래 건수가 부족하다는 뜻입니다.

## 6. 개별 매물 위험 분석

학습/전처리 후 아래처럼 실행합니다.

```powershell
python .\frontend\chatbot\deep_learning\risk_inference.py --dong 혜화동 --housing-type 연립다세대 --area-m2 66 --floor 3 --deposit 22000
```

건물명까지 비교하려면:

```powershell
python .\frontend\chatbot\deep_learning\risk_inference.py --dong 가회동 --property-name 북촌힐스 --housing-type 연립다세대 --area-m2 88 --floor 3 --deposit 33000
```

출력 결과의 핵심은 다음입니다.

| 위치 | 해석 |
|---|---|
| `input.input_deposit_per_pyeong` | 입력 매물의 평당 보증금 |
| `market_analysis.recent_region_median_deposit_per_pyeong` | 최근 지역 기준 평당 전세가 |
| `market_analysis.region_deposit_gap_pct` | 입력 매물이 지역 기준보다 몇 % 높거나 낮은지 |
| `market_analysis.sale_per_pyeong` | 매매 평당가 기준 |
| `market_analysis.jeonse_ratio` | 입력 매물의 전세가율 |
| `market_analysis.forecast_24m` | LSTM 기반 24개월 전망 |
| `building_analysis.building_gap_pct` | 같은 건물 기준 대비 차이 |
| `risk.risk_score` | 최종 위험 점수 |
| `risk.risk_level` | 보통/주의/위험 |
| `risk.reasons` | 위험 판단 이유 |
| `risk.advice` | 확인해야 할 조치 |

## 7. 해석 시 주의사항

- 이 분석은 계약 가능 여부를 확정하는 도구가 아니라 위험 신호를 정리하는 보조 도구입니다.
- `위험`은 사기 확정이 아니라 보증금 회수 가능성, 가격 괴리, 시장 하락 가능성을 더 확인해야 한다는 뜻입니다.
- 거래 건수가 적은 동/면적구간은 `count`, `std`, `q25`, `q75`를 함께 봐야 합니다.
- 건물명이 없는 경우 건물 단위 비교는 제한됩니다.
- 전세가율이 높고 LSTM 전망이 하락이면 보수적으로 판단하는 것이 좋습니다.
- 최종 계약 전에는 등기부등본, 선순위 권리, 임대인 체납 여부, 반환보증 가입 가능성을 반드시 확인해야 합니다.