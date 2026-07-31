from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.neighbors import NearestNeighbors

from . import public_config as cfg


def _conformal_offset(residuals: np.ndarray, tau: float) -> float:
    values = np.asarray(residuals, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return 0.0
    level = min(1.0, np.ceil((values.size + 1) * tau) / values.size)
    return float(np.quantile(values, level, method="higher"))


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, tau: float) -> float:
    order = np.argsort(values)
    values = np.asarray(values)[order]
    weights = np.asarray(weights)[order]
    threshold = tau * np.sum(weights)
    return float(values[min(np.searchsorted(np.cumsum(weights), threshold), len(values) - 1)])


def _fit_local(state: pd.DataFrame, truth: np.ndarray, pred: np.ndarray, k: int = 256) -> dict:
    matrix = state.to_numpy(dtype=float)
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0)
    std[std == 0] = 1.0
    scaled = (matrix - mean) / std
    neighbors = NearestNeighbors(n_neighbors=min(k, len(state))).fit(scaled)
    residuals = truth - pred
    return {"mean": mean, "std": std, "neighbors": neighbors, "residuals": residuals, "global": _conformal_offset(residuals, cfg.TAU)}


def _apply_local(calibrator: dict, state: pd.DataFrame, pred: np.ndarray, shrinkage: float) -> np.ndarray:
    scaled = (state.to_numpy(dtype=float) - calibrator["mean"]) / calibrator["std"]
    distances, indices = calibrator["neighbors"].kneighbors(scaled, return_distance=True)
    output = np.zeros(len(state), dtype=float)
    for row, (distance, index) in enumerate(zip(distances, indices)):
        radius = max(float(distance[-1]), 1e-6)
        weights = np.exp(-0.5 * (distance / radius) ** 2)
        local = _weighted_quantile(calibrator["residuals"][index], weights, cfg.TAU)
        ess = (weights.sum() ** 2) / max(np.square(weights).sum(), 1e-6)
        mix = ess / (ess + shrinkage)
        offset = mix * local + (1.0 - mix) * calibrator["global"]
        output[row] = max(0.0, float(pred[row] + offset))
    return output


def _metric(truth: np.ndarray, reserve: np.ndarray) -> dict[str, float]:
    shortfall = np.clip(truth - reserve, 0.0, None)
    cost = cfg.COST_RESERVE * reserve + cfg.COST_SHORTFALL * shortfall
    q95 = np.quantile(shortfall, 0.95)
    tail = shortfall[shortfall >= q95]
    return {
        "reserve_mean": float(np.mean(reserve)),
        "shortfall_mean": float(np.mean(shortfall)),
        "shortfall_cvar95": float(np.mean(tail)) if tail.size else 0.0,
        "cost_mean": float(np.mean(cost)),
        "coverage": float(np.mean(truth <= reserve)),
        "coverage_gap": float(np.mean(truth <= reserve) - cfg.TAU),
    }


def _windows(ts: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    start = pd.to_datetime(ts).min().floor("D")
    end = pd.to_datetime(ts).max()
    result = []
    while True:
        train_end = start + pd.Timedelta(days=cfg.TRAIN_DAYS)
        test_end = train_end + pd.Timedelta(days=cfg.TEST_DAYS)
        if test_end > end:
            return result
        result.append((start, train_end - pd.Timedelta(days=cfg.CAL_DAYS), train_end, test_end))
        start += pd.Timedelta(days=cfg.STEP_DAYS)


def _select_adaptive(cal_fit: pd.DataFrame, cal_select: pd.DataFrame, fit_pred: np.ndarray, select_pred: np.ndarray, target: str) -> tuple[str, float]:
    rows = []
    for name, columns in cfg.STATE_VARIANTS.items():
        calibrator = _fit_local(cal_fit[columns], cal_fit[target].to_numpy(), fit_pred)
        for shrinkage in (0.0, 30.0, 60.0, 120.0, 240.0):
            reserve = _apply_local(calibrator, cal_select[columns], select_pred, shrinkage)
            score = _metric(cal_select[target].to_numpy(), reserve)["cost_mean"]
            rows.append((score, name, shrinkage))
    return min(rows, key=lambda row: (row[0], row[2]))[1:]


def evaluate_region(path: Path, max_windows: int = 0, seed: int = cfg.SEED) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = pd.read_csv(path, parse_dates=["ts"])
    region = str(frame["region_id"].iloc[0]) if "region_id" in frame and len(frame) else path.stem.split("_")[0]
    if region not in cfg.PUBLIC_REGIONS:
        raise ValueError(f"Only public regions are allowed: {sorted(cfg.PUBLIC_REGIONS)}; got {region}")
    frame = frame.sort_values("ts").dropna(subset=cfg.FEATURES + ["target_future_max_ramp"]).reset_index(drop=True)
    target = "target_future_max_ramp"
    rows: list[dict[str, object]] = []
    counterfactual: list[dict[str, object]] = []
    windows = _windows(frame["ts"])
    if max_windows:
        windows = windows[:max_windows]
    for window_id, (start, cal_start, train_end, test_end) in enumerate(windows):
        train = frame[(frame.ts >= start) & (frame.ts < cal_start)]
        calibration = frame[(frame.ts >= cal_start) & (frame.ts < train_end)]
        test = frame[(frame.ts >= train_end) & (frame.ts < test_end)]
        if train.empty or calibration.empty or test.empty:
            continue
        model = LGBMRegressor(objective="quantile", alpha=cfg.TAU, n_estimators=220, learning_rate=0.05, num_leaves=63, min_child_samples=80, verbosity=-1, random_state=seed + window_id)
        model.fit(train[cfg.FEATURES], train[target])
        cal_pred = np.clip(model.predict(calibration[cfg.FEATURES]), 0.0, None)
        test_pred = np.clip(model.predict(test[cfg.FEATURES]), 0.0, None)
        cal_truth = calibration[target].to_numpy(dtype=float)
        test_truth = test[target].to_numpy(dtype=float)
        residuals = cal_truth - cal_pred
        reserves: dict[str, np.ndarray] = {
            "lgbm_quantile": test_pred,
            "global_conformal": np.clip(test_pred + _conformal_offset(residuals, cfg.TAU), 0.0, None),
            "robust_upper_tail": np.clip(test_pred + _conformal_offset(residuals, 0.975), 0.0, None),
        }
        local_state = cfg.STATE_VARIANTS["full"]
        reserves["local_conformal"] = _apply_local(_fit_local(calibration[local_state], cal_truth, cal_pred), test[local_state], test_pred, 60.0)
        split = cal_start + pd.Timedelta(days=20)
        cal_fit = calibration[calibration.ts < split]
        cal_select = calibration[calibration.ts >= split]
        fit_pred = cal_pred[calibration.ts < split]
        select_pred = cal_pred[calibration.ts >= split]
        selected_state, selected_shrinkage = _select_adaptive(cal_fit, cal_select, fit_pred, select_pred, target)
        reserves["adaptive_local_conformal"] = _apply_local(_fit_local(calibration[list(cfg.STATE_VARIANTS[selected_state])], cal_truth, cal_pred), test[list(cfg.STATE_VARIANTS[selected_state])], test_pred, selected_shrinkage)
        rng = np.random.default_rng(seed + 1000 + window_id)
        scrambled = calibration[list(cfg.STATE_VARIANTS[selected_state])].copy()
        for column in scrambled.columns:
            scrambled[column] = rng.permutation(scrambled[column].to_numpy())
        scrambled_cal = _fit_local(scrambled, cal_truth, cal_pred)
        reserves["scrambled_selected_state"] = _apply_local(scrambled_cal, test[list(cfg.STATE_VARIANTS[selected_state])], test_pred, selected_shrinkage)
        for method, reserve in reserves.items():
            row = {"region_id": region, "region_label": cfg.PUBLIC_REGIONS[region]["label"], "window_id": window_id, "method": method, "window_start": start.date().isoformat(), "test_start": train_end.date().isoformat(), "test_end": test_end.date().isoformat(), "selected_state": selected_state if method in {"adaptive_local_conformal", "scrambled_selected_state"} else "", "selected_shrinkage": selected_shrinkage if method in {"adaptive_local_conformal", "scrambled_selected_state"} else ""}
            row.update(_metric(test_truth, reserve))
            rows.append(row)
        base_cost = _metric(test_truth, reserves["adaptive_local_conformal"])["cost_mean"]
        scrambled_cost = _metric(test_truth, reserves["scrambled_selected_state"])["cost_mean"]
        counterfactual.append({"region_id": region, "window_id": window_id, "base_method": "adaptive_local_conformal", "scrambled_method": "scrambled_selected_state", "cost_change": scrambled_cost - base_cost, "base_cost": base_cost, "scrambled_cost": scrambled_cost})
    window_metrics = pd.DataFrame(rows)
    if window_metrics.empty:
        raise RuntimeError(f"No complete rolling windows found in {path}")
    summary = window_metrics.groupby(["region_id", "region_label", "method"], as_index=False).agg({"cost_mean": "mean", "coverage": "mean", "shortfall_mean": "mean", "shortfall_cvar95": "mean", "reserve_mean": "mean", "window_id": "nunique"}).rename(columns={"window_id": "window_count"})
    summary["method_label"] = summary["method"].str.replace("_", " ").str.title()
    summary["rank"] = summary.groupby("region_id")["cost_mean"].rank(method="first").astype(int)
    summary = summary.sort_values(["region_id", "rank"]).reset_index(drop=True)
    return window_metrics, summary, pd.DataFrame(counterfactual)


def run(input_dir: Path, output_dir: Path, regions: Iterable[str] | None = None, max_windows: int = 0) -> None:
    selected = list(regions or cfg.PUBLIC_REGIONS)
    all_windows: list[pd.DataFrame] = []
    all_summaries: list[pd.DataFrame] = []
    all_counterfactuals: list[pd.DataFrame] = []
    for region in selected:
        if region not in cfg.PUBLIC_REGIONS:
            raise ValueError(f"Unsupported/non-public region: {region}")
        windows, summary, counterfactual = evaluate_region(input_dir / f"{region}_hourly.csv", max_windows=max_windows)
        all_windows.append(windows)
        all_summaries.append(summary)
        all_counterfactuals.append(counterfactual)
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.concat(all_windows, ignore_index=True).to_csv(output_dir / "rolling_window_metrics.csv", index=False)
    pd.concat(all_summaries, ignore_index=True).to_csv(output_dir / "validation_results.csv", index=False)
    pd.concat(all_counterfactuals, ignore_index=True).to_csv(output_dir / "counterfactual_results.csv", index=False)
