from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from . import public_config as cfg


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "ask-energy-reserve-reproducibility/1.0"})
    return session


def download_public_inputs() -> None:
    cfg.RAW_DIR.mkdir(parents=True, exist_ok=True)
    eia_path = cfg.RAW_DIR / "EBA.zip"
    if not eia_path.exists() or eia_path.stat().st_size < 100_000_000:
        with _session().get(cfg.EIA_URL, stream=True, timeout=120) as response:
            response.raise_for_status()
            with eia_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    years = range(pd.Timestamp(cfg.START).year, pd.Timestamp(cfg.END).year + 1)
    for spec in cfg.PUBLIC_REGIONS.values():
        station_dir = cfg.RAW_DIR / "noaa" / spec["station"]
        station_dir.mkdir(parents=True, exist_ok=True)
        for year in years:
            target = station_dir / f"{year}.csv"
            if target.exists() and target.stat().st_size > 10_000:
                continue
            url = f"{cfg.NOAA_URL}/{year}/{spec['station']}.csv"
            response = _session().get(url, timeout=120)
            response.raise_for_status()
            target.write_bytes(response.content)


def _float(value: object, scale: float = 1.0) -> float:
    text = str(value).split(",")[0].strip()
    if text in {"", "9999", "+9999", "-9999", "99999"}:
        return float("nan")
    try:
        return float(text) / scale
    except ValueError:
        return float("nan")


def _wind(value: object) -> float:
    parts = str(value).split(",")
    return _float(parts[3], 10.0) if len(parts) >= 4 else float("nan")


def _precip(value: object) -> float:
    parts = str(value).split(",")
    if len(parts) < 2:
        return 0.0
    parsed = _float(parts[1], 10.0)
    return 0.0 if not np.isfinite(parsed) else parsed


def _humidity(temp: pd.Series, dew: pd.Series) -> pd.Series:
    numerator = np.exp((17.625 * dew) / (243.04 + dew))
    denominator = np.exp((17.625 * temp) / (243.04 + temp))
    return (100.0 * numerator / denominator).clip(0.0, 100.0)


def _load_eia(region: str) -> pd.DataFrame:
    spec = cfg.PUBLIC_REGIONS[region]
    candidates = [f"EBA.{region}-ALL.D.H", f"EBA.{region}-ALL.D", f"EBA.{region}-ALL.DF.H"]
    records: list[dict[str, object]] = []
    with zipfile.ZipFile(cfg.RAW_DIR / "EBA.zip") as archive:
        members = [name for name in archive.namelist() if name.lower().endswith((".txt", ".json"))]
        if not members:
            raise RuntimeError("EIA bulk archive contains no JSON-lines member")
        with archive.open(members[0]) as handle:
            for raw_line in handle:
                line = raw_line.decode("utf-8", errors="ignore").strip().rstrip(",")
                if not line or line in {"[", "]"}:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(record.get("series_id", "")) not in candidates:
                    continue
                current: list[dict[str, object]] = []
                for pair in record.get("data", []):
                    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                        continue
                    ts = pd.to_datetime(pair[0], utc=True, errors="coerce")
                    value = pd.to_numeric(pair[1], errors="coerce")
                    if pd.isna(ts) or pd.isna(value):
                        continue
                    current.append({"ts_utc": ts, "y": float(value)})
                if current:
                    records = current
                    break
    if not records:
        raise RuntimeError(f"No EIA demand series found for {region}")
    frame = pd.DataFrame(records).sort_values("ts_utc")
    frame["ts"] = frame["ts_utc"].dt.tz_convert(ZoneInfo(spec["timezone"])).dt.tz_localize(None)
    return frame[["ts", "y"]].groupby("ts", as_index=False).mean()


def _load_noaa(region: str, years: Iterable[int]) -> pd.DataFrame:
    spec = cfg.PUBLIC_REGIONS[region]
    frames: list[pd.DataFrame] = []
    for year in sorted(set(years)):
        raw = pd.read_csv(cfg.RAW_DIR / "noaa" / spec["station"] / f"{year}.csv", low_memory=False)
        raw["ts_utc"] = pd.to_datetime(raw["DATE"], utc=True, errors="coerce")
        raw = raw.loc[raw["ts_utc"].notna()].copy()
        raw["T_obs"] = raw["TMP"].map(lambda x: _float(x, 10.0))
        dew = raw["DEW"].map(lambda x: _float(x, 10.0))
        raw["H_obs"] = _humidity(raw["T_obs"], dew)
        raw["W_obs"] = raw["WND"].map(_wind)
        precip = [col for col in raw.columns if col.startswith("AA")]
        raw["R_obs"] = raw[precip].apply(lambda row: sum(_precip(v) for v in row), axis=1) if precip else 0.0
        raw["ts"] = raw["ts_utc"].dt.tz_convert(ZoneInfo(spec["timezone"])).dt.tz_localize(None).dt.floor("h")
        frames.append(raw[["ts", "T_obs", "H_obs", "R_obs", "W_obs"]].groupby("ts", as_index=False).mean())
    if not frames:
        raise RuntimeError(f"No NOAA files found for {region}")
    return pd.concat(frames, ignore_index=True).drop_duplicates("ts").sort_values("ts")


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values("ts").copy()
    out["delta_y"] = out["y"].diff()
    out["ramp_pos"] = out["delta_y"].clip(lower=0.0)
    out["delta_y_lag_1"] = out["delta_y"].shift(1)
    out["delta_y_lag_6"] = out["delta_y"].shift(6)
    for lag in (1, 3, 6, 24):
        out[f"y_lag_{lag}"] = out["y"].shift(lag)
    out["recent_max_ramp_window"] = out["ramp_pos"].rolling(24, min_periods=24).max()
    out["recent_mean_ramp_window"] = out["ramp_pos"].rolling(24, min_periods=24).mean()
    out["recent_load_mean_window"] = out["y"].rolling(24, min_periods=24).mean()
    out["recent_load_std_window"] = out["y"].rolling(24, min_periods=24).std()
    hour = out["ts"].dt.hour
    dow = out["ts"].dt.dayofweek
    month = out["ts"].dt.month
    out["hod_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hod_cos"] = np.cos(2 * np.pi * hour / 24)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    out["month_sin"] = np.sin(2 * np.pi * month / 12)
    out["month_cos"] = np.cos(2 * np.pi * month / 12)
    out["is_weekend"] = (dow >= 5).astype(int)
    out["target_future_max_ramp"] = out["y"].diff().shift(-1).clip(lower=0.0)
    start = pd.Timestamp(cfg.START)
    end = pd.Timestamp(cfg.END)
    out = out[(out["ts"] >= start) & (out["ts"] <= end)].copy()
    return out.dropna(subset=cfg.FEATURES + ["target_future_max_ramp"]).reset_index(drop=True)


def prepare_hourly_region(region: str) -> Path:
    load = _load_eia(region)
    weather = _load_noaa(region, load["ts"].dt.year.unique())
    merged = load.merge(weather, on="ts", how="inner").sort_values("ts")
    result = add_features(merged)
    cfg.HOURLY_DIR.mkdir(parents=True, exist_ok=True)
    path = cfg.HOURLY_DIR / f"{region}_hourly.csv"
    result.to_csv(path, index=False)
    return path
