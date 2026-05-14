# Supervisor 연동용 모델 에이전트 Input/Output 명세

## 1. 모델 에이전트 역할

모델 에이전트는 계약서 또는 텍스트에서 추출된 계약 정보를 받아 아래 내용을 계산합니다.

```text
1. 현재 계약 전세가율
2. 면적구간별 최근 12개월 시세 대비 위험도
3. 12개월/24개월 예측 매매가 기반 위험도
4. 모델 신뢰도 및 한계
5. 저전세가율 여부 및 추가 확인 필요 항목
```

단, 반지하/지하층 계약은 현재 지상층 기준 모델의 적용 대상에서 제외합니다.

저전세가율은 계약 보증금이 기준 매매가의 30% 이하인 경우로 정의합니다. 저전세가율은 깡통전세 가능성은 상대적으로 낮을 수 있으나, 비정상적으로 낮은 보증금 구조, 월세/관리비 전가, 선순위 권리, 불법건축물, 실제 시세 왜곡 가능성을 함께 확인해야 합니다.

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
    "primary_horizon_months": 24,
    "primary_model": "lightgbm",
    "forecast_risk_ratio_24m": 0.95,
    "forecast_risk_level_24m": "고위험",
    "supporting_horizon_months": 12,
    "supporting_model": "extra_trees"
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
모델 에이전트는 계약서 또는 텍스트에서 추출한 동, 주택유형, 계약일, 보증금, 면적, 층수 정보를 받아 가격 기반 전세 위험도를 계산합니다. 반지하/지하층은 지상층 기준 모델 적용 대상에서 제외하고 excluded_case를 반환합니다. 필수값이 부족하면 need_more_info를 반환하고, 충분하면 현재 시장 전세가율, 면적구간 시세 비교, 12/24개월 예측 위험도, 모델 신뢰도 지표를 JSON으로 반환합니다. 현재 계약 전세가율 또는 면적구간 기준 전세가율이 30% 이하이면 저전세가율 특이 케이스로 표시하고, 가격 기반 위험도 분석과 함께 월세·관리비 구조, 선순위 권리, 건축물대장 위반 여부, 시설 하자, 특약상 불리한 조건, 전세보증금 반환보증 가입 가능 여부를 추가 확인하도록 안내합니다.
```
