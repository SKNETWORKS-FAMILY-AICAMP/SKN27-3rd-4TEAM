# 24개월 예측 모델 결과

## 전처리 기준

이 결과는 `floor < 0`인 지하/반지하층 거래를 제외하고 다시 학습한 결과입니다. 따라서 지상층 기준의 동별·주택유형별 시장 흐름에 더 가깝습니다.

## 에이전트 활용 위치

- 권장 활용: 핵심 장기 판단용
- 모델 에이전트는 이 결과를 법률/특약 판단이 아니라 시장 가격 위험 판단에만 사용합니다.

## Best Model

- Best model: `lightgbm`
- Valid MAPE: 27.03%
- Baseline MAPE: 29.63%
- Baseline 대비 MAPE 개선: 예
- ROC-AUC: 0.7946
- F1: 0.6218
- 과적합 경고: 예
- Severe: 예

## 판단 메모

- 데이터 누수 검사 결과 `train_label_overlap_into_valid_rows = 0`이 되도록 purged time split을 적용했습니다.
- feature는 현재 월 집계값, 과거 lag, `shift(1)` rolling 값만 사용합니다.
- 지하/반지하층 계약은 이 모델의 일반 위험도 산출 대상에서 제외하고, 별도 주의 문구와 법률/특약 검토로 넘기는 것이 좋습니다.
