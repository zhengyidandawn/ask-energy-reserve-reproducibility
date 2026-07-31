from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.public_data import download_public_inputs


if __name__ == "__main__":
    download_public_inputs()
    print("Downloaded public EIA/NOAA inputs under data/raw.")
