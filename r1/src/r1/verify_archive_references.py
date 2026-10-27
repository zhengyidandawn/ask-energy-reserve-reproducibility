from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import re
import sys
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from lxml import html

from verify_cited_references import LOOKUP, OUTPUT, normalized


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": LOOKUP.USER_AGENT})
    with urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def verify(row: dict) -> dict:
    entry = row["bibliography"]
    result = {"key": entry["key"], "title": entry["title"]}
    try:
        if entry["key"] == "Vovk2005AlgorithmicLearning":
            record = LOOKUP.request_json("crossref", "https://api.crossref.org/works/10.1007/b106715", {})
            (OUTPUT / "Vovk2005_first_edition_crossref.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            message = record["message"]
            assert message["published-print"]["date-parts"][0][0] == 2005
            assert normalized(message["title"][0]) == normalized(entry["title"])
            result.update({"verified": True, "source": "https://doi.org/10.1007/b106715", "edition_year": 2005})
            return result
        if entry["key"] in ("Romano2019CQR", "GibbsCandes2021AdaptiveConformal", "Ke2017LightGBM"):
            index_url = "https://papers.nips.cc/paper/" + entry["year"]
            index = fetch(index_url)
            (OUTPUT / (entry["key"] + "_proceedings_index.html")).write_text(index, encoding="utf-8")
            document = html.fromstring(index)
            matches = [element for element in document.xpath("//a[@href]")
                       if normalized(element.text_content()) == normalized(entry["title"])]
            assert len(matches) == 1
            url = urljoin(index_url, matches[0].get("href"))
        elif "arXiv" in entry.get("journal", ""):
            identifier = re.search(r"arXiv:(\d{4}\.\d+)", entry["journal"])[1]
            url = "https://arxiv.org/abs/" + identifier
        else:
            url = entry["url"]
        content = fetch(url)
        (OUTPUT / (entry["key"] + "_source.html")).write_text(content, encoding="utf-8")
        plain = " ".join(html.fromstring(content).itertext())
        title_match = normalized(entry["title"]) in normalized(plain)
        if entry["key"] == "FERCNERC2024WinterStormReport":
            title_match = "winterstormelliott" in normalized(plain)
        assert title_match
        result.update({"verified": True, "source": url, "title_found": True})
    except Exception as error:
        result.update({"verified": False, "error": str(error)})
    return result


def main() -> None:
    references = json.loads((OUTPUT / "cited_references.json").read_text(encoding="utf-8"))
    pending = [row for row in references if row["status"] == "publisher_or_archive_source"]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(verify, pending))
    (OUTPUT / "archive_reference_checks.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
