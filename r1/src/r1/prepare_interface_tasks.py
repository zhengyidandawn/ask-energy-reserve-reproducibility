from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

from run_paired_services import PROJECT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--development-recheck", action="store_true")
    args = parser.parse_args()
    root = PROJECT / "data" / "api_r1" / "paired_protocol_v1"
    if args.development_recheck:
        base = json.loads((PROJECT / "data" / "api_r1" / "development_smoke_v1.json").read_text(encoding="utf-8"))
        tasks = [{**case, "service": "hunyuan", "interface": "json_object", "repeat": repeat, "packet": "development",
            "task_id": f"hunyuan_json_object_{case['case_id']}_d{repeat}"} for repeat in (2, 3) for case in base["cases"]]
        output = root / "hunyuan_recheck_tasks.jsonl"
    else:
        records = json.loads((PROJECT / "results" / "api_r1" / "paired" / "interface_smoke_v1" / "records.json").read_text(encoding="utf-8"))
        with (PROJECT / "data" / "human_r1" / "evaluation_labels.csv").open(encoding="utf-8", newline="") as handle:
            external = [row for row in csv.DictReader(handle) if row["packet"] == "independently_authored_48"]
        tasks = []
        for service in ("deepseek", "qwen", "ernie", "hunyuan"):
            for interface in ("json_schema", "tool_call"):
                probe = [row for row in records if row["service"] == service and row["interface"] == interface]
                if len(probe) != 3 or not all(row["status"] == "success" and row["checks"]["json_valid"]
                    and (interface != "tool_call" or row["checks"]["tool_call_returned"]) for row in probe):
                    continue
                for repeat in range(1, 6):
                    for case in external:
                        tasks.append({"task_id": f"{service}_{interface}_{case['case_id']}_r{repeat}",
                            "case_id": case["case_id"], "user_request": case["user_request"],
                            "service": service, "interface": interface, "repeat": repeat,
                            "packet": "independently_authored_48", "expected_decision": case["expected_decision"]})
        output = root / "interface_tasks.jsonl"
    with output.open("x", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")
    print(json.dumps({"tasks": len(tasks), "path": str(output), "development_only": args.development_recheck}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
