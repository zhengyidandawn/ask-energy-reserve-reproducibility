from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from run_paired_services import PROJECT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    protocol = PROJECT / "data" / "api_r1" / "paired_protocol_v1"
    original = PROJECT / "data" / "api_r1" / "paired" / "repeated_four_services_v1"
    if args.smoke:
        tasks = [json.loads(line) for line in (protocol / "hunyuan_recheck_tasks.jsonl").read_text(encoding="utf-8").splitlines()]
        tasks = tasks[:1]
        tasks[0]["task_id"] += "_funding_check"
        output = protocol / "hunyuan_funding_smoke_tasks.jsonl"
    else:
        completed = {json.loads(path.read_text(encoding="utf-8"))["task_id"] for path in original.rglob("record.json")}
        completed.update(json.loads(path.read_text(encoding="utf-8"))["task_id"] for root in original.parent.glob("repeated_hunyuan_resume_*") for path in root.rglob("record.json"))
        tasks = [json.loads(line) for line in (protocol / "repeat_tasks.jsonl").read_text(encoding="utf-8").splitlines()]
        tasks = [task for task in tasks if task["service"] == "hunyuan" and task["task_id"] not in completed]
        output = protocol / "hunyuan_remaining_tasks_v1.jsonl"
    with output.open("x", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")
    print(json.dumps({"tasks": len(tasks), "path": str(output), "previous_attempts_retained": True}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
