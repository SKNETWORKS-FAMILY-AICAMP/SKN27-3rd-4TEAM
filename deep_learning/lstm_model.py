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
LOOKBACK = 12
FORECAST_MONTHS = 24
MIN_MONTHS = LOOKBACK + 6


def _model_key(row: pd.Series | dict) -> str:
    parts = [row.get("sido", "미상"), row.get("sigungu", "미상"), row.get("dong_name", "미상"), row.get("housing_type", "미상"), row.get("area_bucket", "미상")]
    return "_".join(str(p).replace(" ", "") for p in parts)


def make_sequences(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x, y = [], []
    for idx in range(LOOKBACK, len(values)):
        x.append(values[idx - LOOKBACK : idx])
        y.append(values[idx])
    return np.asarray(x), np.asarray(y)


def build_model(hidden: int = 64):
    import torch.nn as nn

    class LSTMRegressor(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(input_size=1, hidden_size=hidden, num_layers=2, dropout=0.2, batch_first=True)
            self.head = nn.Sequential(nn.Linear(hidden, 32), nn.ReLU(), nn.Linear(32, 1))

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :])

    return LSTMRegressor()


def train(input_path: Path = PROCESSED_DIR / "jeonse_monthly.csv", output_dir: Path = MODEL_DIR) -> dict:
    try:
        import torch
        import torch.nn as nn
        from sklearn.metrics import mean_absolute_error, mean_squared_error
        from sklearn.preprocessing import MinMaxScaler
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        raise ImportError("LSTM 학습에는 torch와 scikit-learn이 필요합니다.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    group_cols = ["sido", "sigungu", "dong_name", "housing_type", "area_bucket"]
    results, skipped = {}, {}

    for keys, group in df.groupby(group_cols, dropna=False):
        group = group.sort_values("contract_month")
        key_data = dict(zip(group_cols, keys, strict=False))
        key = _model_key(key_data)
        values = group["median_deposit_per_pyeong"].astype(float).interpolate().ffill().bfill().to_numpy().reshape(-1, 1)
        if len(values) < MIN_MONTHS:
            skipped[key] = f"{len(values)}개월: 최소 {MIN_MONTHS}개월 필요"
            continue

        scaler = MinMaxScaler()
        scaled = scaler.fit_transform(values).flatten()
        x, y = make_sequences(scaled)
        split = max(1, int(len(x) * 0.8))
        x_train = torch.FloatTensor(x[:split]).unsqueeze(-1)
        y_train = torch.FloatTensor(y[:split]).unsqueeze(-1)
        x_test = torch.FloatTensor(x[split:]).unsqueeze(-1)
        y_test = torch.FloatTensor(y[split:]).unsqueeze(-1)
        loader = DataLoader(TensorDataset(x_train, y_train), batch_size=16, shuffle=True)
        model = build_model()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        criterion = nn.MSELoss()
        best_state, best_loss, patience = model.state_dict(), float("inf"), 0

        for _ in range(120):
            model.train()
            epoch_loss = 0.0
            for xb, yb in loader:
                optimizer.zero_grad()
                loss = criterion(model(xb), yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                epoch_loss += float(loss.item())
            avg_loss = epoch_loss / max(len(loader), 1)
            if avg_loss < best_loss:
                best_loss = avg_loss
                best_state = {name: tensor.detach().clone() for name, tensor in model.state_dict().items()}
                patience = 0
            else:
                patience += 1
                if patience >= 15:
                    break

        model.load_state_dict(best_state)
        model.eval()
        with torch.no_grad():
            if len(x_test):
                pred = scaler.inverse_transform(model(x_test).numpy()).flatten()
                actual = scaler.inverse_transform(y_test.numpy()).flatten()
                mae = float(mean_absolute_error(actual, pred))
                rmse = float(np.sqrt(mean_squared_error(actual, pred)))
            else:
                mae = rmse = 0.0
        torch.save(best_state, output_dir / f"lstm_{key}.pt")
        joblib.dump(scaler, output_dir / f"lstm_scaler_{key}.pkl")
        results[key] = {"mae": round(mae, 2), "rmse": round(rmse, 2), "months": int(len(values)), **key_data}

    summary = {"trained_models": results, "skipped": skipped}
    (output_dir / "lstm_metadata.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def forecast(key_data: dict, recent_values: list[float], months: int = FORECAST_MONTHS) -> dict:
    import torch

    key = _model_key(key_data)
    scaler = joblib.load(MODEL_DIR / f"lstm_scaler_{key}.pkl")
    model = build_model()
    model.load_state_dict(torch.load(MODEL_DIR / f"lstm_{key}.pt", map_location="cpu"))
    model.eval()
    scaled = list(scaler.transform(np.asarray(recent_values[-LOOKBACK:], dtype=float).reshape(-1, 1)).flatten())
    predictions = []
    with torch.no_grad():
        for _ in range(months):
            x = torch.FloatTensor(scaled[-LOOKBACK:]).reshape(1, LOOKBACK, 1)
            pred_scaled = float(model(x).numpy()[0][0])
            scaled.append(pred_scaled)
            predictions.append(float(scaler.inverse_transform([[pred_scaled]])[0][0]))
    current, final = float(recent_values[-1]), float(predictions[-1])
    change_rate = (final - current) / current * 100 if current else 0
    return {
        "current_per_pyeong": round(current, 2),
        "predicted_24m_per_pyeong": round(final, 2),
        "change_rate": round(change_rate, 2),
        "trend": "상승" if change_rate > 5 else "하락" if change_rate < -5 else "보합",
        "risk_signal": "주의" if change_rate < -10 else "보통",
        "monthly_forecast": [round(v, 2) for v in predictions],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=PROCESSED_DIR / "jeonse_monthly.csv")
    args = parser.parse_args()
    print(json.dumps(train(args.input), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
