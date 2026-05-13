from __future__ import annotations

import argparse
import json
from pathlib import Path

from preprocess import PROCESSED_DIR, run as run_preprocess


def main() -> None:
    parser = argparse.ArgumentParser(description="Run preprocess, TabNet, and LSTM analysis.")
    parser.add_argument("--source", choices=["db", "csv"], default="db")
    parser.add_argument("--skip-tabnet", action="store_true")
    parser.add_argument("--skip-lstm", action="store_true")
    args = parser.parse_args()

    result = {"preprocess": run_preprocess(source=args.source)}

    if not args.skip_tabnet:
        from tabnet_model import train as train_tabnet

        result["tabnet"] = train_tabnet(PROCESSED_DIR / "jeonse_labeled.csv")

    if not args.skip_lstm:
        from lstm_model import train as train_lstm

        result["lstm"] = train_lstm(PROCESSED_DIR / "jeonse_monthly.csv")

    output_path = Path(__file__).resolve().parent / "artifacts" / "analysis_summary.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

