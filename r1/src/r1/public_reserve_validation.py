from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from prepare_human_evidence import write_csv, write_json
from run_paired_services import PROJECT

DATA = PROJECT / "data" / "public_validation_r1"
RESULTS = PROJECT / "results" / "public_validation_r1"
COUNTRIES = {"DE": "Germany", "AT": "Austria", "BE": "Belgium", "NL": "Netherlands"}
BASE_FEATURES = ["load", "lag_1", "lag_4", "lag_12", "lag_96", "ramp_1", "ramp_4", "recent_ramp_max", "recent_load_mean", "recent_load_std", "hour_sin", "hour_cos", "dow_sin", "dow_cos"]
STATE_FEATURES = ["load", "ramp_1", "recent_ramp_max", "recent_load_std", "hour_sin", "hour_cos"]


def make_frame(source: pd.DataFrame, country: str, horizon: int = 60) -> pd.DataFrame:
    column = country + "_load_actual_entsoe_transparency"
    frame = pd.DataFrame({"ts": pd.to_datetime(source["utc_timestamp"], utc=True), "load": pd.to_numeric(source[column], errors="coerce")})
    frame = frame.sort_values("ts").drop_duplicates("ts", keep="last").set_index("ts")
    grid = pd.date_range(frame.index.min(), frame.index.max(), freq="15min", tz="UTC")
    frame = frame.reindex(grid).rename_axis("ts").reset_index()
    frame.loc[frame["load"] <= 0, "load"] = np.nan
    for lag in (1, 4, 12, 96):
        frame["lag_" + str(lag)] = frame["load"].shift(lag)
    frame["ramp_1"] = frame["load"].diff().clip(lower=0)
    frame["ramp_4"] = (frame["load"] - frame["load"].shift(4)).clip(lower=0)
    frame["recent_ramp_max"] = frame["ramp_1"].rolling(12, min_periods=12).max()
    frame["recent_load_mean"] = frame["load"].rolling(12, min_periods=12).mean()
    frame["recent_load_std"] = frame["load"].rolling(12, min_periods=12).std()
    clock = frame["ts"].dt.tz_convert("Europe/Berlin")
    hour = clock.dt.hour + clock.dt.minute / 60
    for name, position, period in (("hour", hour, 24), ("dow", clock.dt.dayofweek, 7)):
        frame[name + "_sin"] = np.sin(2 * np.pi * position / period)
        frame[name + "_cos"] = np.cos(2 * np.pi * position / period)
    month = clock.dt.month
    frame["season"] = np.select([month.isin([12, 1, 2]), month.isin([3, 4, 5]), month.isin([6, 7, 8])], ["winter", "spring", "summer"], default="autumn")
    steps = horizon // 15
    futures = pd.concat([frame["load"].shift(-offset) for offset in range(1, steps + 1)], axis=1)
    future_ramps = pd.concat([frame["load"].diff().shift(-offset) for offset in range(1, steps + 1)], axis=1)
    frame["target"] = future_ramps.clip(lower=0).max(axis=1)
    frame.loc[futures.isna().any(axis=1) | frame["load"].isna(), "target"] = np.nan
    frame["target_end"] = frame["ts"] + pd.Timedelta(minutes=horizon)
    return frame


def weighted_local(fit_state: np.ndarray, residual: np.ndarray, query_state: np.ndarray, probability: float, neighbors: int, bandwidth_factor: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    center, spread = fit_state.mean(axis=0), fit_state.std(axis=0)
    spread = np.where(spread > 1e-10, spread, 1.0)
    reference = (fit_state - center) / spread
    query = (query_state - center) / spread
    count = min(neighbors, len(reference))
    distance, indices = cKDTree(reference).query(query, k=count, workers=2)
    if count == 1:
        distance, indices = distance[:, None], indices[:, None]
    bandwidth = np.maximum(distance[:, -1] * bandwidth_factor, 1e-6)
    weights = np.exp(-(distance / bandwidth[:, None]) ** 2 / 2)
    values = residual[indices]
    order = np.argsort(values, axis=1)
    sorted_values = np.take_along_axis(values, order, axis=1)
    sorted_weights = np.take_along_axis(weights, order, axis=1)
    cumulative = np.cumsum(sorted_weights, axis=1)
    cut = probability * cumulative[:, -1]
    positions = np.argmax(cumulative >= cut[:, None], axis=1)
    offsets = sorted_values[np.arange(len(query)), positions]
    effective = weights.sum(axis=1) ** 2 / (weights**2).sum(axis=1)
    return offsets, effective


def metrics(target: np.ndarray, reserve: np.ndarray, load_scale: float, shortfall_cost: float = 20) -> dict:
    shortfall = np.maximum(target - reserve, 0)
    cost = reserve + shortfall_cost * shortfall
    ordered = np.sort(shortfall)[::-1]
    tail_mass = 0.05 * len(ordered)
    whole = int(np.floor(tail_mass))
    remainder = tail_mass - whole
    tail_sum = ordered[:whole].sum()
    if remainder > 0:
        tail_sum += remainder * ordered[whole]
    return {"coverage": float(np.mean(target <= reserve)), "mean_reserve_MW": float(reserve.mean()),
        "mean_shortfall_MW": float(shortfall.mean()), "shortfall_CVaR95_MW": float(tail_sum / tail_mass),
        "cost_index": float(cost.mean()), "normalized_cost": float(cost.mean() / load_scale), "n": len(target)}


def common_screen(proposals: dict[str, tuple[np.ndarray, np.ndarray]], selection_target: np.ndarray, required: float) -> tuple[dict[str, np.ndarray], dict]:
    final, selected = {}, {}
    for name, (selection, test) in proposals.items():
        correction = max(0.0, float(np.quantile(selection_target - selection, required, method="higher")))
        final[name] = np.maximum(test + correction, 0)
        selected[name] = {"additional_offset_MW": correction, "selection_coverage": float(np.mean(selection_target <= np.maximum(selection + correction, 0)))}
    return final, selected


def evaluate_window(frame: pd.DataFrame, country: str, window: int, horizon: int = 60, calibration_days: int = 30,
                    neighbors: int = 256, required: float = 0.95, feature_mode: str = "full", shortfall_cost: float = 20,
                    bandwidth_factor: float = 1.0, first_test_start: str = "2019-01-01",
                    additional_features: list[str] | None = None, cache_root: Path | None = None) -> tuple[list[dict], list[dict], dict]:
    test_start = pd.Timestamp(first_test_start, tz="UTC") + pd.Timedelta(days=30 * window)
    test_end = test_start + pd.Timedelta(days=30)
    cal_start = test_start - pd.Timedelta(days=calibration_days)
    selection_start = test_start - pd.Timedelta(days=10)
    train_start = cal_start - pd.Timedelta(days=700)
    extra_features = additional_features or []
    usable = frame.dropna(subset=BASE_FEATURES + extra_features + ["target"])
    training = usable[(usable["ts"] >= train_start) & (usable["target_end"] < cal_start)]
    calibration = usable[(usable["ts"] >= cal_start) & (usable["target_end"] < selection_start)]
    selection = usable[(usable["ts"] >= selection_start) & (usable["target_end"] < test_start)]
    test = usable[(usable["ts"] >= test_start) & (usable["ts"] < test_end)]
    if min(len(training), len(calibration), len(selection), len(test)) < 250:
        raise ValueError("Insufficient complete source observations in a temporal block")
    if not (training["target_end"].max() < calibration["ts"].min() and calibration["target_end"].max() < selection["ts"].min() and selection["target_end"].max() < test["ts"].min()):
        raise AssertionError("Overlapping target escaped temporal purging")
    features = BASE_FEATURES if feature_mode == "full" else ["load", "lag_1", "lag_4", "lag_96", "hour_sin", "hour_cos", "dow_sin", "dow_cos"]
    features = features + extra_features
    probability = 1 - 1 / shortfall_cost
    started = time.perf_counter()
    model = lgb.LGBMRegressor(objective="quantile", alpha=probability, n_estimators=220, learning_rate=0.04,
        num_leaves=63, min_child_samples=80, subsample=0.9, colsample_bytree=0.9,
        reg_lambda=1.0, random_state=20261010 + window, n_jobs=2, verbosity=-1)
    model.fit(training[features], training["target"])
    predictions = {name: model.predict(block[features]) for name, block in (("calibration", calibration), ("selection", selection), ("test", test))}
    fit_seconds = time.perf_counter() - started
    residual = calibration["target"].to_numpy() - predictions["calibration"]
    global_offset = float(np.quantile(residual, probability, method="higher"))
    query_selection = np.column_stack([selection[STATE_FEATURES].to_numpy(), predictions["selection"]])
    query_test = np.column_stack([test[STATE_FEATURES].to_numpy(), predictions["test"]])
    fit_state = np.column_stack([calibration[STATE_FEATURES].to_numpy(), predictions["calibration"]])
    local_selection, effective_selection = weighted_local(fit_state, residual, query_selection, probability, neighbors, bandwidth_factor)
    local_test, effective_test = weighted_local(fit_state, residual, query_test, probability, neighbors, bandwidth_factor)
    selection_target = selection["target"].to_numpy()
    candidates = {}
    for shrinkage in (0.0, 0.25, 0.5, 0.75, 1.0):
        candidate = np.maximum(predictions["selection"] + shrinkage * local_selection + (1 - shrinkage) * global_offset, 0)
        correction = max(0.0, float(np.quantile(selection_target - candidate, required, method="higher")))
        adjusted = candidate + correction
        candidates[shrinkage] = float(np.mean(adjusted + shortfall_cost * np.maximum(selection_target - adjusted, 0)))
    selected_shrinkage = min(candidates, key=candidates.get)
    adaptive_selection = predictions["selection"] + selected_shrinkage * local_selection + (1 - selected_shrinkage) * global_offset
    adaptive_test = predictions["test"] + selected_shrinkage * local_test + (1 - selected_shrinkage) * global_offset
    blocks = []
    timestamps_ns = calibration["ts"].to_numpy(dtype="datetime64[ns]").astype("int64")
    grouping = timestamps_ns // (horizon * 60 * 10**9)
    for group in np.unique(grouping):
        values = residual[grouping == group]
        if len(values) == horizon // 15:
            blocks.append(float(values.max()))
    if not blocks:
        raise ValueError("No complete horizon-length calibration block after temporal purging")
    block_offset = float(np.quantile(blocks, probability, method="higher"))
    load_cut = float(training["load"].quantile(0.8))
    ramp_cut = float(training["recent_ramp_max"].quantile(0.8))
    def states(block: pd.DataFrame) -> np.ndarray:
        return (block["load"].to_numpy() >= load_cut).astype(int) + 2 * (block["recent_ramp_max"].to_numpy() >= ramp_cut).astype(int)
    cal_states, selection_states, test_states = states(calibration), states(selection), states(test)
    robust_offsets = {}
    stochastic_offsets = {}
    for regime in range(4):
        pool = residual[cal_states == regime]
        if len(pool) < 41:
            pool = residual
        scenarios = np.quantile(pool, np.linspace(0.05, 0.95, 41))
        robust_offsets[regime] = float(scenarios.max())
        stochastic_offsets[regime] = float(np.quantile(scenarios, probability, method="higher"))
    static = float(np.quantile(calibration["target"], probability, method="higher"))
    proposals = {
        "Static quantile": (np.full(len(selection), static), np.full(len(test), static)),
        "Quantile predictor": (predictions["selection"], predictions["test"]),
        "Global calibration": (predictions["selection"] + global_offset, predictions["test"] + global_offset),
        "Local calibration": (predictions["selection"] + local_selection, predictions["test"] + local_test),
        "Selected shrinkage": (adaptive_selection, adaptive_test),
        "Block-score calibration": (predictions["selection"] + block_offset, predictions["test"] + block_offset),
        "Scenario quantile": (predictions["selection"] + np.array([stochastic_offsets[regime] for regime in selection_states]), predictions["test"] + np.array([stochastic_offsets[regime] for regime in test_states])),
        "Scenario maximum": (predictions["selection"] + np.array([robust_offsets[regime] for regime in selection_states]), predictions["test"] + np.array([robust_offsets[regime] for regime in test_states])),
    }
    final, selected = common_screen(proposals, selection_target, required)
    target = test["target"].to_numpy()
    scale = float(calibration["load"].mean())
    row_base = {"country": country, "country_name": COUNTRIES[country], "window": window, "test_start": str(test_start),
        "horizon_minutes": horizon, "calibration_days": calibration_days, "neighbors": neighbors,
        "required_coverage": required, "feature_mode": feature_mode, "shortfall_cost": shortfall_cost, "bandwidth_factor": bandwidth_factor}
    rows, conditional = [], []
    for method, reserve in final.items():
        row = {**row_base, "method": method, **metrics(target, reserve, scale, shortfall_cost),
            "selection_coverage": selected[method]["selection_coverage"], "additional_offset_MW": selected[method]["additional_offset_MW"],
            "predictor_pinball_loss": float(np.mean(np.maximum(probability * (target - predictions["test"]), (probability - 1) * (target - predictions["test"])))),
            "effective_sample_mean": float(effective_test.mean()), "effective_sample_min": float(effective_test.min()),
            "selected_shrinkage": selected_shrinkage, "base_fit_seconds": fit_seconds}
        rows.append(row)
        groups = {"all": np.ones(len(test), dtype=bool), "high_observed_ramp": test["recent_ramp_max"].to_numpy() >= ramp_cut,
            "high_load": test["load"].to_numpy() >= load_cut}
        groups.update({"season_" + season: test["season"].to_numpy() == season for season in ("winter", "spring", "summer", "autumn")})
        for name, mask in groups.items():
            if mask.sum():
                conditional.append({**row_base, "method": method, "regime": name, **metrics(target[mask], reserve[mask], scale, shortfall_cost)})
    suffix = "" if bandwidth_factor == 1.0 else f"_bw{bandwidth_factor}"
    cache = (cache_root or DATA / "prediction_cache") / f"{country}_w{window}_H{horizon}_cal{calibration_days}_K{neighbors}_req{required}_f{feature_mode}_cs{shortfall_cost}{suffix}.npz"
    cache.parent.mkdir(parents=True, exist_ok=True)
    arrays = {"timestamps": test["ts"].to_numpy(dtype="datetime64[ns]").astype("int64"), "target": target,
              "prediction": predictions["test"],
              **{name.replace(" ", "_").replace("-", "_"): reserve for name, reserve in final.items()}}
    if cache_root is not None:
        arrays.update({"load_scale": np.array(scale), "selection_target": selection_target,
                       "selection_timestamps": selection["ts"].to_numpy(dtype="datetime64[ns]").astype("int64"),
                       "features": np.array(features)})
    np.savez_compressed(cache, **arrays)
    dependence = {"country": country, "window": window, "horizon_minutes": horizon,
        "target_autocorrelation_lag1": float(pd.Series(target).autocorr(1)),
        "residual_autocorrelation_lag1": float(pd.Series(residual).autocorr(1)),
        "calibration_n": len(calibration), "selection_n": len(selection), "test_n": len(test),
        "block_scores_n": len(blocks), "effective_sample_mean": float(effective_test.mean()),
        "purged_boundaries_passed": True}
    return rows, conditional, dependence


def summarize(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[(row["country"], row["method"])].append(row)
    output = []
    generator = np.random.default_rng(20261010)
    for (country, method), subset in sorted(groups.items()):
        costs = np.array([row["normalized_cost"] for row in subset])
        samples = costs[generator.integers(0, len(costs), size=(3000, len(costs)))].mean(axis=1)
        record = {"country": country, "country_name": COUNTRIES[country], "method": method, "n_windows": len(subset),
            "cost_ci_low": float(np.quantile(samples, 0.025)), "cost_ci_high": float(np.quantile(samples, 0.975))}
        for metric in ("coverage", "mean_reserve_MW", "mean_shortfall_MW", "shortfall_CVaR95_MW", "normalized_cost", "predictor_pinball_loss", "selection_coverage"):
            record[metric] = float(np.mean([row[metric] for row in subset]))
        record["windows_meeting_coverage"] = sum(row["coverage"] >= 0.95 for row in subset)
        record["mean_coverage_feasible"] = record["coverage"] >= 0.95
        output.append(record)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    columns = ["utc_timestamp"] + [country + "_load_actual_entsoe_transparency" for country in COUNTRIES]
    source = pd.read_csv(DATA / "time_series_15min_singleindex.csv", usecols=columns)
    protocol_path = DATA / "numerical_protocol_v2.json"
    if not protocol_path.exists():
        write_json(protocol_path, {"frozen_at": datetime.now(timezone.utc).isoformat(), "countries": COUNTRIES,
            "n_windows": 12, "step_days": 30, "first_test_start": "2019-01-01T00:00:00Z", "test_days": 30,
            "training_days": 700, "calibration_days": 30, "selection_days_within_calibration": 10,
            "horizon_minutes": 60, "target": "maximum positive one-step load increment over future horizon, manuscript equation 1", "cost_reserve": 1, "cost_shortfall": 20, "common_selection_coverage": 0.95,
            "all_future_target_end_times_purged_at_block_boundaries": True, "missing_data_policy": "exclude incomplete input or target rows; no imputation",
            "model": "LightGBM quantile regression, 220 iterations, 63 leaves, learning rate 0.04, minimum 80 observations per leaf, seed 20261010 + window",
            "neighborhood": 256, "local_weights": "Gaussian kernel over standardized decision-time state and base prediction",
            "shrinkage_grid": [0, 0.25, 0.5, 0.75, 1], "block_score": "maximum residual within complete nonoverlapping horizon-length timestamp blocks",
            "source_sha256": hashlib.sha256((DATA / "time_series_15min_singleindex.csv").read_bytes()).hexdigest()})
    countries = ["DE"] if args.smoke else list(COUNTRIES)
    windows = [0] if args.smoke else list(range(12))
    all_rows, conditional, dependence = [], [], []
    for country in countries:
        frame = make_frame(source, country)
        for window in windows:
            rows, regime_rows, diagnostic = evaluate_window(frame, country, window)
            all_rows.extend(rows)
            conditional.extend(regime_rows)
            dependence.append(diagnostic)
            print(json.dumps({"country": country, "window": window,
                "purging": diagnostic["purged_boundaries_passed"], "test_n": diagnostic["test_n"],
                "selected_coverage": next(row["coverage"] for row in rows if row["method"] == "Selected shrinkage")}), flush=True)
    name = "smoke" if args.smoke else "main"
    write_csv(RESULTS / name / "window_results.csv", all_rows)
    write_csv(RESULTS / name / "conditional_results.csv", conditional)
    write_csv(RESULTS / name / "dependence_diagnostics.csv", dependence)
    write_csv(RESULTS / name / "summary.csv", summarize(all_rows))
    if args.smoke:
        assert all(np.isfinite(row["normalized_cost"]) and 0 <= row["coverage"] <= 1 for row in all_rows)
        assert all(row["selection_coverage"] >= 0.95 for row in all_rows)
        write_json(RESULTS / "smoke" / "usability.json", {"passed": True, "temporal_purging_passed": True,
            "finite_results": True, "common_selection_constraint_passed": True, "held_out_results_preserved": True})
    else:
        sensitivity = []
        frame = make_frame(source, "DE")
        for calibration_days, neighbors, required in ((14, 256, 0.95), (60, 256, 0.95), (30, 128, 0.95), (30, 512, 0.95), (30, 256, 0.90), (30, 256, 0.975)):
            for window in (0, 3, 6, 9):
                rows, _, _ = evaluate_window(frame, "DE", window, calibration_days=calibration_days, neighbors=neighbors, required=required)
                sensitivity.extend(rows)
        write_csv(RESULTS / "sensitivity.csv", sensitivity)
        trace = []
        for country, horizon, mode, penalty, required in (("DE", 60, "full", 20, 0.95), ("AT", 60, "full", 20, 0.95),
            ("DE", 120, "full", 20, 0.95), ("DE", 180, "full", 20, 0.95), ("DE", 60, "history_calendar", 20, 0.95),
            ("DE", 60, "full", 10, 0.95), ("DE", 60, "full", 40, 0.95), ("DE", 60, "full", 20, 0.975)):
            frame = make_frame(source, country, horizon)
            rows, _, _ = evaluate_window(frame, country, 0, horizon=horizon, feature_mode=mode, shortfall_cost=penalty, required=required)
            trace.extend(rows)
        write_csv(RESULTS / "field_to_calculation_trace.csv", trace)
    print(f"Public-data validation output: {RESULTS / name}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
