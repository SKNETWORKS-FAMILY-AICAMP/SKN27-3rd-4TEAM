from __future__ import annotations

import argparse
import json

import pandas as pd

from lstm_model import LOOKBACK, MODEL_DIR, forecast, train as train_lstm
from preprocess import (
    PROCESSED_DIR,
    area_bucket,
    building_monthly_stats,
    floor_bucket,
    monthly_stats,
    normalize_jeonse,
    normalize_sale,
    read_db,
)


def _safe_float(value):
    if value is None or pd.isna(value):
        return None
    return round(float(value), 2)


def _market_phase(change_pct):
    if change_pct is None:
        return "예측 부족"
    if change_pct > 5:
        return "상승장"
    if change_pct < -5:
        return "하락장"
    return "보합장"


def _score_risk(gap_pct, jeonse_ratio, forecast_change_pct, building_gap_pct):
    score = 30
    reasons = []
    advice = []

    if building_gap_pct is not None:
        if building_gap_pct >= 20:
            score += 18
            reasons.append("입력 보증금이 같은 건물·면적대·층구간의 최근 평균보다 20% 이상 높습니다.")
            advice.append("같은 건물의 최근 거래와 층수·면적 차이를 확인하고, 특이하게 높은 보증금이면 추가 확인이 필요합니다.")
        elif building_gap_pct <= -30:
            score += 8
            reasons.append("입력 보증금이 같은 건물 평균보다 과도하게 낮아 허위매물 또는 특수 조건 여부를 확인해야 합니다.")

    if gap_pct is not None:
        if gap_pct >= 25:
            score += 25
            reasons.append("입력 보증금이 같은 지역·유형·면적대 최근 평당가보다 25% 이상 높습니다.")
            advice.append("등기부 권리관계, 반환보증 가입 가능 여부, 선순위 채권 금액을 계약 전에 확인하세요.")
        elif gap_pct >= 10:
            score += 12
            reasons.append("입력 보증금이 최근 지역 평당가보다 높은 편입니다.")
        elif gap_pct <= -35:
            score += 10
            reasons.append("입력 보증금이 지역 시세보다 과도하게 낮아 허위매물 또는 특이 조건 여부 확인이 필요합니다.")

    if jeonse_ratio is not None:
        if jeonse_ratio >= 90:
            score += 25
            reasons.append("매매 평당가 대비 전세 평당가 비율이 90% 이상으로 깡통전세 위험 구간입니다.")
            advice.append("반환보증 가입 가능성과 특약 문구를 계약 전에 확인하세요.")
        elif jeonse_ratio >= 80:
            score += 15
            reasons.append("전세가율이 80% 이상으로 보증금 회수 여력이 낮아질 수 있습니다.")

    if forecast_change_pct is not None:
        if forecast_change_pct <= -10:
            score += 20
            reasons.append("LSTM 예측상 24개월 뒤 같은 조건의 평당가가 10% 이상 하락할 가능성이 있습니다.")
            advice.append("2년 뒤 퇴거 시점의 보증금 회수 가능성을 기준으로 보수적으로 판단하세요.")
        elif forecast_change_pct < -5:
            score += 10
            reasons.append("LSTM 예측상 24개월 뒤 가격 흐름이 하락장에 가깝습니다.")
        elif forecast_change_pct > 5 and gap_pct is not None and gap_pct > 10:
            score -= 5
            reasons.append("상승장 예측이 있어 고평가 신호 일부는 완화될 수 있습니다.")

    score = max(0, min(100, score))
    if score >= 75:
        level = "위험"
    elif score >= 50:
        level = "주의"
    else:
        level = "보통"

    if not advice:
        advice.append("계약 전 등기부등본, 임대인 체납 여부, 반환보증 가입 가능성, 전입신고·확정일자 절차를 확인하세요.")
    return score, level, reasons, advice


def _building_reference(building_monthly, args, bucket, input_floor_bucket, input_per_pyeong):
    if not args.property_name:
        return {
            "status": "건물명을 입력하지 않아 건물 단위 비교는 건너뛰었습니다.",
            "matched_months": 0,
            "recent_building_median_per_pyeong": None,
            "building_gap_pct": None,
        }

    base = building_monthly[
        (building_monthly["sido"] == args.sido)
        & (building_monthly["sigungu"] == args.sigungu)
        & (building_monthly["dong_name"] == args.dong)
        & (building_monthly["housing_type"] == args.housing_type)
        & (building_monthly["property_name"] == args.property_name)
        & (building_monthly["area_bucket"] == bucket)
    ].copy()
    exact_floor = base[base["floor_bucket"] == input_floor_bucket].copy()
    ref = exact_floor if not exact_floor.empty else base
    ref = ref.sort_values("contract_month")
    recent = _safe_float(ref["building_median_deposit_per_pyeong"].tail(3).median()) if not ref.empty else None
    gap = round((input_per_pyeong - recent) / recent * 100, 2) if recent else None
    return {
        "status": "같은 건물·면적대·층구간 기준" if not exact_floor.empty else "같은 건물·면적대 기준",
        "property_name": args.property_name,
        "floor_bucket": input_floor_bucket,
        "matched_months": int(len(ref)),
        "recent_building_median_per_pyeong": recent,
        "building_gap_pct": gap,
        "recent_building_trade_count": int(ref["building_count"].tail(3).sum()) if not ref.empty else 0,
        "avg_area_m2": _safe_float(ref["building_avg_area_m2"].tail(3).mean()) if not ref.empty else None,
        "avg_floor": _safe_float(ref["building_avg_floor"].tail(3).mean()) if not ref.empty else None,
    }


def analyze(args):
    jeonse_raw, sale_raw, source_counts = read_db()
    jeonse = normalize_jeonse(jeonse_raw)
    sale = normalize_sale(sale_raw)
    jeonse_monthly = monthly_stats(jeonse, "deposit_per_pyeong", "median_deposit_per_pyeong", include_dong=True)
    sale_monthly = monthly_stats(sale, "sale_per_pyeong", "median_sale_per_pyeong", include_dong=False)
    building_monthly = building_monthly_stats(jeonse)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    jeonse_monthly.to_csv(PROCESSED_DIR / "jeonse_monthly.csv", index=False, encoding="utf-8-sig")
    sale_monthly.to_csv(PROCESSED_DIR / "sale_monthly.csv", index=False, encoding="utf-8-sig")
    building_monthly.to_csv(PROCESSED_DIR / "jeonse_building_monthly.csv", index=False, encoding="utf-8-sig")

    bucket = area_bucket(args.area_m2)
    input_floor_bucket = floor_bucket(args.floor)
    input_per_pyeong = args.deposit / (args.area_m2 / 3.3058)
    building_ref = _building_reference(building_monthly, args, bucket, input_floor_bucket, input_per_pyeong)

    group_filter = (
        (jeonse_monthly["sido"] == args.sido)
        & (jeonse_monthly["sigungu"] == args.sigungu)
        & (jeonse_monthly["dong_name"] == args.dong)
        & (jeonse_monthly["housing_type"] == args.housing_type)
        & (jeonse_monthly["area_bucket"] == bucket)
    )
    group_series = jeonse_monthly.loc[group_filter].sort_values("contract_month")
    recent_median = _safe_float(group_series["median_deposit_per_pyeong"].tail(3).median()) if not group_series.empty else None
    gap_pct = round((input_per_pyeong - recent_median) / recent_median * 100, 2) if recent_median else None

    sale_filter = (
        (sale_monthly["sido"] == args.sido)
        & (sale_monthly["sigungu"] == args.sigungu)
        & (sale_monthly["housing_type"] == args.housing_type)
        & (sale_monthly["area_bucket"] == bucket)
    )
    sale_ref = sale_monthly.loc[sale_filter].sort_values("contract_month")
    sale_per_pyeong = _safe_float(sale_ref["median_sale_per_pyeong"].tail(3).median()) if not sale_ref.empty else None
    jeonse_ratio = round(input_per_pyeong / sale_per_pyeong * 100, 2) if sale_per_pyeong else None

    forecast_result = None
    if len(group_series) >= LOOKBACK + 6:
        metadata = train_lstm(PROCESSED_DIR / "jeonse_monthly.csv", MODEL_DIR)
        key_data = {"sido": args.sido, "sigungu": args.sigungu, "dong_name": args.dong, "housing_type": args.housing_type, "area_bucket": bucket}
        model_key = "_".join(str(key_data[k]).replace(" ", "") for k in ["sido", "sigungu", "dong_name", "housing_type", "area_bucket"])
        if model_key in metadata.get("trained_models", {}):
            forecast_result = forecast(key_data, group_series["median_deposit_per_pyeong"].astype(float).tolist())

    forecast_change_pct = forecast_result["change_rate"] if forecast_result else None
    score, level, reasons, advice = _score_risk(gap_pct, jeonse_ratio, forecast_change_pct, building_ref["building_gap_pct"])

    return {
        "input": {
            "sido": args.sido,
            "sigungu": args.sigungu,
            "dong": args.dong,
            "property_name": args.property_name,
            "housing_type": args.housing_type,
            "area_m2": args.area_m2,
            "floor": args.floor,
            "deposit_amount_manwon": args.deposit,
            "area_bucket": bucket,
            "floor_bucket": input_floor_bucket,
            "input_deposit_per_pyeong": round(input_per_pyeong, 2),
        },
        "data_status": {
            "db_rows": source_counts,
            "matched_region_months": int(len(group_series)),
            "matched_building_months": building_ref["matched_months"],
            "usable_sale_months": int(len(sale_ref)),
        },
        "building_analysis": building_ref,
        "market_analysis": {
            "recent_region_median_deposit_per_pyeong": recent_median,
            "region_deposit_gap_pct": gap_pct,
            "sale_per_pyeong": sale_per_pyeong,
            "jeonse_ratio": jeonse_ratio,
            "forecast_24m": forecast_result,
            "market_phase": _market_phase(forecast_change_pct),
        },
        "risk": {"risk_level": level, "risk_score": score, "reasons": reasons, "advice": advice},
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze one jeonse candidate using building average, market data, and LSTM forecast.")
    parser.add_argument("--sido", default="서울특별시")
    parser.add_argument("--sigungu", default="종로구")
    parser.add_argument("--dong", required=True)
    parser.add_argument("--property-name", default="")
    parser.add_argument("--housing-type", default="오피스텔")
    parser.add_argument("--area-m2", type=float, required=True)
    parser.add_argument("--floor", type=float, default=0)
    parser.add_argument("--deposit", type=float, required=True, help="보증금, 만원 단위")
    args = parser.parse_args()
    print(json.dumps(analyze(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
