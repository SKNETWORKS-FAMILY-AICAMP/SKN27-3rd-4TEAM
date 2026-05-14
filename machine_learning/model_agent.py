"""Model agent interface for can-jeonse market risk analysis.

This module wraps the trained machine_learning forecast artifacts so a
supervisor agent can call one stable function:

    analyze_contract(contract_info: dict) -> dict

The training data excludes basement/underground rows (floor < 0). If a user
contract is basement/underground, this agent returns excluded_case instead of
forcing a ground-floor market model onto a structurally different unit.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

# Make imports work both as a script and as a package-like module.
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from can_jeonse_forecast import (  # noqa: E402
    ARTIFACT_DIR,
    CAT_COLS,
    M2_PER_PYEONG,
    NUM_COLS,
    RISK_THRESHOLD,
    ModelBundle,
    get_area_bucket,
    predict_growth,
)

AGENT_NAME = "model_agent"
PRIMARY_HORIZON = 24
LOW_JEONSE_RATIO_THRESHOLD = 0.30
LOW_PRICE_ANOMALY_FACTOR = 0.85
BASEMENT_KEYWORDS = ("반지하", "지하층", "지하", "B1", "b1", "basement", "Basement")
LOW_JEONSE_ADDITIONAL_CHECKS = [
    "월세, 관리비, 옵션비, 별도 사용료가 과도하게 책정되었는지 확인",
    "등기부등본상 선순위 근저당, 압류, 가압류, 신탁등기, 임차권등기명령 확인",
    "건축물대장상 위반건축물, 용도 불일치, 불법 증축, 불법 쪼개기 여부 확인",
    "실거래 시세 대비 과도하게 낮은 금액인 경우 시설 하자, 침수·누수, 채광·환기 문제 확인",
    "특약상 수리 책임, 원상복구, 관리비, 중도해지, 보증보험 제한 조항 확인",
    "전세보증금 반환보증 가입 가능 여부, 보증 한도, 임대인 체납 여부 확인",
]
PROPERTY_TYPE_MAP = {
    "villa": "villa",
    "연립": "villa",
    "연립다세대": "villa",
    "다세대": "villa",
    "빌라": "villa",
    "주거용": "villa",
    "officetel": "officetel",
    "오피스텔": "officetel",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if pd.isna(value) if not isinstance(value, (dict, list, tuple, str)) else False:
        return None
    return value


def _round_or_none(value: Any, digits: int = 4) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def normalize_property_type(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    for key, normalized in PROPERTY_TYPE_MAP.items():
        if key.lower() in text.lower():
            return normalized
    return text if text in {"villa", "officetel"} else None


def extract_dong_name(*texts: Any) -> str | None:
    for value in texts:
        if not value:
            continue
        match = re.search(r"([가-힣0-9]+동)", str(value))
        if match:
            return match.group(1)
    return None


def parse_amount_to_manwon(value: Any) -> float | None:
    """Parse deposit amount into Korean manwon units."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)

    text = str(value).replace(",", "").replace(" ", "")
    if not text:
        return None

    total = 0.0
    eok = re.search(r"([0-9.]+)억", text)
    man = re.search(r"([0-9.]+)만", text)
    if eok:
        total += float(eok.group(1)) * 10000
    if man:
        total += float(man.group(1))
    if total > 0:
        return total

    nums = re.findall(r"[0-9.]+", text)
    return float(nums[0]) if nums else None


def parse_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    text = str(value).replace(",", "")
    nums = re.findall(r"-?[0-9.]+", text)
    return float(nums[0]) if nums else None


def normalize_contract(contract_info: dict[str, Any]) -> dict[str, Any]:
    info = dict(contract_info)
    info["dong_name"] = info.get("dong_name") or extract_dong_name(info.get("address"), info.get("raw_text"))
    info["property_type"] = normalize_property_type(info.get("property_type") or info.get("building_type"))
    info["deposit_amount_manwon"] = parse_amount_to_manwon(
        info.get("deposit_amount_manwon") or info.get("deposit") or info.get("deposit_amount")
    )

    area_m2 = parse_float(info.get("exclusive_area_m2") or info.get("area_m2"))
    area_pyeong = parse_float(info.get("exclusive_area_pyeong") or info.get("area_pyeong"))
    if area_m2 is None and area_pyeong is not None:
        area_m2 = area_pyeong * M2_PER_PYEONG
    if area_pyeong is None and area_m2 is not None:
        area_pyeong = area_m2 / M2_PER_PYEONG
    info["exclusive_area_m2"] = area_m2
    info["exclusive_area_pyeong"] = area_pyeong

    floor = parse_float(info.get("floor"))
    info["floor"] = floor

    base_month = info.get("base_month")
    if not base_month:
        date_value = info.get("contract_date") or info.get("transaction_date")
        if date_value:
            base_month = pd.to_datetime(date_value, errors="coerce")
            base_month = None if pd.isna(base_month) else base_month.to_period("M").to_timestamp()
    else:
        base_month = pd.to_datetime(str(base_month), errors="coerce")
        base_month = None if pd.isna(base_month) else base_month.to_period("M").to_timestamp()
    info["base_month"] = base_month

    return info


def validate_required(info: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not info.get("dong_name"):
        missing.append("dong_name")
    if not info.get("property_type"):
        missing.append("property_type")
    if info.get("base_month") is None:
        missing.append("contract_date_or_base_month")
    if info.get("deposit_amount_manwon") is None:
        missing.append("deposit_amount_manwon")
    if info.get("exclusive_area_m2") is None and info.get("exclusive_area_pyeong") is None:
        missing.append("exclusive_area_m2_or_exclusive_area_pyeong")
    return missing


FIELD_REQUESTS = {
    "dong_name": "주소 또는 동 이름(예: 서울특별시 종로구 신영동)",
    "property_type": "주택유형(villa/연립다세대/빌라 또는 officetel/오피스텔)",
    "contract_date_or_base_month": "계약일 또는 계약월(예: 2025-05-12)",
    "deposit_amount_manwon": "보증금(만원 단위 또는 2억 8,600만 원 형식)",
    "exclusive_area_m2_or_exclusive_area_pyeong": "전용면적(㎡ 또는 평)",
    "known_dong_property_market_data": "분석 가능한 종로구 동 이름과 주택유형",
}


def build_required_input_request(missing: list[str]) -> dict[str, Any]:
    requested = [FIELD_REQUESTS.get(field, field) for field in missing]
    return {
        "requested_fields": requested,
        "minimum_text_input_example": (
            "예: 서울특별시 종로구 신영동, 연립다세대, 계약일 2025-05-12, "
            "보증금 2억 8,600만 원, 전용면적 42.39㎡, 3층"
        ),
        "ask_user_message": "계약서 파일이 없으면 주소, 주택유형, 계약일, 보증금, 전용면적, 층수를 알려주세요.",
    }


def is_basement_case(info: dict[str, Any]) -> tuple[bool, str | None]:
    floor = info.get("floor")
    if floor is not None and floor < 0:
        return True, "floor_below_zero"
    if bool(info.get("is_basement")):
        return True, "is_basement_true"
    raw_text = " ".join(str(info.get(key, "")) for key in ("raw_text", "address", "unit_description"))
    if any(keyword in raw_text for keyword in BASEMENT_KEYWORDS):
        return True, "basement_keyword"
    return False, None


def risk_level(ratio: float | None) -> str | None:
    if ratio is None or pd.isna(ratio):
        return None
    if ratio < 0.70:
        return "안전"
    if ratio < 0.80:
        return "주의"
    if ratio < 0.90:
        return "위험"
    if ratio < 1.00:
        return "고위험"
    return "깡통 가능성 매우 높음"


def load_artifacts(artifact_dir: Path = ARTIFACT_DIR) -> dict[str, pd.DataFrame]:
    return {
        "panel": pd.read_csv(artifact_dir / "monthly_panel.csv", parse_dates=["month"]),
        "transactions": pd.read_csv(
            artifact_dir / "transactions_normalized.csv",
            parse_dates=["month", "transaction_date"],
        ),
        "best_models": pd.read_csv(artifact_dir / "best_models.csv"),
    }


def select_market_row(panel: pd.DataFrame, info: dict[str, Any]) -> tuple[pd.Series | None, str]:
    group = panel[
        (panel["dong_name"] == info["dong_name"])
        & (panel["property_type"] == info["property_type"])
    ].sort_values("month")
    if group.empty:
        return None, "no_dong_property_match"

    base_month = info["base_month"]
    exact = group[group["month"] == base_month]
    if not exact.empty:
        return exact.iloc[-1], "exact_month"

    before = group[group["month"] <= base_month]
    if not before.empty:
        return before.iloc[-1], "latest_before_contract_month"

    return group.iloc[0], "earliest_available_after_contract_month"


def _weighted_average(values: pd.Series, weights: pd.Series) -> float | None:
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return None
    return float(np.average(values[valid], weights=weights[valid]))


def area_bucket_market(transactions: pd.DataFrame, info: dict[str, Any]) -> dict[str, Any]:
    base_month = info["base_month"]
    start_month = base_month - pd.DateOffset(months=11)
    area_bucket = get_area_bucket(float(info["exclusive_area_m2"]))

    subset = transactions[
        (transactions["dong_name"] == info["dong_name"])
        & (transactions["property_type"] == info["property_type"])
        & (transactions["month"] >= start_month)
        & (transactions["month"] <= base_month)
    ].copy()
    subset["area_bucket"] = subset["exclusive_area_m2"].apply(get_area_bucket)
    bucket_subset = subset[subset["area_bucket"] == area_bucket]

    match_type = "same_dong_property_area_bucket_recent_12m"
    market = bucket_subset
    if market.empty:
        match_type = "same_dong_property_recent_12m_fallback"
        market = subset

    sale = market[market["trade_type"] == "sale"]
    jeonse = market[market["trade_type"] == "jeonse"]
    sale_pp = _weighted_average(sale["price_per_pyeong"], sale["exclusive_area_pyeong"]) if not sale.empty else None
    jeonse_pp = _weighted_average(jeonse["price_per_pyeong"], jeonse["exclusive_area_pyeong"]) if not jeonse.empty else None
    contract_pp = info["deposit_amount_manwon"] / info["exclusive_area_pyeong"]
    ratio = contract_pp / sale_pp if sale_pp else None
    low_price_anomaly = bool(jeonse_pp and contract_pp < jeonse_pp * LOW_PRICE_ANOMALY_FACTOR)

    return {
        "area_bucket": area_bucket,
        "match_type": match_type,
        "area_bucket_sale_per_pyeong": _round_or_none(sale_pp, 2),
        "area_bucket_jeonse_per_pyeong": _round_or_none(jeonse_pp, 2),
        "area_bucket_risk_ratio": _round_or_none(ratio, 4),
        "area_bucket_risk_level": risk_level(ratio),
        "sale_sample_count": int(len(sale)),
        "jeonse_sample_count": int(len(jeonse)),
        "low_price_anomaly": low_price_anomaly,
        "low_price_anomaly_rule": f"contract_jeonse_per_pyeong < area_bucket_jeonse_per_pyeong * {LOW_PRICE_ANOMALY_FACTOR}",
    }


def build_low_jeonse_ratio_check(current_ratio: float | None, area_ratio: float | None) -> dict[str, Any]:
    ratio_candidates = {
        "current_risk_ratio": current_ratio,
        "area_bucket_risk_ratio": area_ratio,
    }
    matched = [name for name, value in ratio_candidates.items() if value is not None and value <= LOW_JEONSE_RATIO_THRESHOLD]
    is_low = bool(matched)
    return {
        "threshold_ratio": LOW_JEONSE_RATIO_THRESHOLD,
        "is_low_jeonse_ratio": is_low,
        "basis": matched or None,
        "message": (
            "현재 계약 전세가율 또는 면적구간 기준 전세가율이 30% 이하인 저전세가율 계약입니다. "
            "가격 기준 깡통전세 위험은 낮게 보일 수 있으나, 보증금이 낮은 사유와 별도 비용·권리관계·건축물 상태를 반드시 확인해야 합니다."
            if is_low
            else "현재 계약 전세가율과 면적구간 기준 전세가율이 모두 30%를 초과하여 저전세가율 특이 케이스로 분류하지 않습니다."
        ),
        "additional_checks": LOW_JEONSE_ADDITIONAL_CHECKS if is_low else [],
    }


def build_price_position_check(current_ratio: float | None, area_check: dict[str, Any]) -> dict[str, Any]:
    area_ratio = area_check.get("area_bucket_risk_ratio")
    low_price_anomaly = bool(area_check.get("low_price_anomaly"))
    messages: list[str] = []
    is_above_current_sale_price = bool(current_ratio is not None and current_ratio >= 1.0)
    is_high_jeonse_ratio = bool(current_ratio is not None and current_ratio >= RISK_THRESHOLD)
    if is_above_current_sale_price:
        messages.append("계약 전세 평당가가 현재 시장 매매 평당가 이상이므로 깡통전세 가능성이 매우 높습니다.")
    elif is_high_jeonse_ratio:
        messages.append("계약 전세 평당가가 현재 시장 매매 평당가의 80% 이상으로 높은 편입니다.")
    if low_price_anomaly:
        messages.append("계약 전세 평당가가 같은 동·주택유형·면적구간의 최근 전세 시세보다 15% 이상 낮아 저가 이상치로 표시했습니다.")
    if not messages:
        messages.append("계약 전세가가 현재 시세 기준에서 극단적인 고가 또는 저가 이상치로 표시되지는 않았습니다.")
    return {
        "is_above_current_sale_price": is_above_current_sale_price,
        "is_high_jeonse_ratio": is_high_jeonse_ratio,
        "low_price_anomaly": low_price_anomaly,
        "current_risk_ratio": _round_or_none(current_ratio, 4),
        "area_bucket_risk_ratio": area_ratio,
        "messages": messages,
    }

def _load_bundle(horizon: int, artifact_dir: Path = ARTIFACT_DIR) -> ModelBundle:
    # Older artifacts were saved from script execution, so pickle may look for
    # __main__.ModelBundle. Register the class before loading for compatibility.
    setattr(sys.modules["__main__"], "ModelBundle", ModelBundle)
    return joblib.load(artifact_dir / f"growth_{horizon}m_best_model.joblib")


def _metrics_for(best_models: pd.DataFrame, horizon: int) -> dict[str, Any]:
    row = best_models[best_models["horizon_months"] == horizon]
    if row.empty:
        return {}
    r = row.iloc[0]
    overfit = {}
    leakage = {}
    for key, target in (("overfit_audit", overfit), ("leakage_audit", leakage)):
        try:
            parsed = ast.literal_eval(str(r[key]))
            target.update(parsed)
        except Exception:
            pass
    return {
        "horizon_months": int(r["horizon_months"]),
        "model_name": str(r["model_name"]),
        "valid_mape": _round_or_none(r["future_price_mape"], 4),
        "baseline_mape": _round_or_none(r["baseline_future_price_mape"], 4),
        "model_beats_baseline": bool(r["model_beats_baseline_mape"]),
        "leakage_safe": bool(leakage.get("is_leakage_safe_for_validation", True)),
        "overfit_warning": bool(overfit.get("warning", False)),
        "overfit_severe": bool(overfit.get("severe", False)),
    }


def forecast_market(row: pd.Series, info: dict[str, Any], best_models: pd.DataFrame, horizon: int) -> dict[str, Any]:
    feature_row = row[CAT_COLS + NUM_COLS].to_frame().T
    if feature_row[NUM_COLS].isna().any(axis=None):
        return {
            "horizon_months": horizon,
            "status": "unavailable",
            "reason": "selected_market_row_has_missing_model_features",
        }

    bundle = _load_bundle(horizon)
    growth = float(predict_growth(bundle, feature_row)[0])
    current_sale_pp = float(row["sale_per_pyeong"])
    forecast_sale_pp = current_sale_pp * (1.0 + growth)
    contract_pp = info["deposit_amount_manwon"] / info["exclusive_area_pyeong"]
    ratio = contract_pp / forecast_sale_pp if forecast_sale_pp > 0 else None
    metrics = _metrics_for(best_models, horizon)

    return {
        "horizon_months": horizon,
        "status": "success",
        "model_name": bundle.model_name,
        "model_members": list(bundle.models.keys()),
        "predicted_growth": _round_or_none(growth, 4),
        "forecast_sale_per_pyeong": _round_or_none(forecast_sale_pp, 2),
        "forecast_risk_ratio": _round_or_none(ratio, 4),
        "forecast_risk_level": risk_level(ratio),
        "quality": metrics,
    }


def build_price_evidence(
    contract_pp: float,
    current_sale_pp: float,
    current_jeonse_pp: float,
    current_ratio: float | None,
    area_check: dict[str, Any],
    primary_forecast: dict[str, Any],
    match_type: str,
    market_month: str,
) -> dict[str, Any]:
    primary_ratio = primary_forecast.get("forecast_risk_ratio")
    primary_level = primary_forecast.get("forecast_risk_level")
    return {
        "final_prediction_model": "24m_lightgbm",
        "final_risk_basis": "contract_jeonse_per_pyeong / forecast_sale_per_pyeong_24m",
        "nearby_price_data": [
            {
                "basis": area_check.get("match_type"),
                "area_bucket": area_check.get("area_bucket"),
                "sale_price_per_pyeong": area_check.get("area_bucket_sale_per_pyeong"),
                "jeonse_price_per_pyeong": area_check.get("area_bucket_jeonse_per_pyeong"),
                "sale_sample_count": area_check.get("sale_sample_count"),
                "jeonse_sample_count": area_check.get("jeonse_sample_count"),
                "risk_ratio": area_check.get("area_bucket_risk_ratio"),
                "risk_level": area_check.get("area_bucket_risk_level"),
            }
        ],
        "sale_price": primary_forecast.get("forecast_sale_per_pyeong"),
        "sale_price_type": "24개월 LightGBM 예측 매매 평당가",
        "jeonse_price": _round_or_none(contract_pp, 2),
        "jeonse_price_type": "계약 전세 평당가",
        "jeonse_ratio": primary_ratio,
        "risk": primary_level,
        "calculation_basis": "계약 전세 평당가를 24개월 LightGBM 예측 매매 평당가로 나눈 값입니다.",
        "datasource": [
            "machine_learning/artifacts/can_jeonse/monthly_panel.csv",
            "machine_learning/artifacts/can_jeonse/transactions_normalized.csv",
            "machine_learning/artifacts/can_jeonse/growth_24m_best_model.joblib",
        ],
        "supporting_evidence": {
            "current_market": {
                "basis": match_type,
                "market_base_month": market_month,
                "sale_price_per_pyeong": _round_or_none(current_sale_pp, 2),
                "jeonse_price_per_pyeong": _round_or_none(current_jeonse_pp, 2),
                "risk_ratio": _round_or_none(current_ratio, 4),
                "risk_level": risk_level(current_ratio),
                "usage": "최종 등급 산정에는 직접 사용하지 않고 현재 시세 설명 근거로만 사용",
            },
            "area_bucket_recent_12m": {
                "basis": area_check.get("match_type"),
                "risk_ratio": area_check.get("area_bucket_risk_ratio"),
                "risk_level": area_check.get("area_bucket_risk_level"),
                "low_price_anomaly": area_check.get("low_price_anomaly"),
                "usage": "최종 등급 산정에는 직접 사용하지 않고 면적대 시세 설명 근거로만 사용",
            },
        },
        "caution": "24개월 LightGBM은 전세계약 만기 시점과 가장 잘 맞는 최종 모델입니다. 다만 overfit severe 경고가 있어 현재 시세, 면적구간 시세, 법률/특약 검토와 함께 설명해야 합니다.",
    }


def analyze_contract(contract_info: dict[str, Any], artifact_dir: Path = ARTIFACT_DIR) -> dict[str, Any]:
    info = normalize_contract(contract_info)
    contract_id = info.get("contract_id")

    missing = validate_required(info)
    if missing:
        return {
            "status": "need_more_info",
            "agent_name": AGENT_NAME,
            "contract_id": contract_id,
            "missing_fields": missing,
            "message": "가격 기반 위험도 분석을 위해 동, 주택유형, 계약일/계약월, 보증금, 전용면적 정보가 필요합니다.",
            "required_input_request": build_required_input_request(missing),
        }

    basement, basement_reason = is_basement_case(info)
    if basement:
        return {
            "status": "excluded_case",
            "agent_name": AGENT_NAME,
            "contract_id": contract_id,
            "reason": "basement_or_underground_unit",
            "detected_by": basement_reason,
            "message": "반지하 또는 지하층 매물은 현재 모델의 지상층 기준 시세 산출 대상에서 제외됩니다. 가격 구조와 침수, 채광, 환기 리스크가 달라 별도 검토가 필요합니다.",
            "recommended_next_agents": ["legal_agent", "special_terms_agent"],
        }

    artifacts = load_artifacts(artifact_dir)
    panel = artifacts["panel"]
    transactions = artifacts["transactions"]
    best_models = artifacts["best_models"]

    row, match_type = select_market_row(panel, info)
    if row is None:
        return {
            "status": "need_more_info",
            "agent_name": AGENT_NAME,
            "contract_id": contract_id,
            "missing_fields": ["known_dong_property_market_data"],
            "message": "해당 동과 주택유형의 학습/시세 데이터가 없어 가격 기반 모델 분석을 수행하기 어렵습니다.",
            "required_input_request": build_required_input_request(["known_dong_property_market_data"]),
        }

    contract_pp = info["deposit_amount_manwon"] / info["exclusive_area_pyeong"]
    current_sale_pp = float(row["sale_per_pyeong"])
    current_jeonse_pp = float(row["jeonse_per_pyeong"])
    current_ratio = contract_pp / current_sale_pp if current_sale_pp > 0 else None

    area_check = area_bucket_market(transactions, info)
    primary_forecast = forecast_market(row, info, best_models, PRIMARY_HORIZON)
    low_jeonse_ratio_check = build_low_jeonse_ratio_check(current_ratio, area_check.get("area_bucket_risk_ratio"))
    price_position_check = build_price_position_check(current_ratio, area_check)

    final_level = primary_forecast.get("forecast_risk_level") if primary_forecast.get("status") == "success" else None
    price_evidence = build_price_evidence(
        contract_pp=contract_pp,
        current_sale_pp=current_sale_pp,
        current_jeonse_pp=current_jeonse_pp,
        current_ratio=current_ratio,
        area_check=area_check,
        primary_forecast=primary_forecast,
        match_type=match_type,
        market_month=row["month"].strftime("%Y-%m"),
    )

    primary_quality = primary_forecast.get("quality", {}) if primary_forecast.get("status") == "success" else {}
    return {
        "status": "success",
        "agent_name": AGENT_NAME,
        "risk_type": "market_price_risk",
        "contract_id": contract_id,
        "input_summary": {
            "dong_name": info["dong_name"],
            "property_type": info["property_type"],
            "base_month": info["base_month"].strftime("%Y-%m"),
            "deposit_amount_manwon": _round_or_none(info["deposit_amount_manwon"], 2),
            "exclusive_area_m2": _round_or_none(info["exclusive_area_m2"], 2),
            "exclusive_area_pyeong": _round_or_none(info["exclusive_area_pyeong"], 2),
            "area_bucket": area_check["area_bucket"],
            "floor": _round_or_none(info.get("floor"), 1),
            "is_basement": False,
        },
        "current_market_check": {
            "market_match_type": match_type,
            "market_base_month": row["month"].strftime("%Y-%m"),
            "contract_jeonse_per_pyeong": _round_or_none(contract_pp, 2),
            "market_sale_per_pyeong": _round_or_none(current_sale_pp, 2),
            "market_jeonse_per_pyeong": _round_or_none(current_jeonse_pp, 2),
            "current_risk_ratio": _round_or_none(current_ratio, 4),
            "current_risk_level": risk_level(current_ratio),
        },
        "area_bucket_check": area_check,
        "price_position_check": price_position_check,
        "low_jeonse_ratio_check": low_jeonse_ratio_check,
        "forecast_check": {
            "primary": primary_forecast,
        },
        "price_evidence": price_evidence,
        "model_quality": primary_quality,
        "final_market_risk": final_level,
        "limitations": [
            "동일 매물의 실제 매매가가 아니라 동/주택유형/월 및 면적구간 시장 데이터 기준입니다.",
            "반지하 또는 지하층 매물은 모델 적용 대상에서 제외됩니다.",
            "최종 가격 위험도는 24개월 LightGBM 예측값만 기준으로 산정합니다.",
            "24개월 LightGBM은 baseline보다 낫지만 과적합 severe 경고가 있어 현재 시세와 면적구간 시세를 함께 설명해야 합니다.",
            "전세가율이 30% 이하인 저전세가율 계약은 가격 기반 깡통전세 위험도와 별개로 권리관계, 관리비·월세 구조, 건축물 하자, 보증보험 가입 가능 여부를 추가 확인해야 합니다.",
            "법률, 권리관계, 특약 위험은 별도 에이전트 확인이 필요합니다.",
        ],
        "recommended_next_agents": (["legal_agent", "special_terms_agent", "registry_agent", "building_agent", "insurance_agent"] if low_jeonse_ratio_check["is_low_jeonse_ratio"] else ["legal_agent", "special_terms_agent"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run model agent market-risk analysis.")
    parser.add_argument("--json", type=Path, help="Path to contract info JSON file.")
    parser.add_argument("--demo", action="store_true", help="Run with the sample contract discussed in docs.")
    args = parser.parse_args()

    if args.demo:
        payload = {
            "contract_id": "sample_01",
            "address": "서울특별시 종로구 신영동 179-21",
            "dong_name": "신영동",
            "property_type": "villa",
            "contract_date": "2025-05-12",
            "deposit_amount_manwon": 28600,
            "exclusive_area_m2": 42.39,
            "floor": 3,
            "is_basement": False,
            "source_type": "demo",
        }
    elif args.json:
        payload = json.loads(args.json.read_text(encoding="utf-8-sig"))
    else:
        payload = json.load(sys.stdin)

    result = analyze_contract(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_safe))


if __name__ == "__main__":
    main()
