from __future__ import annotations

import json
from pathlib import Path

from run_paired_services import PROJECT


def main() -> None:
    protocol = PROJECT / "data" / "api_r1" / "clarification_protocol_v1"
    source = PROJECT / "data" / "api_r1" / "paired" / "clarification_qwen_v1"
    tasks = [json.loads(line) for line in (protocol / "qwen_tasks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    statuses = {}
    for record_path in source.rglob("record.json"):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        statuses[record["task_id"]] = record.get("status")
    pending = [task for task in tasks if statuses.get(task["task_id"]) != "success"]
    if not pending:
        raise SystemExit("No unsuccessful clarification slots remain.")
    output = protocol / "qwen_recovery_tasks_v1.jsonl"
    output.write_text("".join(json.dumps(task, ensure_ascii=False) + "\n" for task in pending), encoding="utf-8")
    print(json.dumps({"pending_tasks": len(pending), "task_ids": [task["task_id"] for task in pending], "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
