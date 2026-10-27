from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from prepare_human_evidence import write_csv, write_json
from public_reserve_validation import COUNTRIES, evaluate_window, make_frame, metrics
from workspace_paths import PROJECT


DATA = PROJECT / "data" / "evidence_completion_20261011"
RESULTS = PROJECT / "results" / "evidence_completion_20261011"
PUBLIC = PROJECT / "data" / "public_validation_r1"
METHOD_KEYS = {"Static quantile": "Static_quantile", "Quantile predictor": "Quantile_predictor",
               "Global calibration": "Global_calibration", "Local calibration": "Local_calibration",
               "Selected shrinkage": "Selected_shrinkage", "Block-score calibration": "Block_score_calibration",
               "Scenario quantile": "Scenario_quantile", "Scenario maximum": "Scenario_maximum"}


def benchmark_margins() -> tuple[list[dict], list[dict]]:
    original = pd.read_csv(PROJECT / "results" / "public_validation_r1" / "main" / "window_results.csv")
    margins, frontiers = [], []
    for country in COUNTRIES:
        gaps = []
        for window in range(12):
            path = PUBLIC / "prediction_cache" / f"{country}_w{window}_H60_cal30_K256_req0.95_ffull_cs20.npz"
            arrays = np.load(path)
            target = arrays["target"]
            subset = original[(original["country"] == country) & (original["window"] == window)]
            reference = subset.iloc[0]
            scale = float((reference["mean_reserve_MW"] + 20 * reference["mean_shortfall_MW"]) / reference["normalized_cost"])
            for method, key in METHOD_KEYS.items():
                reserve = arrays[key]
                for required in (0.95, 0.975, 0.99):
                    correction = float(np.quantile(target - reserve, required, method="higher"))
                    adjusted = np.maximum(reserve + correction, 0)
                    row = {"country": country, "window": window, "method": method,
                           "required_coverage": required, "empirical_offset_MW": correction,
                           "interpretation": "retrospective equal-coverage sensitivity", **metrics(target, adjusted, scale)}
                    frontiers.append(row)
                    if required == 0.95:
                        gaps.append(max(0, correction / scale))
        margins.append({"country": country, "benchmark_windows": 12, "required_coverage": 0.95,
                        "common_margin_load_fraction": max(gaps),
                        "margin_definition": "largest nonnegative 95th-percentile residual correction over all eight methods and 12 benchmark windows",
                        "first_new_test_start": "2020-01-01", "new_test_windows": 8})
    return margins, frontiers


def join_weather(frame: pd.DataFrame) -> pd.DataFrame:
    observations = pd.read_csv(DATA / "weather" / "station_observations.csv", dtype={"station": str}, parse_dates=["ts"])
    count = observations["station"].nunique()
    if count != 6:
        raise ValueError("Six geographically distributed stations are required")
    weather = observations.groupby("ts").agg(temperature_C=("temperature_C", "mean"),
                                            humidity_percent=("relative_humidity_percent", "mean"),
                                            temperature_count=("temperature_C", "count"),
                                            humidity_count=("relative_humidity_percent", "count")).reset_index()
    weather = weather[(weather["temperature_count"] == count) & (weather["humidity_count"] == count)]
    weather["available_at"] = weather["ts"] + pd.Timedelta(hours=1)
    weather = weather.rename(columns={"temperature_C": "distributed_temperature_C", "humidity_percent": "distributed_humidity_percent"})
    joined = pd.merge_asof(frame.sort_values("ts"), weather.sort_values("available_at"),
                          left_on="ts", right_on="available_at", direction="backward", tolerance=pd.Timedelta(minutes=59))
    joined = joined.rename(columns={"ts_x": "ts", "ts_y": "weather_observation_time"})
    finite = joined["distributed_temperature_C"].notna()
    if not (joined.loc[finite, "weather_observation_time"] < joined.loc[finite, "ts"]).all():
        raise AssertionError("Weather observation exceeds the decision-time information boundary")
    return joined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--phase", choices=("reliability", "weather"), required=True)
    args = parser.parse_args()
    output = RESULTS / args.phase / ("smoke" if args.smoke else "main")
    output.mkdir(parents=True, exist_ok=True)
    margins, frontiers = benchmark_margins()
    if args.phase == "reliability":
        write_csv(RESULTS / "reliability" / "benchmark_margins.csv", margins)
        write_csv(RESULTS / "reliability" / "equal_coverage_frontier.csv", frontiers)
    protocol = DATA / (args.phase + "_protocol.json")
    if not protocol.exists():
        write_json(protocol, {"frozen_at": datetime.now(timezone.utc).isoformat(), "phase": args.phase,
                              "required_coverage": 0.95, "first_test_start": "2020-01-01",
                              "windows": 8, "method_count": 8, "countries": list(COUNTRIES) if args.phase == "reliability" else ["DE"],
                              "common_margin": margins, "margins_use_2019_benchmark_only": True,
                              "test_outcomes_used_for_selection": False,
                              "weather_features": "equal-weight observed air temperature and humidity over six official DWD stations",
                              "source_sha256": hashlib.sha256((PUBLIC / "time_series_15min_singleindex.csv").read_bytes()).hexdigest()})
    if not args.smoke and not (RESULTS / args.phase / "smoke" / "usability.json").exists():
        raise ValueError("A successful smoke test is required")
    countries = ["DE"] if args.smoke or args.phase == "weather" else list(COUNTRIES)
    source = pd.read_csv(PUBLIC / "time_series_15min_singleindex.csv",
                         usecols=["utc_timestamp"] + [country + "_load_actual_entsoe_transparency" for country in countries])
    frames = {country: make_frame(source, country) for country in countries}
    if args.phase == "weather":
        frames["DE"] = join_weather(frames["DE"]).dropna(subset=["distributed_temperature_C", "distributed_humidity_percent"])
    windows = [0] if args.smoke else list(range(8))
    variants = ["load_calendar"] if args.phase == "reliability" else ["load_calendar", "distributed_weather"]
    tasks = [(country, window, variant) for country in countries for window in windows for variant in variants]
    rows, conditions = [], []
    def run(task):
        country, window, variant = task
        extras = ["distributed_temperature_C", "distributed_humidity_percent"] if variant == "distributed_weather" else []
        cache = DATA / "prediction_cache" / args.phase / ("smoke" if args.smoke else "main") / variant
        new_rows, new_conditions, diagnostic = evaluate_window(frames[country], country, window,
            first_test_start="2020-01-01", additional_features=extras, cache_root=cache)
        arrays = np.load(cache / f"{country}_w{window}_H60_cal30_K256_req0.95_ffull_cs20.npz")
        scale = float(arrays["load_scale"])
        common_margin = next(row["common_margin_load_fraction"] for row in margins if row["country"] == country) * scale
        final = []
        for row in new_rows:
            reserve = arrays[METHOD_KEYS[row["method"]]]
            final.append({**row, "input_variant": variant, "common_margin_MW": 0.0, "margin_applied": False})
            if args.phase == "reliability":
                final.append({**row, **metrics(arrays["target"], reserve + common_margin, scale),
                              "input_variant": variant, "common_margin_MW": common_margin, "margin_applied": True})
        return final, [{**row, "input_variant": variant} for row in new_conditions], diagnostic
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(run, task): task for task in tasks}
        for future in as_completed(pending):
            new_rows, new_conditions, diagnostic = future.result()
            rows.extend(new_rows)
            conditions.extend(new_conditions)
            print(json.dumps({"task": pending[future], "temporal_purging": diagnostic["purged_boundaries_passed"],
                              "test_n": diagnostic["test_n"]}), flush=True)
    rows.sort(key=lambda row: (row["country"], row["window"], row["input_variant"], row["margin_applied"], row["method"]))
    write_csv(output / "window_results.csv", rows)
    write_csv(output / "conditional_results.csv", conditions)
    summary = []
    frame = pd.DataFrame(rows)
    for keys, subset in frame.groupby(["country", "input_variant", "margin_applied", "method"]):
        country, variant, applied, method = keys
        summary.append({"country": country, "input_variant": variant, "margin_applied": bool(applied), "method": method,
                        "windows": len(subset), "decisions": int(subset["n"].sum()),
                        "windows_meeting_coverage": int((subset["coverage"] >= .95).sum()),
                        "minimum_window_coverage": float(subset["coverage"].min()),
                        **{metric: float(subset[metric].mean()) for metric in
                           ("coverage", "normalized_cost", "mean_reserve_MW", "mean_shortfall_MW", "shortfall_CVaR95_MW", "predictor_pinball_loss")}})
    write_csv(output / "summary.csv", summary)
    usable = all(np.isfinite(row["normalized_cost"]) and row["selection_coverage"] >= .95 for row in rows)
    if not usable:
        raise ValueError("Non-finite results or selection reliability violation")
    write_json(output / "usability.json", {"passed": True, "test_outcomes_used_for_selection": False,
                                           "all_completed_results_retained": True, "tasks": len(tasks),
                                           "physical_units": "MW", "rows": len(rows)})
    print(json.dumps({"phase": args.phase, "smoke": args.smoke, "rows": len(rows), "output": str(output)}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
