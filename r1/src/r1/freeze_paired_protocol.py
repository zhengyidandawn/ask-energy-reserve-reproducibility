from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

from run_paired_services import PROJECT, WORKSPACE, output_schema


def main() -> None:
    root = PROJECT / "data" / "api_r1" / "paired_protocol_v1"
    root.mkdir(parents=True, exist_ok=True)
    base = json.loads((PROJECT / "data" / "api_r1" / "development_smoke_v1.json").read_text(encoding="utf-8"))
    config = {"protocol_version": "aei-r1-paired-v1", "frozen_at": datetime.now(timezone.utc).isoformat(),
        "services": base["services"], "parameters": {"temperature": 0.0, "top_p": 1.0, "max_tokens": 4096},
        "timeout_seconds": 120, "initial_concurrency_per_service": 3, "maximum_concurrency_per_service": 10,
        "independent_repeats": 5, "automatic_retries": 0,
        "primary_inference_unit": "unique_request_text_cluster",
        "bootstrap_draws": 3000, "bootstrap_seed": 20261010,
        "pairwise_test": "paired_cluster_sign_permutation", "multiplicity": "Holm over six service pairs within each endpoint and packet",
        "test_failures_count_as_failures": True, "developer_smoke_excluded_from_formal_scores": True,
        "historical_model_identifiers_preserved": True,
        "human_time_measure": "estimated_minutes_reported_separately_from_API_latency",
        "form_reference": "expert-entered study fields on the 24 matched requests; human transcription required",
        "api_cost_measure": "provider usage retained; billed amount reported only if provided by provider or billing record"}
    for filename, value in (("protocol.json", config), ("output_schema.json", output_schema())):
        path = root / filename
        content = json.dumps(value, ensure_ascii=False, indent=2)
        if path.exists():
            raise FileExistsError("Protocol already exists; create a new version instead of overwriting")
        path.write_text(content, encoding="utf-8")
    smoke = []
    for name in base["services"]:
        for interface in ("json_object", "json_schema", "tool_call"):
            for case in base["cases"]:
                smoke.append({**case, "service": name, "interface": interface, "repeat": 1, "packet": "development",
                    "task_id": name + "_" + interface + "_" + case["case_id"]})
    with (root / "smoke_tasks.jsonl").open("x", encoding="utf-8") as handle:
        for task in smoke:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")
    with (WORKSPACE / "supplementary_artifacts" / "llm_benchmark" / "case_labels_blind.csv").open(encoding="utf-8-sig", newline="") as handle:
        blind = list(csv.DictReader(handle))
    with (PROJECT / "data" / "human_r1" / "evaluation_labels.csv").open(encoding="utf-8", newline="") as handle:
        external = [row for row in csv.DictReader(handle) if row["packet"] == "independently_authored_48"]
    tasks = []
    for name in base["services"]:
        for repeat in range(1, 6):
            for packet, cases in (("blind_original_200", blind), ("independently_authored_48", external)):
                for case in cases:
                    tasks.append({"task_id": f"{name}_json_object_{case['case_id']}_r{repeat}", "case_id": case["case_id"],
                        "user_request": case["user_request"], "service": name, "interface": "json_object",
                        "repeat": repeat, "packet": packet, "expected_decision": case["expected_decision"]})
    with (root / "repeat_tasks.jsonl").open("x", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")
    manifest = {"frozen_at": config["frozen_at"], "repeat_tasks": len(tasks), "development_tasks": len(smoke),
        "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir() if path.is_file()}}
    (root / "freeze_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"frozen_protocol": str(root), "formal_repeat_calls": len(tasks), "development_calls": len(smoke)}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
