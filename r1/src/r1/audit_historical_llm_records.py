from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT.parents[1]
SERVICES = ("deepseek", "qwen", "ernie", "hunyuan")
CASE_SETS = {"blind": 200, "five_service": 150}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def main() -> int:
    versions_path = WORKSPACE / "supplementary_artifacts" / "llm_benchmark" / "model_versions.csv"
    with versions_path.open(encoding="utf-8-sig", newline="") as handle:
        versions = {row["service"]: row for row in csv.DictReader(handle)}
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "main_services": list(SERVICES),
        "version_table_sha256": sha256(versions_path), "external_api_called": False,
        "purpose": "historical_archive_inventory_not_new_results", "datasets": [], "errors": []}
    file_rows = []
    for case_set, expected_count in CASE_SETS.items():
        prompt_path = WORKSPACE / "supplementary_artifacts" / "llm_benchmark" / f"prompts_{case_set}.jsonl"
        prompts = load_jsonl(prompt_path)
        prompt_ids = {row["case_id"] for row in prompts}
        system_hashes = {hashlib.sha256(row["system_prompt"].encode("utf-8")).hexdigest() for row in prompts}
        if len(prompts) != expected_count or len(prompt_ids) != expected_count or len(system_hashes) != 1:
            report["errors"].append(f"Prompt count, IDs, or instruction are inconsistent for {case_set}.")
        file_rows.append({"role": "prompts", "service": "shared", "case_set": case_set,
            "workspace_relative_path": prompt_path.relative_to(WORKSPACE).as_posix(), "sha256": sha256(prompt_path)})
        for service in SERVICES:
            directory = WORKSPACE / "experiments" / "outputs" / "llm_benchmark" / case_set / service
            output_path = directory / "model_outputs.jsonl"
            config_path = directory / "invocation_config.json"
            outputs = load_jsonl(output_path)
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            counts = Counter(row["case_id"] for row in outputs)
            models = Counter(row.get("returned_model") for row in outputs)
            row_model_mismatch = sum(row.get("returned_model") != row.get("provider_response", {}).get("model") for row in outputs)
            expected_returned = {value.strip() for value in versions[service]["returned_models"].split(";")}
            if len(outputs) != expected_count or set(counts) != prompt_ids or any(value != 1 for value in counts.values()):
                report["errors"].append(f"Record count or request IDs are inconsistent for {case_set}/{service}.")
            if set(models) != expected_returned or row_model_mismatch:
                report["errors"].append(f"Returned identifiers differ from the archived version table for {case_set}/{service}.")
            dataset = {"service": service, "case_set": case_set, "responses": len(outputs), "unique_case_ids": len(counts),
                "responses_per_case": sorted(set(counts.values())), "requested_model": config["model_name"],
                "returned_models": dict(models), "batch_configuration_time": config["invocation_date"],
                "endpoint_base_url": config["base_url"], "prompt_version": config.get("prompt_version"),
                "benchmark_config_version": config.get("benchmark_config_version"), "system_prompt_sha256": sorted(system_hashes),
                "temperature": config.get("temperature"), "top_p": config.get("top_p"), "max_tokens": config.get("max_tokens"),
                "response_format": config.get("response_format"), "model_outputs_sha256": sha256(output_path),
                "invocation_config_sha256": sha256(config_path), "provider_model_field_mismatches": row_model_mismatch,
                "records_with_usage": sum(isinstance(row.get("provider_response", {}).get("usage"), dict) for row in outputs),
                "historical_seed_setting": "not_recorded" if "seed" not in config else config["seed"],
                "historical_thinking_setting": "not_recorded" if "thinking" not in config else config["thinking"],
                "historical_latency_setting": "not_recorded" if "latency_ms" not in outputs[0] else "available",
                "independent_multiple_run_evidence": any(value > 1 for value in counts.values()),
                "immutable_provider_weights_established": False}
            report["datasets"].append(dataset)
            for role, path in [("responses", output_path), ("invocation_config", config_path)]:
                file_rows.append({"role": role, "service": service, "case_set": case_set,
                    "workspace_relative_path": path.relative_to(WORKSPACE).as_posix(), "sha256": sha256(path)})
    report["total_main_service_responses"] = sum(row["responses"] for row in report["datasets"])
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    data_dir = PROJECT / "data" / "api_r1" / "historical" / run_id
    result_dir = PROJECT / "results" / "api_r1" / "historical" / run_id
    data_dir.mkdir(parents=True, exist_ok=False)
    result_dir.mkdir(parents=True, exist_ok=False)
    with (data_dir / "archive_file_inventory.csv").open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["role", "service", "case_set", "workspace_relative_path", "sha256"])
        writer.writeheader()
        writer.writerows(file_rows)
    (data_dir / "metadata_records.json").write_text(json.dumps(report["datasets"], ensure_ascii=False, indent=2), encoding="utf-8")
    (result_dir / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total_responses": report["total_main_service_responses"], "datasets": len(report["datasets"]),
        "errors": report["errors"], "independent_multiple_runs_found": any(row["independent_multiple_run_evidence"] for row in report["datasets"]),
        "external_api_called": False, "results_directory": str(result_dir)}, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
