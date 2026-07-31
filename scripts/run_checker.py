from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ask.checker import run_checker
from ask.scoring import write_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic ASK checker on a saved JSONL response file.")
    parser.add_argument("--service", choices=["deepseek", "qwen", "ernie", "hunyuan"], required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    args = parser.parse_args()
    labels = ROOT / "data" / "llm" / "case_labels_blind.csv"
    if not labels.exists():
        raise SystemExit(f"Missing labels: {labels}")
    if not args.outputs.exists():
        raise SystemExit(f"Missing outputs: {args.outputs}")
    out_dir = args.outputs.parent
    rows = run_checker(labels, args.outputs, out_dir / "checker_results.csv", out_dir / "audit_logs", args.service)
    summary = write_summary(rows, out_dir / "checker_summary.csv", out_dir / "checker_summary.json")
    print(f"Checked {summary['n_cases']} cases; wrote results beside {args.outputs}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
