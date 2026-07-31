from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    llm = read_rows(ROOT / "results" / "llm" / "blind_summary.csv")
    assert {row["backend_key"] for row in llm} == {"deepseek", "qwen", "ernie", "hunyuan"}
    assert {int(row["n_cases"]) for row in llm} == {200}
    joint = [float(row["task_success_rate"]) for row in llm]
    assert min(joint) >= 0.705 and max(joint) <= 0.885

    public = read_rows(ROOT / "results" / "public_four_region" / "region_summary.csv")
    assert {row["region_id"] for row in public} == {"ERCO", "CISO", "ISNE", "MISO"}
    assert all(row["rank"] == "1" for row in public if row["method"] == "lgbm_adaptive_local_conformal")

    paired = read_rows(ROOT / "results" / "holdout" / "paired_governance_tests.csv")
    unsafe = next(row for row in paired if row["outcome"] == "unsafe_execution")
    assert unsafe["v1_0_rate"] == "0.205" and unsafe["v1_1_rate"] == "0.0"
    assert float(unsafe["exact_mcnemar_p"]) < 1e-10

    print("Frozen claims verified:")
    print(f"  blind joint-success range: {min(joint):.3f}-{max(joint):.3f} across four services")
    print("  adaptive local conformal ranks first in all four public regions")
    print("  unsafe execution: 0.205 -> 0.000; exact McNemar p < 1e-10")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
