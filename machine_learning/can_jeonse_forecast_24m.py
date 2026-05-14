from __future__ import annotations

import argparse
from pathlib import Path

from can_jeonse_forecast import ARTIFACT_DIR, DATA_DIR, run_single_horizon

HORIZON = 24


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate the 24-month can-jeonse forecast model.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACT_DIR)
    args = parser.parse_args()
    run_single_horizon(HORIZON, args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
