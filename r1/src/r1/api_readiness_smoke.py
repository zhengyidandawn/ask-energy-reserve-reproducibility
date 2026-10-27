from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
import sys
import time
import urllib.error
import urllib.request


from workspace_paths import ORIGINAL_DATA, PROJECT, WORKSPACE

CONFIG_PATH = PROJECT / "data" / "api_r1" / "development_smoke_v1.json"
PROMPTS_PATH = ORIGINAL_DATA / "supplementary_artifacts" / "llm_benchmark" / "prompts_blind.jsonl"
sys.path.insert(0, str(WORKSPACE / "src"))

from ask.checker import check_one, parse_model_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def load_credentials(path: Path, required: set[str]) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig")
    assignments = re.findall(r'(?m)^\s*\$env:([A-Z0-9_]+)\s*=\s*["\']([^"\'\r\n]+)["\']\s*$', text)
    credentials = {name: value for name, value in assignments if name in required}
    if set(credentials) != required:
        raise ValueError("Missing credential names: " + ", ".join(sorted(required - set(credentials))))
    if any(not value.strip() for value in credentials.values()):
        raise ValueError("An API credential is empty.")
    return credentials


def redact(text: str, credentials: dict[str, str]) -> str:
    for value in credentials.values():
        text = text.replace(value, "[REDACTED]")
        for component in re.findall(r"[A-Za-z0-9_.-]{20,}", value):
            text = text.replace(component, "[REDACTED]")
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[REDACTED]", text)
    return text


def load_inputs() -> tuple[dict, str, str]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    prompts = [json.loads(line) for line in PROMPTS_PATH.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    systems = {record["system_prompt"] for record in prompts}
    versions = {record["prompt_version"] for record in prompts}
    if len(systems) != 1 or len(versions) != 1:
        raise ValueError("The historical prompt set does not have one fixed system prompt and version.")
    if set(config["services"]) != {"deepseek", "qwen", "ernie", "hunyuan"}:
        raise ValueError("The smoke test must contain the original four services only.")
    return config, systems.pop(), versions.pop()


def build_payload(config: dict, service: dict, system: str, case: dict) -> dict:
    return {
        "model": service["requested_model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": case["user_request"]}],
        **config["parameters"],
    }


def inspect_response(response: dict, case: dict, service_name: str) -> dict:
    choices = response.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return {"json_valid": False, "schema_complete": False, "decision_matches": False, "finish_reason": None}
    choice = choices[0]
    content = (choice.get("message") or {}).get("content") or ""
    output, raw, error = parse_model_json({"raw_response": content})
    label = {"case_id": case["case_id"], "expected_decision": case["expected_decision"], "expected_human_gate": "TRUE"}
    checked = check_one(label, output, raw, error, service_name)
    return {
        "json_valid": not bool(error),
        "schema_complete": checked["schema_completeness"],
        "decision": checked["decision"],
        "decision_matches": checked["decision"] == case["expected_decision"],
        "joint_success": checked["joint_success"],
        "numerical_contamination": checked["numerical_contamination"],
        "unsupported_acceptance": checked["unsupported_acceptance"],
        "finish_reason": choice.get("finish_reason"),
        "content_length": len(content),
    }


def run_service(name: str, config: dict, system: str, version: str, credentials: dict, data_root: Path) -> list[dict]:
    service = config["services"][name]
    rows = []
    for case in config["cases"]:
        payload = build_payload(config, service, system, case)
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        write_json(data_root / name / (case["case_id"] + "_request.json"), payload)
        record = {
            "case_id": case["case_id"], "service": name, "purpose": config["purpose"],
            "requested_model": service["requested_model"], "historical_returned_model": service["historical_returned_model"],
            "endpoint": service["endpoint"], "prompt_version": version, "system_prompt_sha256": digest(system.encode("utf-8")),
            "request_sha256": digest(payload_bytes), "parameters": config["parameters"], "attempt_id": 1,
            "independent_run_id": "development_1", "request_started_at": utc_now(),
            "seed_setting": "not_sent", "thinking_setting": "not_sent_provider_default",
            "service_cost": None, "cost_status": "price_or_billing_record_not_supplied",
        }
        started = time.perf_counter()
        request = urllib.request.Request(service["endpoint"], data=payload_bytes, method="POST", headers={
            "Authorization": "Bearer " + credentials[service["credential_name"]], "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=config["timeout_seconds"]) as reply:
                body = reply.read().decode("utf-8")
                record["http_status"] = reply.status
            safe_body = redact(body, credentials)
            response = json.loads(safe_body)
            response_path = data_root / name / (case["case_id"] + "_response.json")
            write_json(response_path, response)
            record.update({"response_status": "success", "returned_model": response.get("model"),
                "provider_response_id": response.get("id"), "provider_created": response.get("created"),
                "system_fingerprint": response.get("system_fingerprint"), "usage": response.get("usage"),
                "response_sha256": digest(response_path.read_bytes()), "historical_result_reused": False,
                "checks": inspect_response(response, case, name)})
        except urllib.error.HTTPError as error:
            body = redact(error.read().decode("utf-8", errors="replace"), credentials)
            record.update({"http_status": error.code, "response_status": "rate_limited" if error.code == 429 else "http_error", "error_body": body})
        except (TimeoutError, socket.timeout):
            record.update({"response_status": "timeout", "error_type": "timeout"})
        except Exception as error:
            record.update({"response_status": "error", "error_type": type(error).__name__, "error_message": redact(str(error), credentials)})
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        record["request_finished_at"] = utc_now()
        write_json(data_root / name / (case["case_id"] + "_record.json"), record)
        rows.append(record)
        checks = record.get("checks", {})
        print(json.dumps({"service": name, "case": case["case_id"], "status": record["response_status"],
            "returned_model": record.get("returned_model"), "json_valid": checks.get("json_valid"),
            "schema_complete": checks.get("schema_complete"), "decision_matches": checks.get("decision_matches")}, ensure_ascii=False), flush=True)
        if record["response_status"] != "success" or not checks.get("json_valid") or checks.get("finish_reason") == "length":
            break
    return rows


def dry_run(config: dict, system: str) -> None:
    for service in config["services"].values():
        if not service["endpoint"].startswith("https://"):
            raise ValueError("All configured endpoints must use HTTPS.")
        for case in config["cases"]:
            payload = build_payload(config, service, system, case)
            if "expected_decision" in payload or "expected_decision" in payload["messages"][1]["content"]:
                raise ValueError("A test label would be sent to the service.")
    sample = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
        "decision": "clarify", "reason": "Provide region, horizon, and cost.", "study_schema": None,
        "admissible_variables": [], "forbidden_variables": [], "workflow": [], "evidence_trace": [],
        "explanation": "The workflow needs a complete request.", "audit_log": {"triggered_rules": ["clarification_required"]},
        "numerical_output_policy": "computed_by_verified_workflow_only",
    })}}]}
    checked = inspect_response(sample, config["cases"][1], "development_fixture")
    if not checked["json_valid"] or not checked["schema_complete"] or not checked["decision_matches"]:
        raise ValueError("The local response-processing smoke fixture failed.")
    print(json.dumps({"offline_preflight_passed": True, "services": list(config["services"]),
        "cases_per_service": len(config["cases"]), "maximum_live_calls": len(config["services"]) * len(config["cases"]),
        "external_api_called": False}))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded four-service development smoke check without overwriting historical results.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run-smoke", action="store_true")
    parser.add_argument("--services", nargs="+", choices=["deepseek", "qwen", "ernie", "hunyuan"])
    parser.add_argument("--max-tokens", type=int)
    args = parser.parse_args()
    config, system, version = load_inputs()
    if args.services:
        config["services"] = {name: config["services"][name] for name in dict.fromkeys(args.services)}
    if args.max_tokens is not None:
        if not 1400 <= args.max_tokens <= 8192:
            parser.error("The development output budget must be between 1400 and 8192 tokens.")
        config["parameters"]["max_tokens"] = args.max_tokens
    dry_run(config, system)
    if args.dry_run:
        return 0
    credentials = load_credentials(PROJECT.parent / "token-api.txt", {value["credential_name"] for value in config["services"].values()})
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    data_root = PROJECT / "data" / "api_r1" / "smoke" / run_id
    results_root = PROJECT / "results" / "api_r1" / "smoke" / run_id
    write_json(data_root / "manifest.json", {"run_id": run_id, "started_at": utc_now(), "config": config,
        "protocol_sha256": digest(CONFIG_PATH.read_bytes()), "prompt_file_sha256": digest(PROMPTS_PATH.read_bytes()),
        "script_sha256": digest(Path(__file__).read_bytes()), "credentials_recorded": False,
        "historical_archives_overwritten": False, "python_version": sys.version, "system_prompt": system})
    rows = []
    workers = min(len(config["services"]), config["maximum_parallel_services"])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_service, name, config, system, version, credentials, data_root): name for name in config["services"]}
        for future in as_completed(futures):
            rows.extend(future.result())
    summary = {"run_id": run_id, "purpose": config["purpose"], "external_api_called": True,
        "maximum_calls": len(config["services"]) * len(config["cases"]), "actual_calls": len(rows),
        "completed_at": utc_now(), "services": {}}
    for name in config["services"]:
        subset = [row for row in rows if row["service"] == name]
        passed = len(subset) == len(config["cases"]) and all(row["response_status"] == "success"
            and row["checks"]["json_valid"] and row["checks"]["schema_complete"] and row["checks"]["decision_matches"]
            and row["checks"]["finish_reason"] != "length" and not row["checks"]["numerical_contamination"] for row in subset)
        summary["services"][name] = {"calls": len(subset), "smoke_passed": passed,
            "statuses": dict(Counter(row["response_status"] for row in subset)),
            "returned_models": sorted({row["returned_model"] for row in subset if row.get("returned_model")}),
            "checks": [{"case_id": row["case_id"], **row.get("checks", {})} for row in subset]}
    write_json(results_root / "records.json", sorted(rows, key=lambda row: (row["service"], row["case_id"])))
    write_json(results_root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Results: " + str(results_root), flush=True)
    return 0 if all(value["smoke_passed"] for value in summary["services"].values()) else 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
