from __future__ import annotations

import json
from pathlib import Path

from run_paired_services import PROJECT


DATA = PROJECT / "data" / "api_r1"
PAIRED = DATA / "paired"
PROTOCOL = DATA / "paired_protocol_v1"


def records(root: Path) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(root.rglob("record.json"))]


def tasks(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    failed_main = {
        row["task_id"]
        for row in records(PAIRED / "repeated_four_services_v1")
        if row.get("service") in {"qwen", "ernie"} and row.get("status") != "success"
    }
    failed_interfaces = {
        row["task_id"]
        for service in ("qwen", "ernie")
        for row in records(PAIRED / ("interfaces_" + service + "_v1"))
        if row.get("status") != "success"
    }
    main_tasks = [row for row in tasks(PROTOCOL / "repeat_tasks.jsonl") if row["task_id"] in failed_main]
    interface_tasks = [row for row in tasks(PROTOCOL / "interface_tasks.jsonl") if row["task_id"] in failed_interfaces]
    if {row["task_id"] for row in main_tasks} != failed_main:
        raise ValueError("The main recovery task set does not match the recorded failures")
    if {row["task_id"] for row in interface_tasks} != failed_interfaces:
        raise ValueError("The interface recovery task set does not match the recorded failures")
    main_path = PROTOCOL / "non_hunyuan_recovery_main_tasks_v1.jsonl"
    interface_path = PROTOCOL / "non_hunyuan_recovery_interface_tasks_v1.jsonl"
    smoke_path = PROTOCOL / "non_hunyuan_recovery_smoke_tasks_v1.jsonl"
    write_jsonl(main_path, main_tasks)
    write_jsonl(interface_path, interface_tasks)
    smoke_tasks = []
    for service in ("qwen", "ernie"):
        candidate = next((row for row in main_tasks if row["service"] == service), None)
        if candidate:
            smoke_tasks.append({**candidate, "task_id": candidate["task_id"] + "_smoke"})
    write_jsonl(smoke_path, smoke_tasks)
    print(json.dumps({
        "main_tasks": len(main_tasks),
        "interface_tasks": len(interface_tasks),
        "main_services": sorted({row["service"] for row in main_tasks}),
        "interface_services": sorted({row["service"] for row in interface_tasks}),
        "main_path": str(main_path),
        "interface_path": str(interface_path),
        "smoke_tasks": len(smoke_tasks),
        "smoke_path": str(smoke_path),
        "original_records_preserved": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
