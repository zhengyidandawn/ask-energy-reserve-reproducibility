"""Run small offline checks before any expensive or external experiment."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from agreement_stats import summarize
from screen_common_coverage import screen
from validate_protocols import validate_all


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "smoke" / "offline_protocol_smoke.json"


def main() -> None:
    protocol_report = validate_all()
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        annotation = temp / "annotation.csv"
        with annotation.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["annotator_1_label", "annotator_2_label"])
            writer.writeheader()
            writer.writerows([
                {"annotator_1_label": "accept", "annotator_2_label": "accept"},
                {"annotator_1_label": "reject", "annotator_2_label": "clarify"},
                {"annotator_1_label": "not_collected", "annotator_2_label": "not_collected"},
            ])
        policy = temp / "policy.csv"
        with policy.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["policy", "window", "coverage"])
            writer.writeheader()
            writer.writerows([
                {"policy": "eligible", "window": "1", "coverage": "0.96"},
                {"policy": "eligible", "window": "2", "coverage": "0.94"},
                {"policy": "diagnostic", "window": "1", "coverage": "0.92"},
                {"policy": "diagnostic", "window": "2", "coverage": "0.93"},
            ])
        report = {
            "protocols_valid": not any(protocol_report.values()),
            "protocol_errors": protocol_report,
            "agreement": summarize(annotation, "annotator_1_label", "annotator_2_label"),
            "coverage_screen": screen(policy, 0.95),
            "external_api_called": False,
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["protocols_valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
