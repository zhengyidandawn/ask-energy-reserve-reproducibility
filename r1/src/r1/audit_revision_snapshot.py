from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import xml.etree.ElementTree as element_tree
import zipfile

from pypdf import PdfReader


PROJECT = Path(__file__).resolve().parents[2]
REVISION = PROJECT.parent
SUBMISSION = REVISION / "提交_AEI_R1"
RESULTS = PROJECT / "results" / "editorial_audit_20261011"


def csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def references(path: Path) -> dict:
    entries = {}
    for block in re.split(r"(?m)^@", path.read_text(encoding="utf-8"))[1:]:
        key_match = re.match(r"\w+\{([^,]+),", block)
        if not key_match:
            continue
        entry = {}
        for name in ("title", "author", "journal", "year", "doi"):
            match = re.search(r"(?m)^\s*" + name + r"\s*=\s*\{(.*)\}\s*,?\s*$", block)
            if match:
                entry[name] = match.group(1).replace("{", "").replace("}", "")
        entries[key_match.group(1)] = entry
    return entries


def document_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        root = element_tree.fromstring(archive.read("word/document.xml"))
    namespace = {"word": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    return ["".join(paragraph.itertext()) for paragraph in root.findall(".//word:p", namespace)]


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    snapshot = {}
    for filename in ("Manuscript_unmark.pdf", "补充材料.pdf"):
        reader = PdfReader(SUBMISSION / filename)
        page_text = [page.extract_text() or "" for page in reader.pages]
        (RESULTS / (Path(filename).stem + ".txt")).write_text(
            "\n\n".join(f"[PDF page {index + 1}]\n{content}" for index, content in enumerate(page_text)),
            encoding="utf-8",
        )
        snapshot[filename] = {"pages": len(page_text), "text_characters": sum(map(len, page_text))}
    snapshot["execution_summary"] = csv_rows(PROJECT / "results" / "paired_public_execution" / "summary.csv")
    execution_rows = csv_rows(PROJECT / "results" / "paired_public_execution" / "paired_trials.csv")
    direct_rows = [row for row in execution_rows if row["direct_plan_computed"] == "True"]
    snapshot["execution_totals"] = {
        "planned": len(execution_rows),
        "completed_checked": sum(row["execution_ready"] == "1" for row in execution_rows),
        "computed_direct": len(direct_rows),
        "nonzero_direct_cost_regret": sum(abs(float(row["direct_cost_regret"])) > 1e-12 for row in direct_rows),
    }
    parser_rows = csv_rows(PROJECT / "results" / "paired_evidence" / "deterministic_parser_scores.csv")
    snapshot["parser_unsafe_cases"] = [row for row in parser_rows if row["unsafe_ready"] == "1"]
    service_rows = csv_rows(PROJECT / "results" / "paired_evidence" / "service_summary.csv")
    snapshot["independent_service_results"] = [row for row in service_rows if row["packet"] == "independently_authored_48"]
    comparison_rows = csv_rows(PROJECT / "results" / "paired_evidence" / "paired_service_tests.csv")
    snapshot["paired_test_metrics"] = sorted({row["metric"] for row in comparison_rows})
    snapshot["public_summary"] = csv_rows(PROJECT / "results" / "public_validation_r1" / "main" / "summary.csv")
    source = PROJECT / "elsarticle_unmark"
    snapshot["framework_figure_text"] = {}
    for basename in ("F1_ASK_boundary_workflow", "F3_rolling_scheme"):
        svg_root = element_tree.parse(source / "figures" / (basename + ".svg")).getroot()
        svg_strings = [text.strip() for text in svg_root.itertext() if text.strip()]
        pdf_strings = [page.extract_text() or "" for page in PdfReader(source / "figures" / (basename + ".pdf")).pages]
        snapshot["framework_figure_text"][basename] = {
            "svg_strings": svg_strings,
            "pdf_text_characters": sum(map(len, pdf_strings)),
        }
    current_references = references(source / "references.bib")
    original_references = references(PROJECT / "baseline" / "references.bib")
    snapshot["added_reference_entries"] = {key: entry for key, entry in current_references.items() if key not in original_references}
    citation_keys = set()
    for path in (source / "sections").glob("*.tex"):
        for match in re.finditer(r"\\cite\w*\{([^}]+)\}", path.read_text(encoding="utf-8")):
            citation_keys.update(match.group(1).split(","))
    snapshot["cited_entries"] = {key: current_references[key] for key in sorted(citation_keys) if key in current_references}
    original_citations = set()
    for path in (PROJECT / "baseline" / "sections").glob("*.tex"):
        for match in re.finditer(r"\\cite\w*\{([^}]+)\}", path.read_text(encoding="utf-8")):
            original_citations.update(match.group(1).split(","))
    snapshot["added_main_text_citations"] = sorted(citation_keys - original_citations)
    comments = (REVISION / "Comments for author.txt").read_text(encoding="utf-8-sig")
    comments = re.sub(r"(?m)^Reviewer #1:\s*", "", comments)
    reviewer_comments = []
    for match in re.finditer(r"(?m)^\d+[.)].*$", comments):
        reviewer_comments.append(match.group().strip())
    letter_text = (PROJECT / "article" / "Response_to_Reviewers_AEI_R1_EN.txt").read_text(encoding="utf-8-sig")
    snapshot["original_comment_count"] = len(reviewer_comments)
    snapshot["comments_missing_from_english_text"] = [comment for comment in reviewer_comments if comment not in letter_text]
    english_paragraphs = document_paragraphs(SUBMISSION / "Response_to_Reviewers_AEI_R1_EN.docx")
    snapshot["comments_missing_from_english_docx"] = [comment for comment in reviewer_comments if comment not in "\n".join(english_paragraphs)]
    chinese_paragraphs = document_paragraphs(SUBMISSION / "Response_to_Reviewers_AEI_R1_CN.docx")
    snapshot["comments_missing_from_chinese_docx"] = [comment for comment in reviewer_comments if comment not in "\n".join(chinese_paragraphs)]
    snapshot["response_identifiers_in_docx"] = [paragraph for paragraph in english_paragraphs if re.fullmatch(r"R[123]-\d+", paragraph)]
    snapshot["submission_archives"] = {}
    for path in SUBMISSION.glob("*.zip"):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        snapshot["submission_archives"][path.name] = {
            "entries": len(names),
            "python_programs": [name for name in names if name.endswith(".py")],
            "request_or_result_records": [name for name in names if name.endswith((".jsonl", ".json", ".csv"))],
        }
    snapshot["submission_root_items"] = sorted(path.name for path in SUBMISSION.iterdir())
    output = RESULTS / "snapshot.json"
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "missing_comments_text": len(snapshot["comments_missing_from_english_text"]),
        "missing_comments_docx": len(snapshot["comments_missing_from_english_docx"]),
        "response_identifiers": len(snapshot["response_identifiers_in_docx"]),
        "added_reference_entries": snapshot["added_reference_entries"],
        "added_main_text_citations": snapshot["added_main_text_citations"],
        "execution_totals": snapshot["execution_totals"],
        "missing_comments_chinese_docx": len(snapshot["comments_missing_from_chinese_docx"]),
        "paired_test_metrics": snapshot["paired_test_metrics"],
        "submission_archives": snapshot["submission_archives"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
