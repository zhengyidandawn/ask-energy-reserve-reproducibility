from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import importlib.util
import json
from pathlib import Path
import re
import sys
import unicodedata

from workspace_paths import PROJECT


LOOKUP_PATH = Path(r"C:\Users\LuYH\.codex\skills\research-lookup\scripts\research_lookup.py")
SPECIFICATION = importlib.util.spec_from_file_location("public_literature_lookup", LOOKUP_PATH)
LOOKUP = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(LOOKUP)
OUTPUT = PROJECT / "data" / "literature" / "cited_reference_verification_20261011"


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).lower()
    return re.sub(r"[^a-z0-9]", "", value)


def field_value(block: str, field: str) -> str | None:
    match = re.search(r"(?m)^\s*" + field + r"\s*=\s*\{", block)
    if not match:
        return None
    depth = 1
    start = match.end()
    position = start
    while position < len(block) and depth:
        if block[position] == "{" and block[position - 1] != "\\":
            depth += 1
        elif block[position] == "}" and block[position - 1] != "\\":
            depth -= 1
        position += 1
    if depth:
        raise ValueError("Unbalanced bibliography field: " + field)
    return block[start:position - 1]


def cited_entries() -> dict:
    bibliography = (PROJECT / "results" / "manuscript_unmark_build" / "main.bbl").read_text(encoding="utf-8")
    keys = set(re.findall(r"\\bibitem\[\{.*?\}\]\{([^}]+)\}", bibliography, re.S))
    entries = {}
    text = (PROJECT / "elsarticle_unmark" / "references.bib").read_text(encoding="utf-8")
    for block in re.split(r"(?m)^@", text)[1:]:
        key = re.match(r"\w+\{([^,]+),", block)[1]
        if key not in keys:
            continue
        entry = {"key": key}
        for field in ("title", "author", "year", "journal", "booktitle", "publisher", "doi", "url"):
            value = field_value(block, field)
            if value is not None:
                entry[field] = value
        entries[key] = entry
    assert len(entries) == len(keys)
    return entries


def verify(entry: dict) -> dict:
    result = {"bibliography": entry}
    doi = entry.get("doi")
    if (not doi and (entry["key"] in ("NERC2024LTRA", "FERCNERC2024WinterStormReport")
                    or "arXiv" in entry.get("journal", ""))) or (doi and doi.startswith("10.48550/")):
        result["status"] = "publisher_or_archive_source"
        return result
    destination = OUTPUT / (entry["key"] + "_crossref.json")
    cached = PROJECT / "data" / "literature" / "strengthening_20261011" / destination.name
    try:
        if not doi:
            search_path = OUTPUT / (entry["key"] + "_identity_search.json")
            if search_path.exists():
                candidates = json.loads(search_path.read_text(encoding="utf-8"))
            else:
                query = " ".join((entry["title"], entry.get("author", "").split(" and ")[0],
                                  entry["year"], entry.get("journal", entry.get("booktitle", ""))))
                candidates = LOOKUP.search_crossref(query, 5, None)
                search_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
            family = normalized(entry.get("author", "").split(" and ")[0].split(",")[0])
            expected_venue = entry.get("journal", entry.get("booktitle", ""))
            candidates = [candidate for candidate in candidates
                          if candidate.get("authors") and family in normalized(candidate["authors"][0])
                          and candidate.get("year") == int(entry["year"])
                          and (not expected_venue or SequenceMatcher(None, normalized(expected_venue),
                               normalized(candidate.get("venue") or "")).ratio() >= 0.7)]
            matches = sorted(candidates, key=lambda candidate: SequenceMatcher(
                None, normalized(entry["title"]), normalized(candidate["title"] or "")).ratio(), reverse=True)
            if not matches or SequenceMatcher(None, normalized(entry["title"]), normalized(matches[0]["title"] or "")).ratio() < 0.8:
                result["status"] = "publisher_or_archive_source"
                return result
            doi = matches[0]["doi"]
            result["discovered_doi"] = doi
            destination = OUTPUT / (entry["key"] + "_discovered_crossref.json")
        if destination.exists() and json.loads(destination.read_text(encoding="utf-8"))["message"]["DOI"].lower() == doi.lower():
            record = json.loads(destination.read_text(encoding="utf-8"))
        elif cached.exists():
            record = json.loads(cached.read_text(encoding="utf-8"))
        else:
            record = LOOKUP.request_json("crossref", "https://api.crossref.org/works/" + doi, {})
        destination.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        message = record["message"]
        title = message["title"][0]
        if message.get("subtitle"):
            title += ": " + message["subtitle"][0]
        similarity = SequenceMatcher(None, normalized(entry["title"]), normalized(title)).ratio()
        dates = {name: value["date-parts"][0] for name, value in message.items()
                 if name in ("published", "published-print", "published-online", "issued") and "date-parts" in value}
        family = normalized(entry.get("author", "").split(" and ")[0].split(",")[0])
        author_match = any(family == normalized(author.get("family", "")) for author in message.get("author", []))
        year_match = any(date[0] == int(entry["year"]) for date in dates.values())
        expected_venue = entry.get("journal", entry.get("booktitle", ""))
        venue_match = not expected_venue or any(SequenceMatcher(None, normalized(expected_venue), normalized(venue)).ratio() >= 0.7
                                               for venue in message.get("container-title", []))
        verified = similarity >= 0.8 and author_match and year_match and venue_match
        result.update({"status": "verified_doi" if verified else "identity_requires_review",
                       "title_similarity": similarity, "registered_title": title,
                       "author_match": author_match, "year_match": year_match, "venue_match": venue_match,
                       "registered_authors": message.get("author", []),
                       "registered_venue": message.get("container-title", []),
                       "registered_dates": dates, "registered_volume": message.get("volume"),
                       "registered_pages": message.get("page", message.get("article-number"))})
        assert message["DOI"].lower() == doi.lower()
    except Exception as error:
        result.update({"status": "lookup_unavailable", "error": str(error)})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    arguments = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entries = list(cited_entries().values())
    if arguments.smoke:
        entries = [entry for entry in entries if entry.get("doi")][:1]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(verify, entries))
    name = "smoke.json" if arguments.smoke else "cited_references.json"
    (OUTPUT / name).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {status: sum(result["status"] == status for result in results)
              for status in sorted({result["status"] for result in results})}
    print(json.dumps({"references": len(results), "statuses": counts,
                      "flagged": [result for result in results if result["status"] in ("identity_requires_review", "lookup_unavailable")]}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
