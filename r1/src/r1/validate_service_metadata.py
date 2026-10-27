"""Validate recorded service metadata; this script never calls an API."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


REQUIRED = {"case_id", "service_name", "requested_model", "returned_model", "prompt_version", "request_timestamp", "temperature", "seed_status", "response_status"}


def validate(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        errors = [f"missing columns: {sorted(REQUIRED - fields)}"] if not REQUIRED <= fields else []
        for index, row in enumerate(reader, start=2):
            missing = sorted(field for field in REQUIRED if not row.get(field, "").strip())
            if missing:
                errors.append(f"row {index} missing values: {missing}")
            if row.get("seed_status") not in {"fixed", "unsupported", "not_recorded"}:
                errors.append(f"row {index} has invalid seed_status")
            if row.get("response_status") not in {"success", "timeout", "rate_limited", "error", "not_run"}:
                errors.append(f"row {index} has invalid response_status")
        return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    errors = validate(args.csv_path)
    for error in errors:
        print(error)
    raise SystemExit(1 if errors else 0)
