"""Compute pairwise agreement for independently annotated CSV records."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def cohens_kappa(first: list[str], second: list[str]) -> float | None:
    pairs = [(a, b) for a, b in zip(first, second) if a and b and a != "not_collected" and b != "not_collected"]
    if not pairs:
        return None
    categories = sorted(set(value for pair in pairs for value in pair))
    total = len(pairs)
    observed = sum(a == b for a, b in pairs) / total
    first_counts = Counter(a for a, _ in pairs)
    second_counts = Counter(b for _, b in pairs)
    expected = sum(first_counts[c] * second_counts[c] for c in categories) / (total * total)
    return None if expected == 1 else (observed - expected) / (1 - expected)


def summarize(path: Path, first_column: str, second_column: str) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    first = [row.get(first_column, "").strip() for row in rows]
    second = [row.get(second_column, "").strip() for row in rows]
    usable = [(a, b) for a, b in zip(first, second) if a and b and a != "not_collected" and b != "not_collected"]
    result: dict[str, object] = {"rows": len(rows), "usable_pairs": len(usable), "cohen_kappa": cohens_kappa(first, second)}
    result["agreement_count"] = sum(a == b for a, b in usable)
    result["label_pairs"] = dict(Counter(f"{a}|{b}" for a, b in usable))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--first", default="annotator_1_label")
    parser.add_argument("--second", default="annotator_2_label")
    args = parser.parse_args()
    print(summarize(args.csv_path, args.first, args.second))
