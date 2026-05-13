"""
Forecast Jongno-gu sale prices and estimate can-jeonse risk.

Input data:
    data/*.csv

Output:
    modeling/artifacts/can_jeonse/

The model aggregates transactions by:
    dong_name + property_type + month

Area is normalized with price per pyeong, so no area bucket is used.
"""

from __future__ import annotations

import argparse
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_absolute_percentage_error,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

try:
    from lightgbm import LGBMRegressor
except ImportError:  # pragma: no cover
    LGBMRegressor = None

try:
    from catboost import CatBoostRegressor
except ImportError:  # pragma: no cover
    CatBoostRegressor = None


warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ARTIFACT_DIR = ROOT / "modeling" / "artifacts" / "can_jeonse"

M2_PER_PYEONG = 3.3058
HORIZONS = (1, 3, 6, 12, 24)
RISK_THRESHOLD = 0.80
GROUP_KEYS = ["dong_name", "property_type"]
CAT_COLS = ["dong_name", "property_type"]
NUM_COLS = [
    "month_num",
    "year",
    "sale_count",
    "jeonse_count",
    "sale_per_pyeong",
    "jeonse_per_pyeong",
    "jeonse_to_sale_ratio",
    "sale_lag_1",
    "sale_lag_2",
    "sale_lag_3",
    "sale_lag_6",
    "sale_lag_12",
    "sale_roll_mean_3",
    "sale_roll_mean_6",
    "sale_roll_mean_12",
    "sale_mom_change",
    "jeonse_roll_mean_3",
    "jeonse_roll_mean_6",
    "jeonse_roll_mean_12",  # [#4] 추가: sale과 동일하게 12개월 이동평균 포함
    "avg_building_age",
    "avg_floor",
]


@dataclass(frozen=True)
class ModelBundle:
    horizon: int
    lightgbm: Pipeline
    catboost: Pipeline | None


# ─────────────────────────────────────────────
# [#2] 면적 구간 정의 및 구간별 평당가 산출
# ─────────────────────────────────────────────
AREA_BUCKET_DEFS: list[tuple[float, float, str]] = [
    (0,   33,          "~33㎡ (10평 미만)"),
    (33,  66,          "33~66㎡ (10~20평)"),
    (66,  99,          "66~99㎡ (20~30평)"),
    (99,  float("inf"), "99㎡~ (30평 이상)"),
]


def get_area_bucket(area_m2: float) -> str:
    """전용면적(㎡)을 4개 구간 레이블로 변환."""
    for lo, hi, label in AREA_BUCKET_DEFS:
        if lo <= area_m2 < hi:
            return label
    return AREA_BUCKET_DEFS[-1][2]


def compute_area_bucket_prices(transactions: pd.DataFrame, months: int = 12) -> pd.DataFrame:
    """동 × 유형 × 면적구간별 최근 N개월 평당가 및 현재 전세가율 산출.

    Streamlit 화면의 '구간별 평당가 현황' 테이블 데이터 소스로 사용할 수 있음.

    반환 컬럼:
        dong_name, property_type, area_bucket,
        sale_per_pyeong, sale_count,
        jeonse_per_pyeong, jeonse_count,
        jeonse_to_sale_ratio, risk_level
    """
    cutoff = transactions["month"].max() - pd.DateOffset(months=months - 1)
    recent = transactions[transactions["month"] >= cutoff].copy()
    recent["area_bucket"] = recent["exclusive_area_m2"].apply(get_area_bucket)

    index_cols = ["dong_name", "property_type", "area_bucket"]

    sale_grp = (
        recent[recent["trade_type"] == "sale"]
        .groupby(index_cols)
        .apply(
            lambda g: pd.Series({
                "sale_per_pyeong": weighted_average(
                    g["price_per_pyeong"], g["exclusive_area_pyeong"]
                ),
                "sale_count": len(g),
            }),
            include_groups=False,
        )
        .reset_index()
    )

    jeonse_grp = (
        recent[recent["trade_type"] == "jeonse"]
        .groupby(index_cols)
        .apply(
            lambda g: pd.Series({
                "jeonse_per_pyeong": weighted_average(
                    g["price_per_pyeong"], g["exclusive_area_pyeong"]
                ),
                "jeonse_count": len(g),
            }),
            include_groups=False,
        )
        .reset_index()
    )

    result = sale_grp.merge(jeonse_grp, on=index_cols, how="outer")
    result["jeonse_to_sale_ratio"] = (
        result["jeonse_per_pyeong"] / result["sale_per_pyeong"]
    ).round(3)

    def _risk_label(ratio: float) -> str:
        if pd.isna(ratio):  return "데이터 부족"
        if ratio >= 1.00:   return "깡통 가능성 매우 높음"
        if ratio >= 0.90:   return "고위험"
        if ratio >= 0.80:   return "위험"
        if ratio >= 0.70:   return "주의"
        return "안전"

    result["risk_level"] = result["jeonse_to_sale_ratio"].apply(_risk_label)
    return result.sort_values(index_cols).reset_index(drop=True)


def safe_auc(metric_func, y_true: pd.Series, y_score: np.ndarray) -> float:
    if len(pd.Series(y_true).dropna().unique()) < 2:
        return float("nan")
    return float(metric_func(y_true, y_score))


def parse_file_meta(path: Path) -> tuple[str, str]:
    name = path.name
    trade_type = "sale" if "매매" in name else "jeonse"

    if "오피스텔" in name:
        property_type = "officetel"
    elif "연립다세대" in name:
        property_type = "villa"
    else:
        raise ValueError(f"Unknown property type in file name: {name}")

    return trade_type, property_type


def load_transactions(data_dir: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(data_dir.glob("*.csv")):
        if "종로구" not in path.name:
            continue

        trade_type, property_type = parse_file_meta(path)
        frame = pd.read_csv(path)

        if "house_name" in frame.columns:
            frame = frame.rename(columns={"house_name": "building_name"})
        if "officetel_name" in frame.columns:
            frame = frame.rename(columns={"officetel_name": "building_name"})
        if "deal_date" in frame.columns:
            frame = frame.rename(columns={"deal_date": "transaction_date"})
        if "contract_date" in frame.columns:
            frame = frame.rename(columns={"contract_date": "transaction_date"})

        price_col = "deal_amount" if trade_type == "sale" else "deposit_amount"
        frame["price_amount"] = pd.to_numeric(frame[price_col], errors="coerce")
        frame["trade_type"] = trade_type

        # [#3] 순전세만 사용: monthly_rent > 0 인 반전세 제외
        if trade_type == "jeonse" and "monthly_rent" in frame.columns:
            before = len(frame)
            frame = frame[
                pd.to_numeric(frame["monthly_rent"], errors="coerce").fillna(0) == 0
            ].copy()
            excluded = before - len(frame)
            if excluded > 0:
                print(f"  [필터] {path.name}: 반전세(월세 포함) {excluded}건 제외")
        frame["property_type"] = property_type
        frame["transaction_date"] = pd.to_datetime(frame["transaction_date"], errors="coerce")
        frame["exclusive_area_m2"] = pd.to_numeric(frame["exclusive_area_m2"], errors="coerce")
        frame["exclusive_area_pyeong"] = frame["exclusive_area_m2"] / M2_PER_PYEONG
        frame["floor"] = pd.to_numeric(frame["floor"], errors="coerce")
        frame["build_year"] = pd.to_numeric(frame["build_year"], errors="coerce")
        frame["dong_name"] = frame["dong_name"].fillna("unknown")
        frame["price_per_pyeong"] = frame["price_amount"] / frame["exclusive_area_pyeong"]
        frame["month"] = frame["transaction_date"].dt.to_period("M").dt.to_timestamp()
        frame["building_age"] = frame["transaction_date"].dt.year - frame["build_year"]

        keep_cols = [
            "trade_type",
            "property_type",
            "dong_name",
            "building_name",
            "jibun",
            "exclusive_area_m2",
            "exclusive_area_pyeong",
            "price_amount",
            "price_per_pyeong",
            "floor",
            "building_age",
            "month",
            "transaction_date",
        ]
        frames.append(frame[keep_cols])

    if not frames:
        raise FileNotFoundError(f"No Jongno-gu CSV files found in {data_dir}")

    transactions = pd.concat(frames, ignore_index=True)
    transactions = transactions.dropna(subset=["month", "exclusive_area_pyeong", "price_per_pyeong"])
    transactions = transactions[transactions["price_per_pyeong"] > 0].copy()
    return transactions


def weighted_average(values: pd.Series, weights: pd.Series) -> float:
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return np.nan
    return np.average(values[valid], weights=weights[valid])


def aggregate_monthly(transactions: pd.DataFrame) -> pd.DataFrame:
    index_cols = ["month", *GROUP_KEYS]
    sale = transactions[transactions["trade_type"] == "sale"].copy()
    jeonse = transactions[transactions["trade_type"] == "jeonse"].copy()

    sale_monthly = (
        sale.groupby(index_cols)
        .apply(
            lambda g: pd.Series(
                {
                    "sale_per_pyeong": weighted_average(
                        g["price_per_pyeong"], g["exclusive_area_pyeong"]
                    ),
                    "sale_count": len(g),
                    "avg_building_age": g["building_age"].mean(),
                    "avg_floor": g["floor"].mean(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )

    jeonse_monthly = (
        jeonse.groupby(index_cols)
        .apply(
            lambda g: pd.Series(
                {
                    "jeonse_per_pyeong": weighted_average(
                        g["price_per_pyeong"], g["exclusive_area_pyeong"]
                    ),
                    "jeonse_count": len(g),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )

    panel = sale_monthly.merge(jeonse_monthly, on=index_cols, how="outer")
    panel = panel.sort_values([*GROUP_KEYS, "month"]).reset_index(drop=True)
    panel["sale_count"] = panel["sale_count"].fillna(0)
    panel["jeonse_count"] = panel["jeonse_count"].fillna(0)

    for col in ["sale_per_pyeong", "jeonse_per_pyeong", "avg_building_age", "avg_floor"]:
        panel[col] = panel.groupby(GROUP_KEYS, dropna=False)[col].ffill()

    return panel.dropna(subset=["sale_per_pyeong"]).copy()


def add_time_features(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.sort_values([*GROUP_KEYS, "month"]).copy()
    grouped = panel.groupby(GROUP_KEYS, dropna=False)

    for lag in [1, 2, 3, 6, 12]:
        panel[f"sale_lag_{lag}"] = grouped["sale_per_pyeong"].shift(lag)

    for window in [3, 6, 12]:
        panel[f"sale_roll_mean_{window}"] = grouped["sale_per_pyeong"].transform(
            lambda s: s.shift(1).rolling(window, min_periods=1).mean()
        )

    for window in [3, 6, 12]:  # [#4] 12개월 추가 (NUM_COLS와 일치)
        panel[f"jeonse_roll_mean_{window}"] = grouped["jeonse_per_pyeong"].transform(
            lambda s: s.shift(1).rolling(window, min_periods=1).mean()
        )

    panel["sale_mom_change"] = grouped["sale_per_pyeong"].pct_change()
    panel["jeonse_to_sale_ratio"] = panel["jeonse_per_pyeong"] / panel["sale_per_pyeong"]
    panel["month_num"] = panel["month"].dt.month
    panel["year"] = panel["month"].dt.year

    for horizon in HORIZONS:
        future_price = grouped["sale_per_pyeong"].shift(-horizon)
        panel[f"target_growth_{horizon}m"] = future_price / panel["sale_per_pyeong"] - 1
        panel[f"actual_future_sale_per_pyeong_{horizon}m"] = future_price
        panel[f"actual_risk_ratio_{horizon}m"] = panel["jeonse_per_pyeong"] / future_price
        panel[f"actual_risk_label_{horizon}m"] = (
            panel[f"actual_risk_ratio_{horizon}m"] >= RISK_THRESHOLD
        ).astype("Int64")

    return panel


def build_model(seed: int = 42) -> tuple[Pipeline, Pipeline | None]:
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=2), CAT_COLS),
            ("num", "passthrough", NUM_COLS),
        ]
    )

    if LGBMRegressor is None:
        lightgbm_regressor = HistGradientBoostingRegressor(random_state=seed, max_iter=300)
    else:
        lightgbm_regressor = LGBMRegressor(
            n_estimators=600,
            learning_rate=0.03,
            max_depth=4,
            num_leaves=16,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=seed,
            verbose=-1,
        )

    lightgbm = Pipeline([("preprocess", preprocessor), ("model", lightgbm_regressor)])

    catboost = None
    if CatBoostRegressor is not None:
        catboost = Pipeline(
            [
                ("preprocess", preprocessor),
                (
                    "model",
                    CatBoostRegressor(
                        iterations=700,
                        learning_rate=0.03,
                        depth=5,
                        loss_function="RMSE",
                        random_seed=seed,
                        verbose=False,
                        allow_writing_files=False,
                    ),
                ),
            ]
        )

    return lightgbm, catboost


def calculate_classification_metrics(
    valid: pd.DataFrame,
    actual_future: pd.Series,
    predicted_future: np.ndarray,
    horizon: int,
) -> dict[str, float | int]:
    y_true = valid[f"actual_risk_label_{horizon}m"].astype(int)
    y_score = valid["jeonse_per_pyeong"].to_numpy() / predicted_future
    y_pred = (y_score >= RISK_THRESHOLD).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()

    return {
        "risk_threshold": RISK_THRESHOLD,
        "risk_positive_count": int(y_true.sum()),
        "risk_negative_count": int((y_true == 0).sum()),
        "pr_auc": safe_auc(average_precision_score, y_true, y_score),
        "roc_auc": safe_auc(roc_auc_score, y_true, y_score),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "f1_score": float(f1_score(y_true, y_pred, zero_division=0)),
        "confusion_tn": int(tn),
        "confusion_fp": int(fp),
        "confusion_fn": int(fn),
        "confusion_tp": int(tp),
    }


def train_horizon_models(panel: pd.DataFrame, output_dir: Path) -> tuple[list[ModelBundle], pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = []
    bundles = []

    feature_frame = panel.dropna(subset=NUM_COLS).copy()
    feature_frame = feature_frame.replace([np.inf, -np.inf], np.nan).dropna(subset=NUM_COLS)

    for horizon in HORIZONS:
        target_col = f"target_growth_{horizon}m"
        train_frame = feature_frame.dropna(subset=[target_col, f"actual_risk_label_{horizon}m"]).copy()
        if train_frame.empty:
            continue

        cutoff = train_frame["month"].quantile(0.8)
        train = train_frame[train_frame["month"] <= cutoff]
        valid = train_frame[train_frame["month"] > cutoff]
        if valid.empty:
            valid = train.tail(max(1, len(train) // 5))
            train = train.iloc[: -len(valid)]

        x_train, y_train = train[CAT_COLS + NUM_COLS], train[target_col]
        x_valid, y_valid = valid[CAT_COLS + NUM_COLS], valid[target_col]

        lightgbm, catboost = build_model()
        lightgbm.fit(x_train, y_train)
        light_pred = lightgbm.predict(x_valid)

        predictions = [light_pred]
        if catboost is not None:
            catboost.fit(x_train, y_train)
            predictions.append(catboost.predict(x_valid))

        ensemble_pred = np.mean(predictions, axis=0)
        actual_future = valid["sale_per_pyeong"] * (1 + y_valid)
        predicted_future = valid["sale_per_pyeong"].to_numpy() * (1 + ensemble_pred)

        row = {
            "horizon_months": horizon,
            "train_rows": int(len(train)),
            "valid_rows": int(len(valid)),
            "growth_mae": float(mean_absolute_error(y_valid, ensemble_pred)),
            "future_price_mae": float(mean_absolute_error(actual_future, predicted_future)),
            "future_price_mape": float(mean_absolute_percentage_error(actual_future, predicted_future)),
            "uses_catboost": catboost is not None,
        }
        row.update(calculate_classification_metrics(valid, actual_future, predicted_future, horizon))
        metrics.append(row)

        bundle = ModelBundle(horizon=horizon, lightgbm=lightgbm, catboost=catboost)
        bundles.append(bundle)
        joblib.dump(bundle, output_dir / f"growth_{horizon}m_model.joblib")

    metrics_frame = pd.DataFrame(metrics)
    metrics_frame.to_csv(output_dir / "metrics.csv", index=False, encoding="utf-8-sig")
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return bundles, metrics_frame


def predict_growth(bundle: ModelBundle, features: pd.DataFrame) -> np.ndarray:
    predictions = [bundle.lightgbm.predict(features)]
    if bundle.catboost is not None:
        predictions.append(bundle.catboost.predict(features))
    return np.mean(predictions, axis=0)


def forecast_latest_24_months(panel: pd.DataFrame, model_24m: ModelBundle) -> pd.DataFrame:
    latest_rows = panel.dropna(subset=NUM_COLS).sort_values("month").groupby(GROUP_KEYS).tail(1)
    features = latest_rows[CAT_COLS + NUM_COLS]
    growth_24m = predict_growth(model_24m, features)
    forecast_sale = latest_rows["sale_per_pyeong"].to_numpy() * (1 + growth_24m)

    result = latest_rows[["dong_name", "property_type", "month", "sale_per_pyeong", "jeonse_per_pyeong"]].copy()
    result["base_month"] = result["month"].dt.strftime("%Y-%m")
    result["forecast_month"] = (result["month"] + pd.DateOffset(months=24)).dt.strftime("%Y-%m")
    result["current_sale_per_pyeong"] = result["sale_per_pyeong"]
    result["forecast_sale_per_pyeong_24m"] = forecast_sale
    result["current_jeonse_per_pyeong"] = result["jeonse_per_pyeong"]
    result["risk_ratio_24m"] = result["current_jeonse_per_pyeong"] / result["forecast_sale_per_pyeong_24m"]
    result["risk_level"] = pd.cut(
        result["risk_ratio_24m"],
        bins=[-np.inf, 0.70, 0.80, 0.90, 1.00, np.inf],
        labels=["안전", "주의", "위험", "고위험", "깡통 가능성 매우 높음"],
    )

    keep_cols = [
        "dong_name",
        "property_type",
        "base_month",
        "forecast_month",
        "current_sale_per_pyeong",
        "forecast_sale_per_pyeong_24m",
        "current_jeonse_per_pyeong",
        "risk_ratio_24m",
        "risk_level",
    ]
    return result[keep_cols].sort_values("risk_ratio_24m", ascending=False)


def run(data_dir: Path = DATA_DIR, output_dir: Path = ARTIFACT_DIR) -> None:
    print(f"[*] Loading transactions from {data_dir}...")
    transactions = load_transactions(data_dir)
    print(f"[+] Loaded {len(transactions)} transactions.")

    print("[*] Processing monthly panel and time features...")
    panel = add_time_features(aggregate_monthly(transactions))
    print(f"[+] Panel created with {len(panel)} rows.")

    output_dir.mkdir(parents=True, exist_ok=True)
    transactions.to_csv(output_dir / "transactions_normalized.csv", index=False, encoding="utf-8-sig")
    panel.to_csv(output_dir / "monthly_panel.csv", index=False, encoding="utf-8-sig")

    print("[*] Training horizon models (1m, 3m, 6m, 12m, 24m)...")
    bundles, metrics = train_horizon_models(panel, output_dir)
    print("[+] Training complete. Metrics saved.")

    print("[*] Generating latest 24-month forecast and risk assessment...")
    model_24m = next(bundle for bundle in bundles if bundle.horizon == 24)
    forecast = forecast_latest_24_months(panel, model_24m)
    forecast.to_csv(output_dir / "can_jeonse_risk_24m.csv", index=False, encoding="utf-8-sig")
    print(f"[+] Forecast complete. Results saved to {output_dir / 'can_jeonse_risk_24m.csv'}")

    print("\n=== Evaluation Metrics ===")
    print(metrics.to_string(index=False))

    print("\n=== Top 10 Can-Jeonse Risk Forecasts ===")
    print(
        forecast.head(10)
        .round(
            {
                "current_sale_per_pyeong": 2,
                "forecast_sale_per_pyeong_24m": 2,
                "current_jeonse_per_pyeong": 2,
                "risk_ratio_24m": 3,
            }
        )
        .to_string(index=False)
    )

    summary = {
        "transaction_rows": int(len(transactions)),
        "monthly_panel_rows": int(len(panel)),
        "metrics": metrics.to_dict(orient="records"),
        "top_risk_rows": forecast.head(10).to_dict(orient="records"),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("[+] Execution finished successfully.")


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACT_DIR)
    args = parser.parse_args(argv)
    run(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
