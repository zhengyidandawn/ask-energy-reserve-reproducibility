from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


METRIC_COLUMNS = [
    "schema_completeness",
    "semantic_correctness",
    "admissible_variable_correctness",
    "forbidden_variable_action_handling",
    "rejection_correctness",
    "clarification_correctness",
    "partial_acceptance_correctness",
    "evidence_trace_completeness",
    "explanation_grounding",
    "human_gate_correctness",
    "joint_success",
]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def summarize_checker_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"n_cases": len(rows)}
    conditional_metrics = {
        "rejection_correctness": lambda row: str(row.get("expected_decision", "")).lower() == "reject",
        "clarification_correctness": lambda row: str(row.get("expected_decision", "")).lower() == "clarify",
        "partial_acceptance_correctness": lambda row: str(row.get("expected_decision", "")).lower() == "partial_accept",
    }
    for col in METRIC_COLUMNS:
        selected = [row for row in rows if conditional_metrics.get(col, lambda _: True)(row)]
        summary[col] = sum(_bool(row.get(col)) for row in selected) / len(selected) if selected else None
    summary["numerical_contamination_count"] = sum(_bool(row.get("numerical_contamination")) for row in rows)
    summary["unsupported_acceptance_count"] = sum(_bool(row.get("unsupported_acceptance")) for row in rows)
    summary["parse_error_count"] = sum(_bool(row.get("parse_error")) for row in rows)
    return summary


def write_summary(rows: list[dict[str, Any]], csv_path: Path, json_path: Path) -> dict[str, Any]:
    summary = summarize_checker_rows(rows)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary
