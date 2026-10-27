from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

from run_paired_services import PROJECT


def invoke(arguments: list[str]) -> None:
    subprocess.run([sys.executable, str(Path(__file__).with_name("run_paired_services.py")), *arguments], check=True)


def main() -> None:
    root = PROJECT / "data" / "api_r1" / "paired_protocol_v1"
    source = PROJECT / "data" / "api_r1" / "paired"
    while True:
        count = len(list((source / "repeated_four_services_v1" / "hunyuan").rglob("record.json")))
        count += sum(len(list((run / "hunyuan").rglob("record.json"))) for run in source.glob("repeated_hunyuan_resume_*"))
        if count == 1240:
            break
        time.sleep(4)
    print("Hunyuan repeated evaluation complete; starting supported interface tranche.", flush=True)
    invoke(["--protocol", str(root / "protocol.json"), "--tasks", str(root / "interface_tasks.jsonl"),
        "--run-id", "interfaces_hunyuan_v1", "--services", "hunyuan"])
    clarification = PROJECT / "data" / "api_r1" / "clarification_protocol_v1"
    smoke_source = json.loads((PROJECT / "results" / "api_r1" / "paired" / "clarification_smoke_v1" / "records.json").read_text(encoding="utf-8"))
    smoke_tasks = [json.loads(line) for line in (clarification / "smoke_tasks.jsonl").read_text(encoding="utf-8").splitlines()]
    task = next(task for task in smoke_tasks if task["service"] == "hunyuan")
    task["task_id"] += "_funded"
    path = clarification / "hunyuan_smoke_tasks.jsonl"
    path.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")
    invoke(["--protocol", str(clarification / "protocol.json"), "--tasks", str(path), "--run-id", "clarification_hunyuan_smoke_v1"])
    response = json.loads((PROJECT / "results" / "api_r1" / "paired" / "clarification_hunyuan_smoke_v1" / "records.json").read_text(encoding="utf-8"))[0]
    if response["status"] != "success" or not response["checks"]["json_valid"]:
        raise ValueError("Hunyuan clarification smoke did not return usable structured output")
    subprocess.run([sys.executable, str(Path(__file__).with_name("prepare_clarification_pairs.py")), "--service", "hunyuan"], check=True)
    invoke(["--protocol", str(clarification / "protocol.json"), "--tasks", str(clarification / "hunyuan_tasks.jsonl"), "--run-id", "clarification_hunyuan_v1"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
