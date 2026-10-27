from __future__ import annotations

import argparse
from collections import defaultdict
import json
import sys

import numpy as np
import pandas as pd

from prepare_human_evidence import read_csv, write_csv, write_json
from public_reserve_validation import BASE_FEATURES, COUNTRIES, DATA, make_frame
from run_paired_services import PROJECT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    source = pd.read_csv(DATA / "time_series_15min_singleindex.csv", usecols=["utc_timestamp", *[country + "_load_actual_entsoe_transparency" for country in COUNTRIES]])
    references = read_csv(PROJECT / "results" / "public_validation_r1" / "main" / "window_results.csv")
    conditional = read_csv(PROJECT / "results" / "public_validation_r1" / "main" / "conditional_results.csv")
    rows = []
    for country in (["DE"] if args.smoke else COUNTRIES):
        frame = make_frame(source, country).dropna(subset=BASE_FEATURES + ["target"])
        for window in (range(1) if args.smoke else range(12)):
            test_start = pd.Timestamp("2019-01-01", tz="UTC") + pd.Timedelta(days=30 * window)
            cal_start = test_start - pd.Timedelta(days=30)
            training = frame[(frame["ts"] >= cal_start - pd.Timedelta(days=700)) & (frame["target_end"] < cal_start)]
            test = frame[(frame["ts"] >= test_start) & (frame["ts"] < test_start + pd.Timedelta(days=30))]
            cache = DATA / "prediction_cache" / f"{country}_w{window}_H60_cal30_K256_req0.95_ffull_cs20.npz"
            with np.load(cache) as saved:
                assert np.array_equal(saved["timestamps"], test["ts"].to_numpy(dtype="datetime64[ns]").astype("int64"))
                assert np.array_equal(saved["target"], test["target"].to_numpy())
                error = saved["target"] - saved["prediction"]
                pinball = np.maximum(0.95 * error, -0.05 * error)
                coverage = saved["target"] <= saved["Selected_shrinkage"]
            reference = next(row for row in references if row["country"] == country and int(row["window"]) == window and row["method"] == "Selected shrinkage")
            assert np.isclose(pinball.mean(), float(reference["predictor_pinball_loss"]), rtol=1e-12)
            groups = {"all": np.ones(len(test), dtype=bool), "high_observed_ramp": test["recent_ramp_max"].to_numpy() >= training["recent_ramp_max"].quantile(0.8)}
            groups.update({"season_" + season: test["season"].to_numpy() == season for season in ("winter", "spring", "summer", "autumn")})
            for regime, mask in groups.items():
                if not mask.any():
                    continue
                expected = next(row for row in conditional if row["country"] == country and int(row["window"]) == window and row["method"] == "Selected shrinkage" and row["regime"] == regime)
                assert int(mask.sum()) == int(expected["n"])
                assert np.isclose(coverage[mask].mean(), float(expected["coverage"]), rtol=1e-12)
                rows.append({"country": country, "window": window, "regime": regime, "n": int(mask.sum()),
                    "predictor_pinball_MW": float(pinball[mask].mean()), "calibrated_coverage": float(coverage[mask].mean())})
    output = PROJECT / "results" / "integrated_r1"
    if args.smoke:
        write_json(output / "conditional_prediction_smoke.json", {"passed": True, "rows": len(rows), "cache_and_existing_metrics_match": True})
    else:
        groups = defaultdict(list)
        for row in rows:
            groups[row["country"], row["regime"]].append(row)
        summaries = []
        for (country, regime), group in groups.items():
            count = sum(row["n"] for row in group)
            summaries.append({"country": country, "regime": regime, "n": count,
                **{metric: sum(row[metric] * row["n"] for row in group) / count for metric in ("predictor_pinball_MW", "calibrated_coverage")}})
        assert sum(row["n"] for row in summaries if row["regime"] == "all") == 138240
        assert all(np.isfinite(row["predictor_pinball_MW"]) for row in summaries)
        write_csv(output / "conditional_prediction_windows.csv", rows)
        write_csv(output / "conditional_prediction_summary.csv", summaries)
        write_json(output / "conditional_prediction_usability.json", {"passed": True, "windows": 48, "test_decisions": 138240,
            "cached_predictions_used": True, "training_rerun": False, "existing_regime_counts_and_coverages_match": True})
    print(json.dumps({"smoke": args.smoke, "rows": len(rows), "passed": True}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
