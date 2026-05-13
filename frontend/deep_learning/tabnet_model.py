from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import uuid
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
    "region_price",
    "sale_price",
    "region_count",
    "sale_count",
    "is_sale_price_available",
]
# 모델 학습 누수를 줄이기 위해 정답 라벨 계산에 직접 쓰인 파생 변수는 제외합니다.
LEAKED_FEATURES = ["z_score", "jeonse_ratio", "q25", "q75"]


def _save_tabnet_model_zip(model, output_dir: Path) -> Path:
    from pytorch_tabnet.utils import ComplexEncoder
    import torch

    # pytorch-tabnet의 기본 save_model은 Windows에서 임시 폴더 삭제 실패가 날 수 있어 직접 zip을 만듭니다.
    temp_parent = Path(os.getenv("TABNET_TEMP_DIR", output_dir / "tmp"))
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tabnet_anomaly_", dir=temp_parent, ignore_cleanup_errors=True) as temp_root:
        temp_model_dir = Path(temp_root) / "tabnet_anomaly"
        temp_model_dir.mkdir(parents=True, exist_ok=True)
        saved_params = {"init_params": {}, "class_attrs": {"preds_mapper": model.preds_mapper}}
        for key, value in model.get_params().items():
            if not isinstance(value, type):
                saved_params["init_params"][key] = value
        (temp_model_dir / "model_params.json").write_text(json.dumps(saved_params, cls=ComplexEncoder), encoding="utf8")
        torch.save(model.network.state_dict(), temp_model_dir / "network.pt")
        staged_zip = Path(shutil.make_archive(str(Path(temp_root) / "tabnet_anomaly"), "zip", temp_model_dir))
        target_zip = output_dir / "tabnet_anomaly.zip"
        try:
            staged_zip.replace(target_zip)
        except PermissionError:
            target_zip = output_dir / f"tabnet_anomaly_{uuid.uuid4().hex}.zip"
            staged_zip.replace(target_zip)
    _cleanup_stale_tabnet_models(output_dir, keep_path=target_zip)
    return target_zip


def _cleanup_stale_tabnet_models(output_dir: Path, keep_path: Path) -> None:
    # 테스트를 반복해도 TabNet 모델 zip/임시 폴더가 무한히 쌓이지 않도록 최신 산출물만 남깁니다.
    for path in output_dir.glob("tabnet_anomaly_*.zip"):
        if path != keep_path:
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                continue
    for path in output_dir.glob("tabnet_anomaly_*"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def _latest_tabnet_model_path() -> Path:
    # 고정 파일명이 잠긴 경우를 대비해 버전별 zip 중 가장 최신 모델을 사용합니다.
    candidates = list(MODEL_DIR.glob("tabnet_anomaly_*.zip"))
    if candidates:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    return MODEL_DIR / "tabnet_anomaly.zip"


def prepare_features(df: pd.DataFrame, fit: bool = True, save_encoders: bool = True) -> pd.DataFrame:
    from sklearn.preprocessing import LabelEncoder

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for col, target in [("housing_type", "housing_type_enc"), ("dong_name", "dong_name_enc")]:
        path = MODEL_DIR / f"{col}_label_encoder.pkl"
        if fit:
            encoder = LabelEncoder()
            out[target] = encoder.fit_transform(out[col].fillna("unknown").astype(str))
            if save_encoders:
                # 테스트 실행에서는 인코더 파일 저장을 끄고, 실제 추론 재사용 시에만 저장합니다.
                joblib.dump(encoder, path)
        else:
            encoder = joblib.load(path)
            values = out[col].fillna("unknown").astype(str)
            known = set(encoder.classes_)
            out[target] = [int(encoder.transform([v])[0]) if v in known else 0 for v in values]
    out["building_age"] = pd.Timestamp.today().year - pd.to_numeric(out.get("build_year", 2000), errors="coerce").fillna(2000)
    out["is_sale_price_available"] = pd.to_numeric(out.get("sale_price", np.nan), errors="coerce").notna().astype(int)
    for col in FEATURES:
        out[col] = pd.to_numeric(out.get(col, 0), errors="coerce").fillna(0)
    return out


def train(input_path: Path = PROCESSED_DIR / "jeonse_labeled.csv", output_dir: Path = MODEL_DIR, save_artifacts: bool = True) -> dict:
    try:
        from pytorch_tabnet.tab_model import TabNetClassifier
        from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
        from sklearn.model_selection import train_test_split
    except ImportError as exc:
        raise ImportError("TabNet training requires pytorch-tabnet and scikit-learn.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    df = prepare_features(df, fit=True, save_encoders=save_artifacts).dropna(subset=FEATURES + ["is_anomaly"])
    if len(df) < 30:
        raise ValueError("TabNet training requires at least 30 labeled rows.")
    x = df[FEATURES].to_numpy(dtype=np.float32)
    y = df["is_anomaly"].astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        raise ValueError("Both normal and anomaly labels are required for classification training.")

    split_strategy = "random_stratified"
    if "contract_month" in df.columns:
        months = np.asarray(sorted(df["contract_month"].dropna().unique()))
        if len(months) >= 5:
            cutoff = months[max(1, int(len(months) * 0.8))]
            train_mask = (df["contract_month"] < cutoff).to_numpy()
            test_mask = (df["contract_month"] >= cutoff).to_numpy()
            if train_mask.any() and test_mask.any() and len(np.unique(y[train_mask])) == 2 and len(np.unique(y[test_mask])) == 2:
                x_train, x_test = x[train_mask], x[test_mask]
                y_train, y_test = y[train_mask], y[test_mask]
                split_strategy = "time_holdout_latest_20pct_months"
            else:
                x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42, stratify=y)
        else:
            x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42, stratify=y)
    else:
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
        "split_strategy": split_strategy,
        "features": FEATURES,
        "excluded_leaked_features": LEAKED_FEATURES,
        "auc": round(float(roc_auc_score(y_test, prob)), 4),
        "classification_report": classification_report(y_test, pred, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y_test, pred).tolist(),
        "feature_importances": {
            feature: round(float(value), 6)
            for feature, value in zip(FEATURES, model.feature_importances_, strict=False)
        },
    }
    if save_artifacts:
        # 저장 모드에서만 추론 재사용을 위한 모델 zip과 메타데이터를 남깁니다.
        model_path = _save_tabnet_model_zip(model, output_dir)
        metadata["model_path"] = str(model_path)
        (output_dir / "tabnet_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        metadata["model_path"] = None
    return metadata


def predict_one(candidate: dict) -> dict:
    from pytorch_tabnet.tab_model import TabNetClassifier

    model = TabNetClassifier()
    model.load_model(str(_latest_tabnet_model_path()))
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

