import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from prepare_human_evidence import write_csv, write_json
from public_reserve_validation import COUNTRIES, DATA, RESULTS, evaluate_window, make_frame


OUTPUT = RESULTS.parent / "strengthening_20261011"
FACTORS = (0.5, 1.0, 2.0)
WINDOWS = (0, 3, 6, 9)


def load_source() -> pd.DataFrame:
    columns = ["utc_timestamp"] + [country + "_load_actual_entsoe_transparency" for country in COUNTRIES]
    return pd.read_csv(DATA / "time_series_15min_singleindex.csv", usecols=columns)


def run(smoke: bool) -> list[dict]:
    source = load_source()
    frame = make_frame(source, "DE")
    factors = (1.0,) if smoke else FACTORS
    windows = (0,) if smoke else WINDOWS
    rows = []
    for factor in factors:
        for window in windows:
            result, _, diagnostic = evaluate_window(
                frame,
                "DE",
                window,
                neighbors=256,
                required=0.95,
                bandwidth_factor=factor,
            )
            selected = next(row for row in result if row["method"] == "Selected shrinkage")
            rows.append({
                "country": "DE",
                "window": window,
                "bandwidth_factor": factor,
                "method": selected["method"],
                "coverage": selected["coverage"],
                "normalized_cost": selected["normalized_cost"],
                "mean_reserve_MW": selected["mean_reserve_MW"],
                "mean_shortfall_MW": selected["mean_shortfall_MW"],
                "shortfall_CVaR95_MW": selected["shortfall_CVaR95_MW"],
                "selection_coverage": selected["selection_coverage"],
                "effective_sample_mean": selected["effective_sample_mean"],
                "effective_sample_min": selected["effective_sample_min"],
                "purged_boundaries_passed": diagnostic["purged_boundaries_passed"],
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = run(args.smoke)
    if args.smoke:
        assert len(rows) == 1
        assert all(np.isfinite(row["normalized_cost"]) for row in rows)
        assert all(row["selection_coverage"] >= 0.95 for row in rows)
        assert all(row["purged_boundaries_passed"] for row in rows)
        write_json(OUTPUT / "bandwidth_smoke.json", {
            "passed": True,
            "factors": [1.0],
            "windows": [0],
            "full_model_training": True,
        })
    else:
        smoke = OUTPUT / "bandwidth_smoke.json"
        if not smoke.exists():
            raise ValueError("A successful bandwidth smoke test is required")
        write_csv(OUTPUT / "bandwidth_sensitivity.csv", rows)
        summary = []
        for factor in FACTORS:
            subset = [row for row in rows if row["bandwidth_factor"] == factor]
            summary.append({
                "bandwidth_factor": factor,
                "windows": len(subset),
                "mean_coverage": float(np.mean([row["coverage"] for row in subset])),
                "mean_normalized_cost": float(np.mean([row["normalized_cost"] for row in subset])),
                "mean_reserve_MW": float(np.mean([row["mean_reserve_MW"] for row in subset])),
                "mean_shortfall_MW": float(np.mean([row["mean_shortfall_MW"] for row in subset])),
                "mean_effective_sample": float(np.mean([row["effective_sample_mean"] for row in subset])),
                "windows_meeting_test_coverage": sum(row["coverage"] >= 0.95 for row in subset),
            })
        write_csv(OUTPUT / "bandwidth_sensitivity_summary.csv", summary)
        write_json(OUTPUT / "bandwidth_usability.json", {
            "passed": True,
            "factors": list(FACTORS),
            "windows": list(WINDOWS),
            "all_finite": all(np.isfinite(row["normalized_cost"]) for row in rows),
            "all_selection_constraints_passed": all(row["selection_coverage"] >= 0.95 for row in rows),
            "all_temporal_purging_passed": all(row["purged_boundaries_passed"] for row in rows),
        })
    print(json.dumps({"smoke": args.smoke, "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
