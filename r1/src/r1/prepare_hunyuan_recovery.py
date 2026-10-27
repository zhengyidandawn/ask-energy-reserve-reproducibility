from __future__ import annotations

import copy
import json
from pathlib import Path

from run_paired_services import PROJECT


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def records_under(root: Path) -> list[dict]:
    return [read_json(path) for path in sorted(root.rglob("record.json"))]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    data = PROJECT / "data" / "api_r1" / "paired_protocol_v1"
    records_root = PROJECT / "data" / "api_r1" / "paired"
    protocol = read_json(data / "protocol.json")
    recovery_protocol = copy.deepcopy(protocol)
    recovery_protocol["protocol_version"] = "aei-r1-hunyuan-recovery-v2"
    recovery_protocol["initial_concurrency_per_service"] = 1
    recovery_protocol["maximum_concurrency_per_service"] = 1
    recovery_protocol["recovery_note"] = "Same request payload parameters; serial schedule with explicit inter-request delay."
    (data / "hunyuan_recovery_protocol_v2.json").write_text(
        json.dumps(recovery_protocol, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    main_records = records_under(records_root / "repeated_four_services_v1")
    for root in sorted(records_root.glob("repeated_hunyuan_resume_*")):
        main_records.extend(records_under(root))
    failed_main_ids = {row["task_id"] for row in main_records
                       if row.get("service") == "hunyuan" and row.get("status") != "success"}
    all_main_tasks = [json.loads(line) for line in (data / "repeat_tasks.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    main_tasks = [row for row in all_main_tasks if row["task_id"] in failed_main_ids]

    interface_records = records_under(records_root / "interfaces_hunyuan_v1")
    failed_interface_ids = {row["task_id"] for row in interface_records if row.get("status") != "success"}
    all_interface_tasks = [json.loads(line) for line in (data / "interface_tasks.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    interface_tasks = [row for row in all_interface_tasks if row["task_id"] in failed_interface_ids]

    main_path = data / "hunyuan_recovery_main_tasks_v2.jsonl"
    interface_path = data / "hunyuan_recovery_interface_tasks_v2.jsonl"
    write_jsonl(main_path, main_tasks)
    write_jsonl(interface_path, interface_tasks)
    print(json.dumps({
        "main_failed_tasks": len(main_tasks),
        "main_task_ids": [row["task_id"] for row in main_tasks],
        "interface_failed_tasks": len(interface_tasks),
        "interface_task_ids": [row["task_id"] for row in interface_tasks],
        "protocol": str(data / "hunyuan_recovery_protocol_v2.json"),
        "previous_attempts_retained": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
