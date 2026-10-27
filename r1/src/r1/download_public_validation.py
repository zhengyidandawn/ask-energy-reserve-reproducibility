from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.request

from run_paired_services import PROJECT

URL = "https://data.open-power-system-data.org/time_series/2020-10-06/time_series_15min_singleindex.csv"
ROOT = PROJECT / "data" / "public_validation_r1"


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(URL, headers={"User-Agent": "AEI research data retrieval", "Accept-Encoding": "identity"})
    output = ROOT / "time_series_15min_singleindex.csv"
    if output.exists() and output.stat().st_size == 112072477:
        print("Verified-size public CSV already downloaded")
        return
    with urllib.request.urlopen(request, timeout=60) as reply:
        prefix = reply.read(65536)
        text = prefix.decode("utf-8-sig")
        lines = text.splitlines()
        reader = csv.DictReader(io.StringIO("\n".join(lines[:-1])))
        first = next(reader)
        required = {"utc_timestamp", "DE_load_actual_entsoe_transparency", "AT_load_actual_entsoe_transparency", "BE_load_actual_entsoe_transparency", "NL_load_actual_entsoe_transparency"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("Public data header smoke failed")
        print(json.dumps({"source_header_smoke_passed": True, "sample_timestamp": first["utc_timestamp"], "fields": len(reader.fieldnames or [])}), flush=True)
        with output.open("wb") as handle:
            handle.write(prefix)
            total = len(prefix)
            threshold = 20 * 1024 * 1024
            for block in iter(lambda: reply.read(1024 * 1024), b""):
                handle.write(block)
                total += len(block)
                if total >= threshold:
                    print(f"Public CSV downloaded: {total // (1024 * 1024)} MiB", flush=True)
                    threshold += 20 * 1024 * 1024
    if output.stat().st_size != 112072477:
        raise ValueError("Public CSV length differs from package metadata")
    manifest = {"url": URL, "package_version": "2020-10-06", "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "bytes": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "time_step_minutes": 15, "load_unit": "MW", "primary_source": "ENTSO-E Transparency Platform",
        "archive": "Open Power System Data time-series package"}
    (ROOT / "retrieval_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
