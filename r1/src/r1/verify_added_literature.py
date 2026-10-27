from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sys
import urllib.request


PROJECT = Path(__file__).resolve().parents[2]
LOOKUP_PATH = Path(r"C:\Users\LuYH\.codex\skills\research-lookup\scripts\research_lookup.py")
SPECIFICATION = importlib.util.spec_from_file_location("public_literature_lookup", LOOKUP_PATH)
LOOKUP = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(LOOKUP)
DOIS = {
    "Elmachtoub2022Smart": "10.1287/mnsc.2020.3922",
    "Bertsimas2020Prescriptive": "10.1287/mnsc.2018.3253",
    "Lim2021TemporalFusion": "10.1016/j.ijforecast.2021.03.012",
    "Vazquez2019DemandResponse": "10.1016/j.apenergy.2018.11.002",
    "Nikseresht2025Hydrogen": "10.1016/j.renene.2025.122737",
    "Yin2024EnergyWater": "10.1016/j.renene.2024.121836",
    "Smets2025Storage": "10.1109/EEM64765.2025.11050194",
    "Hai2026Arbitrage": "10.1145/3765611.3815386",
    "Taylor2003WeatherEnsemble": "10.1016/S0169-2070(01)00123-6",
    "Fajardo2024SpatialTemporalLoad": "10.1109/URUCON63440.2024.10850383",
    "Noy2023Productivity": "10.1126/science.adh2586",
    "Vaccaro2024HumanAI": "10.1038/s41562-024-02024-1",
}


def verify(entry: tuple[str, str]) -> dict:
    key, doi = entry
    record = LOOKUP.request_json("crossref", "https://api.crossref.org/works/" + doi, {})
    message = record["message"]
    if message["DOI"].lower() != doi.lower():
        raise ValueError("DOI record mismatch")
    output = PROJECT / "data" / "literature" / "strengthening_20261011"
    output.mkdir(parents=True, exist_ok=True)
    (output / (key + "_crossref.json")).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    landing = {}
    request = urllib.request.Request("https://doi.org/" + doi, headers={"User-Agent": LOOKUP.USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content = response.read(200000)
            landing = {"status": response.status, "resolved_url": response.url, "bytes_read": len(content)}
            (output / (key + "_landing.html")).write_bytes(content)
    except Exception as error:
        landing = {"error_type": type(error).__name__, "message": str(error)}
    year = message.get("published-print", message.get("published", message.get("issued")))["date-parts"][0][0]
    return {"key": key, "doi": doi, "title": message["title"][0], "authors": message.get("author", []),
        "year": year, "venue": message.get("container-title", [""])[0], "volume": message.get("volume"),
        "pages": message.get("page", message.get("article-number")), "abstract": message.get("abstract"), "landing": landing}


def main() -> None:
    output = PROJECT / "data" / "literature" / "strengthening_20261011" / "verified_additions.json"
    cached = {entry["key"]: entry for entry in json.loads(output.read_text(encoding="utf-8"))} if output.exists() else {}
    missing = [(key, doi) for key, doi in DOIS.items() if key not in cached or cached[key]["doi"].lower() != doi.lower()]
    with ThreadPoolExecutor(max_workers=4) as executor:
        cached.update({entry["key"]: entry for entry in executor.map(verify, missing)})
    entries = [cached[key] for key in DOIS]
    output.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for entry in entries:
        print(json.dumps({key: entry[key] for key in ("key", "title", "year", "venue", "doi", "landing", "abstract")}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
