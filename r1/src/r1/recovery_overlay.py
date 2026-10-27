from __future__ import annotations

import json
from pathlib import Path


from workspace_paths import FORMAL_DATA as DATA_ROOT

RECOVERY_RUNS = {
    "repeated_four_services_v1": ("recovery_hunyuan_main_attempt_v1", "recovery_non_hunyuan_main_attempt_v1"),
    "repeated_hunyuan_resume_v1": ("recovery_hunyuan_main_attempt_v1",),
    "interfaces_qwen_v1": ("recovery_non_hunyuan_interface_attempt_v1",),
    "interfaces_ernie_v1": ("recovery_non_hunyuan_interface_attempt_v1",),
    "interfaces_hunyuan_v1": ("recovery_hunyuan_interface_attempt_v1",),
    "clarification_qwen_v1": ("clarification_qwen_recovery_v1",),
}


def overlay_records(run: str, records: list[dict]) -> list[dict]:
    recovery_runs = RECOVERY_RUNS.get(run, ())
    if not recovery_runs:
        return records
    recovered = {}
    for recovery_run in recovery_runs:
        recovery_root = DATA_ROOT / recovery_run
        if not recovery_root.exists():
            continue
        for path in sorted(recovery_root.rglob("record.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            recovered[record["task_id"]] = record
    return [recovered.get(record["task_id"], record) for record in records]
