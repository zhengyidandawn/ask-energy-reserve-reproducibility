from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import sys
import time
import urllib.error
import urllib.request

from api_readiness_smoke import PROJECT, WORKSPACE, load_credentials, redact

sys.path.insert(0, str(WORKSPACE / "src"))
from ask.checker import check_one, parse_model_json
from ask.schema import ADMISSIBLE_VARIABLES, FORBIDDEN_VARIABLES


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def output_schema() -> dict:
    study = {"type": ["object", "null"], "additionalProperties": False,
        "required": ["task_type", "region_id", "horizon_minutes", "cost_reserve", "cost_shortfall", "rolling_window", "requires_human_approval"],
        "properties": {
            "task_type": {"type": "string", "enum": ["upward_reserve_sizing"]},
            "region_id": {"type": ["string", "null"], "enum": ["GD", "ERCO", "CISO", "ISNE", "MISO", "SWPP", None]},
            "horizon_minutes": {"type": ["integer", "null"], "enum": [60, 120, 180, None]},
            "cost_reserve": {"type": ["number", "null"], "enum": [1, None]},
            "cost_shortfall": {"type": ["number", "null"], "enum": [10, 20, 40, None]},
            "rolling_window": {"type": "object", "additionalProperties": False,
                "required": ["train_days", "cal_days", "test_days", "rolling_step_days"],
                "properties": {name: {"type": "integer", "enum": [value]} for name, value in
                    {"train_days": 730, "cal_days": 30, "test_days": 30, "rolling_step_days": 30}.items()}},
            "requires_human_approval": {"type": "boolean", "enum": [True]},
        }}
    array = {"type": "array", "items": {"type": "string"}}
    properties = {"decision": {"type": "string", "enum": ["accept", "clarify", "reject", "partial_accept"]},
        "reason": {"type": "string"}, "study_schema": study,
        "admissible_variables": {"type": "array", "items": {"type": "string", "enum": sorted(ADMISSIBLE_VARIABLES)}},
        "forbidden_variables": {"type": "array", "items": {"type": "string", "enum": sorted(FORBIDDEN_VARIABLES)}},
        "workflow": array, "evidence_trace": array, "explanation": {"type": "string"},
        "audit_log": {"type": "object", "additionalProperties": False,
            "required": ["triggered_rules", "human_approval_required"],
            "properties": {"triggered_rules": array, "human_approval_required": {"type": "boolean"}}},
        "numerical_output_policy": {"type": "string", "enum": ["computed_by_verified_workflow_only"]}}
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


def historical_system() -> str:
    path = WORKSPACE / "supplementary_artifacts" / "llm_benchmark" / "prompts_blind.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    systems = {record["system_prompt"] for record in records}
    if len(systems) != 1:
        raise ValueError("Historical system prompt is not unique")
    return systems.pop()


def make_payload(service: dict, system: str, task: dict, parameters: dict) -> dict:
    messages = task.get("messages") or [{"role": "user", "content": task["user_request"]}]
    payload = {"model": service["requested_model"], "messages": [{"role": "system", "content": system}] + messages,
        **parameters, "stream": False}
    if task["interface"] == "json_object":
        payload["response_format"] = {"type": "json_object"}
    elif task["interface"] == "json_schema":
        payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "study_plan", "strict": True, "schema": output_schema()}}
    elif task["interface"] == "tool_call":
        payload["tools"] = [{"type": "function", "function": {"name": "submit_plan",
            "description": "Submit the checked energy study plan or clarification/rejection decision.", "strict": True, "parameters": output_schema()}}]
        payload["tool_choice"] = {"type": "function", "function": {"name": "submit_plan"}}
    else:
        raise ValueError("Unknown interface")
    return payload


def inspect(response: dict, task: dict) -> tuple[dict, dict | None]:
    import jsonschema

    choices = response.get("choices") or [{}]
    choice = choices[0]
    message = choice.get("message") or {}
    raw = message.get("content") or ""
    tool_name = None
    if task["interface"] == "tool_call":
        calls = message.get("tool_calls") or []
        if calls:
            function = calls[0].get("function") or {}
            raw = function.get("arguments") or ""
            tool_name = function.get("name")
    parsed, text, error = parse_model_json({"raw_response": raw})
    label = {"case_id": task["case_id"], "expected_decision": task.get("expected_decision", ""), "expected_human_gate": "TRUE"}
    checks = check_one(label, parsed, text, error, task["service"])
    try:
        jsonschema.validate(parsed, output_schema())
        exact_schema = True
    except jsonschema.ValidationError:
        exact_schema = False
    checks.update({"json_valid": not bool(error), "exact_json_schema_valid": exact_schema,
        "finish_reason": choice.get("finish_reason"), "tool_name": tool_name,
        "strict_decision_correct": checks["decision"] == label["expected_decision"],
        "tool_call_returned": tool_name == "submit_plan"})
    return checks, parsed


def call_one(task: dict, config: dict, credentials: dict, data_root: Path, system: str) -> dict:
    service = config["services"][task["service"]]
    key = task["task_id"]
    payload = make_payload(service, system, task, config["parameters"])
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    task_root = data_root / task["service"] / task["interface"] / key
    save(task_root / "request.json", payload)
    record = {"task_id": key, "case_id": task["case_id"], "packet": task["packet"],
        "service": task["service"], "interface": task["interface"], "repeat": task["repeat"],
        "requested_model": service["requested_model"], "endpoint": service["endpoint"],
        "request_sha256": digest(payload_bytes), "system_prompt_sha256": digest(system.encode("utf-8")),
        "parameters": config["parameters"], "request_started_at": utc_now(),
        "seed_setting": "not_sent", "thinking_setting": "not_sent_provider_default",
        "attempt": 1, "automatic_retries": 0, "provider_api_version": "v2" if task["service"] == "ernie" else "v1",
        "usage": None, "billed_cost": None, "billed_cost_status": "billing_record_unavailable"}
    started = time.perf_counter()
    request = urllib.request.Request(service["endpoint"], data=payload_bytes, headers={
        "Authorization": "Bearer " + credentials[service["credential_name"]], "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=config["timeout_seconds"]) as reply:
            body = redact(reply.read().decode("utf-8"), credentials)
            record["http_status"] = reply.status
        response = json.loads(body)
        save(task_root / "response.json", response)
        checks, parsed = inspect(response, task)
        record.update({"status": "success", "returned_model": response.get("model"),
            "provider_response_id": response.get("id"), "provider_created": response.get("created"),
            "system_fingerprint": response.get("system_fingerprint"), "usage": response.get("usage"),
            "response_sha256": digest((task_root / "response.json").read_bytes()), "checks": checks,
            "parsed_output": parsed})
    except urllib.error.HTTPError as error:
        record.update({"status": "rate_limited" if error.code == 429 else "http_error", "http_status": error.code,
            "error_body": redact(error.read().decode("utf-8", errors="replace"), credentials)[:6000]})
    except (TimeoutError, socket.timeout):
        record.update({"status": "timeout", "error_type": "timeout"})
    except Exception as error:
        record.update({"status": "error", "error_type": type(error).__name__, "error_message": redact(str(error), credentials)[:1000]})
    record["latency_seconds"] = time.perf_counter() - started
    record["request_finished_at"] = utc_now()
    save(task_root / "record.json", record)
    return record


def run_service(name: str, tasks: list[dict], config: dict, credentials: dict, data_root: Path, system: str,
                inter_request_delay: float = 0.0) -> list[dict]:
    rows = []
    iterator = iter(tasks)
    target = config["initial_concurrency_per_service"]
    maximum = config["maximum_concurrency_per_service"]
    successes = 0
    exhausted = False
    stopped = False
    with ThreadPoolExecutor(max_workers=maximum) as pool:
        pending = set()
        while pending or not exhausted:
            while len(pending) < target and not exhausted and not stopped:
                try:
                    task = next(iterator)
                except StopIteration:
                    exhausted = True
                    break
                if inter_request_delay > 0 and rows:
                    time.sleep(inter_request_delay)
                pending.add(pool.submit(call_one, task, config, credentials, data_root, system))
            if not pending:
                break
            completed, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                record = future.result()
                rows.append(record)
                if record["status"] in ("rate_limited", "timeout"):
                    target = max(1, target // 2)
                    successes = 0
                elif record.get("http_status") in (401, 402, 403):
                    stopped = True
                    exhausted = True
                elif record["status"] == "success":
                    successes += 1
                    if successes >= 30 and target < maximum:
                        target += 1
                        successes = 0
                if len(rows) % 25 == 0 or len(rows) == len(tasks) or record["status"] != "success":
                    print(json.dumps({"service": name, "finished": len(rows), "planned": len(tasks),
                        "last_status": record["status"], "concurrency": target,
                        "http_status": record.get("http_status")}), flush=True)
    return rows


def load_protocol(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if set(config["services"]) != {"deepseek", "qwen", "ernie", "hunyuan"}:
        raise ValueError("Unexpected service scope")
    return config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--services", nargs="+", choices=["deepseek", "qwen", "ernie", "hunyuan"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--inter-request-delay", type=float, default=0.0)
    args = parser.parse_args()
    config = load_protocol(args.protocol)
    tasks = [json.loads(line) for line in args.tasks.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.services:
        tasks = [task for task in tasks if task["service"] in args.services]
    if len({task["task_id"] for task in tasks}) != len(tasks):
        raise ValueError("Task IDs are not unique")
    system = historical_system()
    for task in tasks:
        payload = make_payload(config["services"][task["service"]], system, task, config["parameters"])
        if not payload["messages"] or "expected_decision" in json.dumps(payload):
            raise ValueError("A label would leak into the API payload")
    if args.dry_run:
        print(json.dumps({"preflight_passed": True, "tasks": len(tasks), "services": sorted({task["service"] for task in tasks}),
            "external_calls": 0, "system_prompt_sha256": digest(system.encode("utf-8"))}))
        return 0
    credentials = load_credentials(PROJECT.parent / "token-api.txt", {service["credential_name"] for service in config["services"].values()})
    data_root = PROJECT / "data" / "api_r1" / "paired" / args.run_id
    results_root = PROJECT / "results" / "api_r1" / "paired" / args.run_id
    save(data_root / "manifest.json", {"run_id": args.run_id, "started_at": utc_now(), "protocol": config,
        "protocol_sha256": digest(args.protocol.read_bytes()), "tasks_sha256": digest(args.tasks.read_bytes()),
        "script_sha256": digest(Path(__file__).read_bytes()), "system_prompt": system,
        "planned_tasks": len(tasks), "inter_request_delay_seconds": args.inter_request_delay,
        "credentials_recorded": False, "historical_files_overwritten": False})
    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run_service, name, [task for task in tasks if task["service"] == name], config,
            credentials, data_root, system, args.inter_request_delay) for name in config["services"]
            if any(task["service"] == name for task in tasks)]
        for future in futures:
            rows.extend(future.result())
    save(results_root / "records.json", sorted(rows, key=lambda row: row["task_id"]))
    summary = {"run_id": args.run_id, "planned_tasks": len(tasks), "completed_tasks": len(rows), "completed_at": utc_now(),
        "statuses": {}, "returned_models": {}}
    for name in config["services"]:
        subset = [row for row in rows if row["service"] == name]
        summary["statuses"][name] = {status: sum(row["status"] == status for row in subset) for status in {row["status"] for row in subset}}
        summary["returned_models"][name] = sorted({row.get("returned_model", "") for row in subset})
    save(results_root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if len(rows) == len(tasks) else 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
