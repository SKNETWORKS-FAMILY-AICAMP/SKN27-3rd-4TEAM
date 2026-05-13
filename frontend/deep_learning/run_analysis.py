from __future__ import annotations

import argparse
import json
from pathlib import Path

from preprocess import PROCESSED_DIR, run as run_preprocess


def main() -> None:
    # 딥러닝 전처리, TabNet, LSTM 분석을 한 번에 실행하는 CLI입니다.
    parser = argparse.ArgumentParser(description="Run preprocess, TabNet, and LSTM analysis.")
    parser.add_argument("--source", choices=["db", "csv"], default="db")
    parser.add_argument("--skip-tabnet", action="store_true")
    parser.add_argument("--skip-lstm", action="store_true")
    parser.add_argument("--no-save-artifacts", action="store_true", help="학습 결과 파일을 저장하지 않고 지표만 출력합니다.")
    args = parser.parse_args()

    result = {"preprocess": run_preprocess(source=args.source)}

    if not args.skip_tabnet:
        try:
            # TabNet 의존성이 없는 로컬 환경에서도 전처리/RAG 검증이 끊기지 않게 결과에 오류를 남깁니다.
            from tabnet_model import train as train_tabnet

            result["tabnet"] = train_tabnet(PROCESSED_DIR / "jeonse_labeled.csv", save_artifacts=not args.no_save_artifacts)
        except (ImportError, ValueError) as exc:
            result["tabnet"] = {"status": "skipped", "reason": str(exc)}

    if not args.skip_lstm:
        try:
            # LSTM 의존성이 없는 로컬 환경에서도 분석 결과를 반환할 수 있게 처리합니다.
            from lstm_model import train as train_lstm

            result["lstm"] = train_lstm(PROCESSED_DIR / "jeonse_monthly.csv", save_artifacts=not args.no_save_artifacts)
        except (ImportError, ValueError) as exc:
            result["lstm"] = {"status": "skipped", "reason": str(exc)}

    output_path = Path(__file__).resolve().parent / "artifacts" / "analysis_summary.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.no_save_artifacts:
        # 저장 모드에서만 분석 요약 파일을 남겨 추후 결과 확인에 사용합니다.
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
