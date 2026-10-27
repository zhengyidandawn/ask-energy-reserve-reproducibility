"""Screen policies before equal-service cost comparisons."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def screen(path: Path, target: float) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        policy = row.get("policy", "").strip()
        if not policy or not row.get("coverage"):
            raise ValueError("policy and coverage are required for every row")
        grouped[policy].append(row)
    results = []
    expected_windows = {len(items) for items in grouped.values()}
    if len(expected_windows) > 1:
        raise ValueError("policies do not use the same number of windows")
    for policy, items in sorted(grouped.items()):
        coverage = sum(float(item["coverage"]) for item in items) / len(items)
        results.append({"policy": policy, "windows": len(items), "coverage": coverage, "eligible": coverage >= target})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--target", type=float, default=0.95)
    args = parser.parse_args()
    for result in screen(args.csv_path, args.target):
        print(result)
