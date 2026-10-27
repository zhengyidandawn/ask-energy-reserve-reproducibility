from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import time

from run_paired_services import PROJECT


def run_one(service: str) -> int:
    source = PROJECT / "data" / "api_r1" / "paired" / "repeated_four_services_v1" / service
    while len(list(source.rglob("record.json"))) < 1240:
        summary = PROJECT / "results" / "api_r1" / "paired" / "repeated_four_services_v1" / "summary.json"
        if summary.exists():
            print(f"No complete repeated sample for {service}; the interface tranche will not start.", flush=True)
            return 0
        time.sleep(3)
    print(f"Starting supported interface comparisons for {service}; repeated generation is complete.", flush=True)
    root = PROJECT / "data" / "api_r1" / "paired_protocol_v1"
    command = [sys.executable, str(Path(__file__).with_name("run_paired_services.py")),
        "--protocol", str(root / "protocol.json"), "--tasks", str(root / "interface_tasks.jsonl"),
        "--run-id", "interfaces_" + service + "_v1", "--services", service]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(run_one, ["deepseek", "qwen", "ernie", "hunyuan"]))
    raise SystemExit(max(codes))
