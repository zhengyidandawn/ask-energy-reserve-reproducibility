from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import public_config as cfg
from src.minimal_validation import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the minimal public four-region reserve validation.")
    parser.add_argument("--input-dir", type=Path, default=cfg.HOURLY_DIR)
    parser.add_argument("--output-dir", type=Path, default=cfg.GENERATED_RESULTS_DIR)
    parser.add_argument("--regions", nargs="+", choices=sorted(cfg.PUBLIC_REGIONS), default=sorted(cfg.PUBLIC_REGIONS))
    parser.add_argument("--max-windows", type=int, default=0)
    args = parser.parse_args()
    run(args.input_dir, args.output_dir, args.regions, args.max_windows)
    print(f"Wrote generated public results under {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
