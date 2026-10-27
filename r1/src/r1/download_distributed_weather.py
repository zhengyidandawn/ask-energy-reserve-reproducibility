from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import urllib.error
import urllib.request
import zipfile

import pandas as pd

from workspace_paths import PROJECT


ROOT = PROJECT / "data" / "evidence_completion_20261011" / "weather"
BASE = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/air_temperature/historical/"
STATIONS = {"00433": "Berlin-Tempelhof", "01975": "Hamburg-Fuhlsbuettel",
            "01420": "Frankfurt-Main", "01048": "Dresden-Klotzsche",
            "04931": "Stuttgart-Echterdingen", "03379": "Muenchen-Stadt"}


def fetch(url: str, destination: Path) -> bytes:
    if destination.exists():
        return destination.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "AEI academic reproducibility study"}), timeout=45) as reply:
            content = reply.read()
    except urllib.error.URLError as error:
        if os.name != "nt" or not isinstance(error.reason, ssl.SSLError):
            raise
        subprocess.run(["pwsh.exe", "-NoProfile", "-File", str(Path(__file__).with_name("fetch_public_source.ps1")),
                        "-Url", url, "-Destination", str(destination)], check=True, capture_output=True)
        return destination.read_bytes()
    destination.write_bytes(content)
    return content


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    inventory = fetch(BASE + "TU_Stundenwerte_Beschreibung_Stationen.txt", ROOT / "station_inventory.txt").decode("latin-1")
    listing = fetch(BASE, ROOT / "directory_listing.html").decode("utf-8", errors="replace")
    names = sorted(set(re.findall(r"stundenwerte_TU_\d{5}_\d{8}_\d{8}_hist\.zip", listing)))
    selected = list(STATIONS)[:1] if args.smoke else list(STATIONS)
    manifest, frames = [], []
    for station in selected:
        inventory_lines = [line for line in inventory.splitlines() if re.match(r"\s*" + station + r"\s", line)]
        if len(inventory_lines) != 1:
            raise ValueError(f"Station inventory cannot identify {station}")
        location = re.match(r"\s*\d+\s+\d{8}\s+\d{8}\s+[-\d]+\s+([\d.]+)\s+([\d.]+)\s+(.*)", inventory_lines[0])
        if location is None:
            raise ValueError(f"Station coordinate format changed: {station}")
        candidates = [name for name in names if name.startswith("stundenwerte_TU_" + station + "_")
                      and name.split("_")[3] <= "20170101" and name.split("_")[4] >= "20201001"]
        if not candidates:
            raise ValueError(f"No full study-period archive for {station}")
        name = max(candidates, key=lambda value: value.split("_")[4])
        raw = fetch(BASE + name, ROOT / "raw" / name)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            products = [entry for entry in archive.namelist() if entry.startswith("produkt_tu_stunde")]
            if len(products) != 1:
                raise ValueError(f"Unexpected DWD product layout: {name}")
            frame = pd.read_csv(archive.open(products[0]), sep=";", na_values=[-999, -999.0])
        frame.columns = frame.columns.str.strip()
        frame["ts"] = pd.to_datetime(frame["MESS_DATUM"].astype(str), format="%Y%m%d%H", utc=True)
        frame = frame[(frame["ts"] >= "2016-12-01") & (frame["ts"] < "2020-10-01")]
        frame = frame[["ts", "TT_TU", "RF_TU"]].rename(columns={"TT_TU": "temperature_C", "RF_TU": "relative_humidity_percent"})
        frame["station"] = station
        if frame.empty or frame["ts"].duplicated().any():
            raise ValueError(f"Empty or duplicated station study data: {station}")
        frames.append(frame)
        manifest.append({"station": station, "name": STATIONS[station], "inventory_record": inventory_lines[0],
                         "latitude": float(location[1]), "longitude": float(location[2]), "url": BASE + name,
                         "archive": name, "sha256": hashlib.sha256(raw).hexdigest(), "rows": len(frame),
                         "missing_temperature": int(frame["temperature_C"].isna().sum()),
                         "missing_humidity": int(frame["relative_humidity_percent"].isna().sum())})
        print(json.dumps({"station": station, "rows": len(frame), "archive_bytes": len(raw)}), flush=True)
    combined = pd.concat(frames, ignore_index=True)
    combined.to_csv(ROOT / ("smoke_station_observations.csv" if args.smoke else "station_observations.csv"), index=False)
    metadata = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "source": "Deutscher Wetterdienst Climate Data Center",
                "inventory_url": BASE + "TU_Stundenwerte_Beschreibung_Stationen.txt", "stations": manifest,
                "record_time": "UTC observation hour", "features": ["air temperature", "relative humidity"],
                "integration": "equal-weight six-location observation mean; hourly observation shifted by one hour before backward time alignment",
                "missing_rule": "require every selected station for both mean features; exclude incomplete rows"}
    (ROOT / ("smoke_manifest.json" if args.smoke else "retrieval_manifest.json")).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
