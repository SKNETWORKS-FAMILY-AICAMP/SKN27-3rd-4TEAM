# Supervisor 연동용 모델 에이전트 Input/Output 명세


## 1. 모델 에이전트 역할

모델 에이전트는 계약서 또는 텍스트에서 추출된 계약 정보를 받아 아래 내용을 계산합니다.

```text
1. 현재 계약 전세가율 (고전세가율 및 30% 미만 저전세가율 리스크 판별)
2. 면적구간별 최근 12개월 시세 대비 위험도
3. 24개월 LightGBM 예측 매매가 기반 최종 위험도
4. 저전세가율(30% 미만) 발생 시 선순위 채권 및 우선변제권 확인 가이드 제공
5. 모델 신뢰도 및 한계
```

단, 반지하/지하층 계약은 현재 지상층 기준 모델의 적용 대상에서 제외합니다.

## 2. Supervisor가 전달해야 하는 Input

```json
{
  "source_type": "docx 또는 text",
  "contract_id": "contract_001",
  "address": "서울특별시 종로구 신영동 179-21",
  "dong_name": "신영동",
  "property_type": "villa",
  "contract_date": "2025-05-12",
  "deposit_amount_manwon": 28600,
  "exclusive_area_m2": 42.39,
  "exclusive_area_pyeong": 12.82,
  "floor": 3,
  "is_basement": false,
  "raw_text": "계약서에서 추출한 원문 일부"
}
```

## 3. 필수값

| 필드 | 설명 |
|---|---|
| `dong_name` | 동 이름 |
| `property_type` | `villa` 또는 `officetel` |
| `contract_date` 또는 `base_month` | 계약일 또는 계약월 |
| `deposit_amount_manwon` | 보증금, 만원 단위 |
| `exclusive_area_m2` 또는 `exclusive_area_pyeong` | 전용면적 |


## 4. 저전세가율 기준 및 추가 확인 항목

모델 에이전트는 현재 계약 전세가율 또는 면적구간 기준 전세가율이 30% 이하이면 `low_jeonse_ratio_check.is_low_jeonse_ratio`를 `true`로 반환합니다.

저전세가율 계약은 가격 기반 깡통전세 위험도가 낮게 나올 수 있지만, 아래 항목은 별도로 확인해야 합니다.

```text
1. 보증금이 낮은 대신 월세, 관리비, 옵션비, 별도 사용료가 과도하게 책정되었는지
2. 등기부등본상 선순위 근저당, 압류, 가압류, 신탁등기, 임차권등기명령이 있는지
3. 건축물대장상 위반건축물, 불법 쪼개기, 용도 불일치, 무허가 증축 여부가 있는지
4. 실제 거래 시세보다 과도하게 낮은 금액인 경우 권리상 하자, 시설 하자, 침수·누수·채광·환기 문제 등이 있는지
5. 특약에서 수리 책임, 원상복구, 관리비, 중도해지, 보증보험 가입 제한 등 임차인에게 불리한 조건이 있는지
6. 전세보증금 반환보증 가입 가능 여부와 보증 한도, 임대인 체납 여부를 확인했는지
```

저전세가율이 감지되면 `recommended_next_agents`에는 `legal_agent`, `special_terms_agent`를 포함하고, 필요 시 `registry_agent`, `building_agent`, `insurance_agent`를 함께 추천할 수 있습니다.


## 5. 반지하/지하층 제외 Output

계약서 또는 사용자 입력에서 `floor < 0`, `is_basement = true`, 반지하/지하/B1 표현이 확인되면 아래처럼 반환합니다.

```json
{
  "status": "excluded_case",
  "agent_name": "model_agent",
  "contract_id": "contract_001",
  "reason": "basement_or_underground_unit",
  "message": "반지하 또는 지하층 매물은 현재 모델의 지상층 기준 시세 산출 대상에서 제외됩니다. 반지하 매물은 가격 구조와 침수·채광·환기 리스크가 달라 모델 결과를 그대로 적용하기 어렵습니다.",
  "recommended_next_agents": [
    "legal_agent",
    "special_terms_agent"
  ]
}
```

## 6. 정보 부족 시 Output

```json
{
  "status": "need_more_info",
  "agent_name": "model_agent",
  "contract_id": "contract_001",
  "missing_fields": [
    "property_type",
    "deposit_amount_manwon",
    "exclusive_area_m2"
  ],
  "message": "가격 기반 위험도 분석을 위해 주택유형, 보증금, 전용면적 정보가 필요합니다."
}
```


## 7. 분석 성공 시 Output

```json
{
  "status": "success",
  "agent_name": "model_agent",
  "risk_type": "market_price_risk",
  "contract_id": "contract_001",
  "input_summary": {
    "dong_name": "신영동",
    "property_type": "villa",
    "base_month": "2025-05",
    "deposit_amount_manwon": 28600,
    "exclusive_area_m2": 42.39,
    "exclusive_area_pyeong": 12.82,
    "area_bucket": "10~20평",
    "floor": 3,
    "is_basement": false
  },
  "current_market_check": {
    "contract_jeonse_per_pyeong": 2230.0,
    "market_sale_per_pyeong": 2104.95,
    "market_jeonse_per_pyeong": 1822.82,
    "current_risk_ratio": 1.06,
    "current_risk_level": "깡통 가능성 매우 높음"
  },
  "area_bucket_check": {
    "area_bucket_sale_per_pyeong": 2150.0,
    "area_bucket_jeonse_per_pyeong": 1850.0,
    "area_bucket_risk_ratio": 1.04,
    "area_bucket_sample_count": 12,
    "low_price_anomaly": false
  },
  "low_jeonse_ratio_check": {
    "threshold_ratio": 0.3,
    "is_low_jeonse_ratio": false,
    "basis": "current_risk_ratio",
    "message": "현재 계약 전세가율이 30%를 초과하여 저전세가율 특이 케이스로 분류하지 않습니다.",
    "additional_checks": []
  },
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
      "current_market": "현재 시세 위험도는 설명용 근거로만 사용",
      "area_bucket_recent_12m": "면적구간 최근 12개월 시세 위험도는 설명용 근거로만 사용"
    }
  },
  "model_quality": {
    "primary_valid_mape": 0.2703,
    "primary_baseline_mape": 0.2963,
    "model_beats_baseline": true,
    "leakage_safe": true,
    "overfit_warning": true,
    "overfit_severe": true
  },
  "final_market_risk": "고위험",
  "limitations": [
    "동일 매물의 실제 매매가가 아니라 동/주택유형/월 및 면적구간 시장 데이터 기준입니다.",
    "반지하·지하층 매물은 모델 적용 대상에서 제외됩니다.",
    "최종 가격 위험도는 24개월 LightGBM 예측값만 기준으로 산정합니다.",
    "24개월 LightGBM은 baseline보다 낫지만 과적합 severe 경고가 있어 현재 시세와 면적구간 시세를 함께 설명해야 합니다.",
    "전세가율이 30% 이하인 저전세가율 계약은 가격 기반 깡통전세 위험도와 별개로 권리관계, 관리비·월세 구조, 건축물 하자, 보증보험 가입 가능 여부를 추가 확인해야 합니다.",
    "법률, 권리관계, 특약 위험은 별도 에이전트 확인이 필요합니다."
  ],
  "recommended_next_agents": [
    "legal_agent",
    "special_terms_agent"
  ]
}
```

## 8. 저전세가율 감지 시 성공 Output 예시

```json
{
  "status": "success",
  "agent_name": "model_agent",
  "risk_type": "market_price_risk",
  "contract_id": "contract_002",
  "current_market_check": {
    "contract_jeonse_per_pyeong": 620.0,
    "market_sale_per_pyeong": 2104.95,
    "market_jeonse_per_pyeong": 1822.82,
    "current_risk_ratio": 0.29,
    "current_risk_level": "가격 기준 깡통전세 위험 낮음"
  },
  "low_jeonse_ratio_check": {
    "threshold_ratio": 0.3,
    "is_low_jeonse_ratio": true,
    "basis": "current_risk_ratio",
    "message": "현재 계약 전세가율이 30% 이하인 저전세가율 계약입니다. 가격 기준 깡통전세 위험은 낮게 보일 수 있으나, 보증금이 낮은 사유와 별도 비용·권리관계·건축물 상태를 반드시 확인해야 합니다.",
    "additional_checks": [
      "월세, 관리비, 옵션비, 별도 사용료가 과도하게 책정되었는지 확인",
      "등기부등본상 선순위 근저당, 압류, 가압류, 신탁등기, 임차권등기명령 확인",
      "건축물대장상 위반건축물, 용도 불일치, 불법 증축, 불법 쪼개기 여부 확인",
      "실거래 시세 대비 과도하게 낮은 금액인 경우 시설 하자, 침수·누수, 채광·환기 문제 확인",
      "특약상 수리 책임, 원상복구, 관리비, 중도해지, 보증보험 제한 조항 확인",
      "전세보증금 반환보증 가입 가능 여부, 보증 한도, 임대인 체납 여부 확인"
    ]
  },
  "final_market_risk": "저전세가율 특이 케이스",
  "recommended_next_agents": [
    "legal_agent",
    "special_terms_agent",
    "registry_agent",
    "building_agent",
    "insurance_agent"
  ]
}
```

## 9. Supervisor에서 사용할 최종 요약 문장

```text
모델 에이전트는 계약서 또는 텍스트에서 추출한 동, 주택유형, 계약일, 보증금, 면적, 층수 정보를 받아 가격 기반 전세 위험도를 계산합니다. 반지하/지하층은 지상층 기준 모델 적용 대상에서 제외하고 excluded_case를 반환합니다. 필수값이 부족하면 need_more_info를 반환하고, 충분하면 24개월 LightGBM 최종 예측 위험도, 현재 시장 전세가율, 면적구간 시세 비교, 모델 신뢰도 지표와 price_evidence를 JSON으로 반환합니다. 현재 계약 전세가율 또는 면적구간 기준 전세가율이 30% 이하이면 저전세가율 특이 케이스로 표시하고, 가격 기반 위험도 분석과 함께 월세·관리비 구조, 선순위 권리, 건축물대장 위반 여부, 시설 하자, 특약상 불리한 조건, 전세보증금 반환보증 가입 가능 여부를 추가 확인하도록 안내합니다.
```
## 10. 모델 에이전트 내부에 구현된 책임 범위

아래 기능은 모델 에이전트 내부에 구현되어 있습니다.

| 기능 | 구현 여부 | 설명 |
|---|---|---|
| 구조화 계약 정보 입력 | 구현됨 | Supervisor 또는 파싱 단계가 추출한 `contract_info`를 입력으로 받음 |
| 필수값 검증 | 구현됨 | 동, 주택유형, 계약일/계약월, 보증금, 면적이 없으면 `need_more_info` 반환 |
| 추가 정보 요청 가이드 | 구현됨 | `required_input_request`에 사용자에게 물어볼 항목과 예시 문장 반환 |
| 반지하/지하층 제외 | 구현됨 | `floor < 0`, `is_basement=true`, 원문 키워드 감지 시 `excluded_case` 반환 |
| 현재 시세 위험도 | 구현됨 | 계약 전세 평당가 / 현재 시장 매매 평당가 |
| 면적구간 최근 12개월 시세 비교 | 구현됨 | 동 + 주택유형 + 면적구간 기준 최근 12개월 매매/전세 평당가 비교 |
| 시세보다 높은 전세가 처리 | 구현됨 | 전세가율 80% 이상 또는 100% 이상 여부를 `price_position_check`에 표시 |
| 시세보다 낮은 전세가 처리 | 구현됨 | 면적구간 전세 시세보다 15% 이상 낮으면 `low_price_anomaly=true` 표시 |
| 저전세가율 특이 케이스 | 구현됨 | 현재/면적구간 전세가율 30% 이하이면 `low_jeonse_ratio_check.is_low_jeonse_ratio=true` 반환 |
| ML 예측 위험도 | 구현됨 | 24개월 LightGBM 최종 예측 반환 |

아래 기능은 모델 에이전트 내부 책임이 아닙니다.

| 기능 | 담당 권장 위치 |
|---|---|
| docx 파일 업로드 UI | Frontend 또는 Supervisor |
| docx 파일 원본 저장 | Backend/DB 또는 파일 저장 계층 |
| docx 본문 파싱 | 계약서 파싱 모듈 또는 Supervisor 전처리 단계 |
| 파싱 결과를 별도 테이블에 저장 | Backend/DB 계층 |
| 사용자에게 파일 업로드/추가 입력 요청 | Supervisor 또는 Frontend |
| 법률/권리관계 판단 | 법률 에이전트 |
| 특약 조항 판단 | 특약 에이전트 |

즉 모델 에이전트는 `docx 파일 자체`가 아니라, docx 또는 텍스트에서 추출된 구조화 정보인 `contract_info`를 받아 가격 기반 위험도를 계산합니다.

## 11. 최종적으로 모델 에이전트가 사용하는 모델

현재 모델 관련 파일이 많기 때문에, 실제 서비스 연결 기준을 아래처럼 구분합니다.

### 11.1 실제 모델 에이전트가 사용하는 모델

| 용도 | 실제 사용 모델 | 파일 | 사용 이유 |
|---|---|---|---|
| Primary forecast | 24개월 LightGBM | `growth_24m_best_model.joblib` | 전세계약 2년 만기 시점과 가장 직접적으로 연결되고, 24개월 horizon에서 MAPE가 가장 낮음 |

따라서 현재 모델 에이전트의 핵심 예측 구조는 아래입니다.

```text
현재 시세 위험도
+ 면적구간 최근 12개월 시세 위험도
+ 24개월 LightGBM primary 예측 위험도
→ final_market_risk는 24개월 LightGBM 예측 위험도만 기준으로 반환
```

### 11.2 학습과 비교는 했지만 모델 에이전트 primary로 쓰지 않는 모델

아래 모델들은 horizon별 성능 비교와 앙상블 평가를 위해 학습/저장되어 있습니다.

```text
LightGBM
XGBoost
CatBoost
HistGradientBoosting
RandomForest
ExtraTrees
Ensemble Mean
```

이 중 `Ensemble Mean`은 현재 아래 세 모델의 평균입니다.

```text
LightGBM + CatBoost + XGBoost
```

하지만 24개월 기준 최종 best model은 `Ensemble Mean`이 아니라 `LightGBM`입니다. 따라서 모델 에이전트의 24개월 primary 예측은 앙상블이 아니라 LightGBM을 사용합니다.

### 11.3 24개월 주요 모델 비교 결과

| 모델 | Valid MAPE | Baseline MAPE | Baseline보다 개선 | ROC-AUC | F1 | 에이전트 사용 여부 |
|---|---:|---:|---|---:|---:|---|
| LightGBM | 27.03% | 29.63% | 예 | 0.7946 | 0.6218 | 24개월 primary로 사용 |
| Ensemble Mean | 28.46% | 29.63% | 예 | 0.7894 | 0.5607 | 비교/평가용 |
| CatBoost | 30.00% | 29.63% | 아니오 | 0.7779 | 0.5701 | 비교/평가용 |
| XGBoost | 30.42% | 29.63% | 아니오 | 0.7763 | 0.5973 | 비교/평가용 |

결론적으로 현재 서비스 연결 모델은 아래처럼 말하면 됩니다.

```text
모델 에이전트는 24개월 LightGBM을 최종 가격 예측 모델로 사용합니다. LightGBM+CatBoost+XGBoost 앙상블과 다른 horizon 모델은 학습 및 비교 결과로 저장되어 있지만, 24개월 best model이 아니므로 현재 에이전트의 primary 모델로는 사용하지 않습니다.
```

## 12. 추가된 Output 필드

이번 보강으로 모델 에이전트는 아래 필드를 추가로 반환합니다.

### 12.1 `required_input_request`

`need_more_info`일 때 Supervisor가 사용자에게 어떤 정보를 요청해야 하는지 알려줍니다.

```json
{
  "requested_fields": [
    "주택유형(villa/연립다세대/빌라 또는 officetel/오피스텔)",
    "계약일 또는 계약월(예: 2025-05-12)",
    "보증금(만원 단위 또는 2억 8,600만 원 형식)",
    "전용면적(㎡ 또는 평)"
  ],
  "minimum_text_input_example": "예: 서울특별시 종로구 신영동, 연립다세대, 계약일 2025-05-12, 보증금 2억 8,600만 원, 전용면적 42.39㎡, 3층",
  "ask_user_message": "계약서 파일이 없으면 주소, 주택유형, 계약일, 보증금, 전용면적, 층수를 알려주세요."
}
```

### 12.2 `price_position_check`

계약 전세가가 시세보다 높은지, 지나치게 낮은지 해석합니다.

```json
{
  "is_above_current_sale_price": false,
  "is_high_jeonse_ratio": true,
  "low_price_anomaly": false,
  "messages": [
    "계약 전세 평당가가 현재 시장 매매 평당가의 80% 이상으로 높은 편입니다."
  ]
}
```

### 12.3 `low_jeonse_ratio_check`

현재 또는 면적구간 기준 전세가율이 30% 이하이면 저전세가율 특이 케이스로 표시합니다.

```json
{
  "threshold_ratio": 0.3,
  "is_low_jeonse_ratio": true,
  "basis": [
    "current_risk_ratio",
    "area_bucket_risk_ratio"
  ],
  "message": "현재 계약 전세가율 또는 면적구간 기준 전세가율이 30% 이하인 저전세가율 계약입니다. 가격 기준 깡통전세 위험은 낮게 보일 수 있으나, 보증금이 낮은 사유와 별도 비용·권리관계·건축물 상태를 반드시 확인해야 합니다."
}
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
