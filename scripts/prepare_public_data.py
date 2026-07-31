from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import public_config as cfg
from src.public_data import prepare_hourly_region


if __name__ == "__main__":
    for region in cfg.PUBLIC_REGIONS:
        path = prepare_hourly_region(region)
        print(f"Prepared {region}: {path}")
