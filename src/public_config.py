from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
HOURLY_DIR = ROOT / "data" / "hourly_regions"
GENERATED_RESULTS_DIR = ROOT / "results" / "generated"

EIA_URL = "https://www.eia.gov/opendata/bulk/EBA.zip"
NOAA_URL = "https://www.ncei.noaa.gov/data/global-hourly/access"
START = "2021-01-01"
END = "2025-02-28 23:00:00"

PUBLIC_REGIONS = {
    "ERCO": {"label": "ERCOT", "timezone": "America/Chicago", "station": "72243012960"},
    "CISO": {"label": "CAISO", "timezone": "America/Los_Angeles", "station": "72483993225"},
    "ISNE": {"label": "ISO-NE", "timezone": "America/New_York", "station": "72509014739"},
    "MISO": {"label": "MISO", "timezone": "America/Chicago", "station": "72530094846"},
}

TRAIN_DAYS = 730
CAL_DAYS = 30
TEST_DAYS = 30
STEP_DAYS = 30
COST_RESERVE = 1.0
COST_SHORTFALL = 20.0
TAU = 1.0 - COST_RESERVE / COST_SHORTFALL
SEED = 20260309

FEATURES = [
    "y",
    "delta_y",
    "ramp_pos",
    "T_obs",
    "H_obs",
    "R_obs",
    "W_obs",
    "y_lag_1",
    "y_lag_3",
    "y_lag_6",
    "y_lag_24",
    "delta_y_lag_1",
    "delta_y_lag_6",
    "recent_max_ramp_window",
    "recent_mean_ramp_window",
    "recent_load_mean_window",
    "recent_load_std_window",
    "hod_sin",
    "hod_cos",
    "dow_sin",
    "dow_cos",
    "month_sin",
    "month_cos",
    "is_weekend",
]

STATE_VARIANTS = {
    "compact": ["y", "recent_max_ramp_window"],
    "weather_load": ["y", "recent_max_ramp_window", "T_obs", "H_obs"],
    "full": [
        "y",
        "recent_max_ramp_window",
        "recent_load_std_window",
        "T_obs",
        "H_obs",
        "hod_sin",
        "hod_cos",
        "dow_sin",
        "dow_cos",
    ],
}
