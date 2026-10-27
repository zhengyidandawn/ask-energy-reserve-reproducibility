from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

import pandas as pd

from run_paired_services import PROJECT

ROOT = PROJECT / "data" / "public_validation_r1" / "eia"
ENDPOINT = "https://api.eia.gov/v2/electricity/rto/region-data/data/"


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    offset = 0
    rows = []
    total = None
    sources = []
    while total is None or offset < total:
        parameters = [("api_key", "DEMO_KEY"), ("frequency", "hourly"), ("data[0]", "value"),
            ("facets[type][]", "D"), ("start", "2023-01-01T00"), ("end", "2025-06-30T23"),
            ("sort[0][column]", "period"), ("sort[0][direction]", "asc"),
            ("sort[1][column]", "respondent"), ("sort[1][direction]", "asc"),
            ("offset", str(offset)), ("length", "5000")]
        parameters.extend(("facets[respondent][]", region) for region in ("ERCO", "CISO", "ISNE", "MISO", "SWPP"))
        url = ENDPOINT + "?" + urllib.parse.urlencode(parameters)
        path = ROOT / f"page_{offset:06d}.json"
        if path.exists():
            body = path.read_bytes()
        else:
            request = urllib.request.Request(url, headers={"User-Agent": "AEI reproducible load-data retrieval", "Accept-Encoding": "identity"})
            for attempt in range(6):
                try:
                    with urllib.request.urlopen(request, timeout=45) as reply:
                        body = reply.read()
                    break
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
                    if isinstance(error, urllib.error.HTTPError) and error.code not in (429, 500, 502, 503, 504):
                        raise
                    if attempt == 5:
                        raise
                    delay = min(10 * (attempt + 1), 50)
                    print(f"EIA retrieval backoff: offset={offset}, seconds={delay}", flush=True)
                    time.sleep(delay)
            path.write_bytes(body)
        response = json.loads(body)
        data = response.get("response", {}).get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("EIA returned no usable data page")
        if any(row.get("respondent") not in {"ERCO", "CISO", "ISNE", "MISO", "SWPP"} or row.get("type") != "D" for row in data):
            raise ValueError("EIA source-field smoke failed")
        if any(row.get("value-units") != "megawatthours" for row in data):
            raise ValueError("Unexpected EIA unit")
        if offset == 0:
            print(json.dumps({"source_smoke_passed": True, "first_records": data[:2]}), flush=True)
        total = int(response["response"]["total"])
        rows.extend(data)
        sources.append({"offset": offset, "url": url, "sha256": hashlib.sha256(body).hexdigest(), "n": len(data)})
        offset += len(data)
        print(f"EIA actual-demand rows downloaded: {offset}/{total}", flush=True)
        time.sleep(2)
    frame = pd.DataFrame(rows)
    frame["ts"] = pd.to_datetime(frame["period"], utc=True)
    frame["load_MW"] = pd.to_numeric(frame["value"], errors="coerce")
    for region, subset in frame.groupby("respondent"):
        subset = subset.sort_values("ts").drop_duplicates("ts", keep="last")
        subset[["ts", "load_MW"]].to_csv(ROOT / (region + "_actual_hourly.csv"), index=False)
    manifest = {"endpoint": ENDPOINT, "retrieved_at": datetime.now(timezone.utc).isoformat(), "n_rows": len(frame),
        "source_units": "megawatthours per one-hour interval", "derived_load_units": "average MW over each hourly interval",
        "requested_start": "2023-01-01T00", "requested_end": "2025-06-30T23", "sources": sources,
        "credential": "public EIA demonstration credential; no author API secret used"}
    (ROOT / "retrieval_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
