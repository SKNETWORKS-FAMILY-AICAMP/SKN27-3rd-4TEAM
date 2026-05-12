from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts"
PROCESSED_DIR = ARTIFACT_ROOT / "processed"
MODEL_DIR = ARTIFACT_ROOT / "models"

FEATURES = [
    "housing_type_enc",
    "dong_name_enc",
    "area_pyeong",
    "floor",
    "building_age",
    "deposit_per_pyeong",
    "z_score",
    "jeonse_ratio",
    "q25",
    "q75",
]


def prepare_features(df: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
    from sklearn.preprocessing import LabelEncoder

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for col, target in [("housing_type", "housing_type_enc"), ("dong_name", "dong_name_enc")]:
        path = MODEL_DIR / f"{col}_label_encoder.pkl"
        if fit:
            encoder = LabelEncoder()
            out[target] = encoder.fit_transform(out[col].fillna("미상").astype(str))
            joblib.dump(encoder, path)
        else:
            encoder = joblib.load(path)
            values = out[col].fillna("미상").astype(str)
            known = set(encoder.classes_)
            out[target] = [int(encoder.transform([v])[0]) if v in known else 0 for v in values]
    out["building_age"] = 2026 - pd.to_numeric(out.get("build_year", 2000), errors="coerce").fillna(2000)
    for col in FEATURES:
        out[col] = pd.to_numeric(out.get(col, 0), errors="coerce").fillna(0)
    return out


def train(input_path: Path = PROCESSED_DIR / "jeonse_labeled.csv", output_dir: Path = MODEL_DIR) -> dict:
    try:
        from pytorch_tabnet.tab_model import TabNetClassifier
        from sklearn.metrics import classification_report, roc_auc_score
        from sklearn.model_selection import train_test_split
    except ImportError as exc:
        raise ImportError("TabNet 학습에는 pytorch-tabnet과 scikit-learn이 필요합니다.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    df = prepare_features(df, fit=True).dropna(subset=FEATURES + ["is_anomaly"])
    if len(df) < 30:
        raise ValueError("TabNet 학습에는 최소 30건 이상의 라벨 데이터가 필요합니다.")
    x = df[FEATURES].to_numpy(dtype=np.float32)
    y = df["is_anomaly"].astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        raise ValueError("정상/이상 라벨이 한 종류뿐이라 분류 모델을 학습할 수 없습니다.")

    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42, stratify=y)
    model = TabNetClassifier(seed=42, n_d=32, n_a=32, n_steps=5, gamma=1.5, verbose=0)
    model.fit(
        x_train,
        y_train,
        eval_set=[(x_test, y_test)],
        eval_name=["valid"],
        eval_metric=["auc"],
        max_epochs=100,
        patience=20,
        batch_size=256,
        virtual_batch_size=128,
    )
    pred = model.predict(x_test)
    prob = model.predict_proba(x_test)[:, 1]
    metadata = {
        "model": "TabNetClassifier",
        "rows": int(len(df)),
        "anomaly_rate": round(float(y.mean()), 4),
        "auc": round(float(roc_auc_score(y_test, prob)), 4),
        "classification_report": classification_report(y_test, pred, output_dict=True, zero_division=0),
        "feature_importances": {
            feature: round(float(value), 6)
            for feature, value in zip(FEATURES, model.feature_importances_, strict=False)
        },
    }
    model.save_model(str(output_dir / "tabnet_anomaly"))
    (output_dir / "tabnet_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def predict_one(candidate: dict) -> dict:
    from pytorch_tabnet.tab_model import TabNetClassifier

    model = TabNetClassifier()
    model.load_model(str(MODEL_DIR / "tabnet_anomaly.zip"))
    row = prepare_features(pd.DataFrame([candidate]), fit=False)
    prob = float(model.predict_proba(row[FEATURES].to_numpy(dtype=np.float32))[0][1])
    return {
        "is_anomaly": bool(prob >= 0.5),
        "anomaly_probability": round(prob, 4),
        "risk_level": "위험" if prob >= 0.7 else "주의" if prob >= 0.4 else "보통",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=PROCESSED_DIR / "jeonse_labeled.csv")
    args = parser.parse_args()
    print(json.dumps(train(args.input), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

