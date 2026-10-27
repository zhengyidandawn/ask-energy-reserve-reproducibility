"""Validate the offline R1 protocol files without contacting any service."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROTOCOLS = ROOT / "data" / "protocols"


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def validate_schema(path: Path) -> list[str]:
    schema = read_json(path)
    errors: list[str] = []
    if schema.get("type") != "object":
        errors.append("type must be object")
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not required:
        errors.append("required must be a non-empty list")
    if not isinstance(properties, dict):
        errors.append("properties must be an object")
    elif isinstance(required, list):
        missing = [name for name in required if name not in properties]
        if missing:
            errors.append(f"required fields missing from properties: {missing}")
    return errors


def validate_csv_header(path: Path, expected: list[str]) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle), [])
    return [] if header == expected else [f"header differs: {header}"]


def validate_all() -> dict[str, list[str]]:
    report: dict[str, list[str]] = {}
    for path in sorted(PROTOCOLS.glob("*_schema.json")):
        report[path.name] = validate_schema(path)
    report["external_request_import_template.csv"] = validate_csv_header(
        ROOT / "data" / "external_validation" / "request_import_template.csv",
        ["request_id", "source_class", "source_description", "source_custodian", "request_text", "language", "region", "horizon_minutes", "expected_status", "annotation_status", "annotator_1_label", "annotator_2_label", "final_label", "provenance_note"],
    )
    report["independent_annotation_template.csv"] = validate_csv_header(
        ROOT / "data" / "annotations" / "independent_annotation_template.csv",
        ["request_id", "annotator_id", "expertise_category", "training_status", "annotation_timestamp", "label", "confidence", "disagreement_reason", "adjudication_status", "notes"],
    )
    return report


if __name__ == "__main__":
    results = validate_all()
    for name, errors in results.items():
        print(f"{name}: {'OK' if not errors else '; '.join(errors)}")
    raise SystemExit(1 if any(results.values()) else 0)
