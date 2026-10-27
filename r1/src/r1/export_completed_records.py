from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import shutil

from recovery_overlay import RECOVERY_RUNS
from workspace_paths import PROJECT


RUNS = (
    "repeated_four_services_v1", "repeated_hunyuan_resume_v1",
    "interfaces_deepseek_v1", "interfaces_qwen_v1",
    "interfaces_ernie_v1", "interfaces_hunyuan_v1",
    "clarification_deepseek_v1", "clarification_qwen_v1",
    "clarification_ernie_v1", "clarification_hunyuan_v1",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    arguments = parser.parse_args()
    source_root = PROJECT / "data" / "api_r1" / "paired"
    package_root = arguments.package_root.resolve()
    destination = package_root / "data" / "formal_api_records"
    manifest = []
    task_ids = set()
    counts = Counter()
    for run in RUNS:
        replacements = {}
        for recovery_run in RECOVERY_RUNS.get(run, ()):
            for path in sorted((source_root / recovery_run).rglob("record.json")):
                record = json.loads(path.read_text(encoding="utf-8"))
                if record["status"] == "success":
                    replacements[record["task_id"]] = path
        for initial_path in sorted((source_root / run).rglob("record.json")):
            initial = json.loads(initial_path.read_text(encoding="utf-8"))
            final_path = replacements.get(initial["task_id"], initial_path)
            record = json.loads(final_path.read_text(encoding="utf-8"))
            if record["status"] != "success":
                raise ValueError(f"Incomplete planned task: {record['task_id']}")
            if record["task_id"] in task_ids:
                raise ValueError(f"Duplicate planned task: {record['task_id']}")
            task_ids.add(record["task_id"])
            phase = "primary" if run.startswith("repeated_") else run.split("_", 1)[0]
            counts[phase] += 1
            relative = initial_path.relative_to(source_root / run)
            target = destination / run / relative.parent
            target.mkdir(parents=True, exist_ok=True)
            for filename in ("record.json", "request.json", "response.json"):
                source = final_path.parent / filename
                if not source.is_file():
                    raise FileNotFoundError(source)
                shutil.copy2(source, target / filename)
            manifest.append({
                "task_id": record["task_id"],
                "source_run": "data/api_r1/paired/" + run,
                "relative_record": relative.as_posix(),
                "completed_source": final_path.relative_to(PROJECT).as_posix(),
                "status": record["status"],
                "sha256": hashlib.sha256(final_path.read_bytes()).hexdigest(),
            })
    expected = {"primary": 4960, "interfaces": 1440, "clarification": 280}
    if dict(counts) != expected:
        raise ValueError(f"Formal record counts differ from the protocol: {dict(counts)}")
    manifest_path = package_root / "data" / "formal_api_records_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    print(json.dumps({"completed_records": len(manifest), "phase_counts": dict(counts),
                      "recovered_records": sum("recovery" in row["completed_source"] for row in manifest)}))


if __name__ == "__main__":
    main()
