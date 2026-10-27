from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from threading import Semaphore

from api_readiness_smoke import load_credentials
from deterministic_interfaces import request_rules
from integrate_r1_evidence import load_records
from prepare_human_evidence import read_csv, write_csv, write_json
from run_paired_services import call_one, historical_system
from workspace_paths import PROJECT


DATA = PROJECT / "data" / "evidence_completion_20261011" / "question_driven_dialogue"
RESULTS = PROJECT / "results" / "evidence_completion_20261011" / "question_driven_dialogue"
PATTERNS = {"region_id": r"region|area|system|区域|地区|省|ERCO|CISO|GD|MISO|ISNE|SWPP",
            "horizon_minutes": r"horizon|minute|hour|时域|分钟|小时|时长",
            "cost_shortfall": r"cost|penalty|ratio|shortfall|c[_ ]?s|成本|罚|缺额|惩罚"}


def mentioned(output: dict) -> set[str]:
    question = " ".join(str(output.get(field, "")) for field in ("reason", "explanation"))
    return {field for field, pattern in PATTERNS.items() if re.search(pattern, question, re.I)}


def terminal_correct(output: dict, expected: dict, supplied: set[str]) -> bool:
    schema = output.get("study_schema") or {}
    if output.get("decision") != "accept" or supplied != set(PATTERNS):
        return False
    try:
        return schema["region_id"] == expected["region_id"] and int(schema["horizon_minutes"]) == int(expected["horizon_minutes"]) \
            and float(schema["cost_shortfall"]) == float(expected["cost_shortfall"]) \
            and float(schema["cost_reserve"]) == 1 and schema.get("requires_human_approval") is True
    except (KeyError, TypeError, ValueError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    mode = "smoke" if args.smoke else "main"
    DATA.mkdir(parents=True, exist_ok=True)
    protocol_path = DATA / "protocol.json"
    config = json.loads((PROJECT / "data" / "api_r1" / "paired_protocol_v1" / "protocol.json").read_text(encoding="utf-8"))
    config.update({"initial_concurrency_per_service": 2, "maximum_concurrency_per_service": 3})
    answers = {row["case_id"]: row for row in read_csv(PROJECT / "data" / "api_r1" / "clarification_protocol_v1" / "scripted_answers.csv")}
    initial = [row for row in load_records("repeated_four_services_v1") if row["case_id"] in answers]
    if len(initial) != 280:
        raise ValueError("Every original initial trial must be retained")
    if not protocol_path.exists():
        write_json(protocol_path, {"frozen_at": datetime.now(timezone.utc).isoformat(), "services": config["services"],
            "parameters": config["parameters"], "initial_trials": 280, "cases": 14, "repeats": 5,
            "maximum_additional_turns": 3, "question_fields": PATTERNS,
            "respondent": "deterministic analyst script answering only explicitly mentioned study fields",
            "missing_question_reply": "Please ask me for any remaining required study fields.",
            "success": "all required fields supplied through questions, accepted matching plan, human approval retained",
            "initial_response_not_discarded": True, "original_initial_responses_preserved": True})
    if not args.smoke and not (RESULTS / "smoke" / "usability.json").exists():
        raise ValueError("A successful smoke test is required")
    if args.smoke:
        case = sorted(answers)[0]
        initial = [row for row in initial if row["case_id"] == case and row["repeat"] == 1]
    credentials = load_credentials(PROJECT.parent / "token-api.txt", {row["credential_name"] for row in config["services"].values()})
    system = historical_system()
    transcript_root = DATA / mode / "transcripts"
    transcript_root.mkdir(parents=True, exist_ok=True)
    def dialogue(first: dict) -> dict:
        case = answers[first["case_id"]]
        identifier = f"{first['service']}_{first['case_id']}_r{first['repeat']}"
        saved = transcript_root / (identifier + ".json")
        if saved.exists():
            return json.loads(saved.read_text(encoding="utf-8"))["summary"]
        expected = {field: case[field] for field in PATTERNS}
        original_fields = request_rules(case["initial_request"])["fields"]
        supplied = {field for field in PATTERNS if original_fields.get(field) is not None
                    and str(original_fields[field]).removesuffix(".0") == str(expected[field]).removesuffix(".0")}
        initially_supplied = set(supplied)
        current = first.get("parsed_output") or {}
        messages = [{"role": "user", "content": case["initial_request"]},
                    {"role": "assistant", "content": json.dumps(current, ensure_ascii=False)}]
        turns, total_seconds, characters = [], float(first["latency_seconds"]), 0
        for round_index in range(1, 4):
            fields = mentioned(current) - supplied if current.get("decision") == "clarify" else set()
            response = "; ".join(field + "=" + str(expected[field]) for field in sorted(fields))
            if fields:
                response = "My confirmed answers to your requested fields are: " + response + ". These answers supersede earlier unspecified or alternative values for these fields."
            else:
                response = "Please ask me for any remaining required study fields."
            supplied.update(fields)
            characters += len(response)
            messages.append({"role": "user", "content": response})
            task_id = identifier + "_turn" + str(round_index)
            task = {"task_id": task_id, "case_id": first["case_id"], "packet": "question_driven_clarification_14",
                    "service": first["service"], "interface": "json_object", "repeat": first["repeat"],
                    "expected_decision": "accept", "user_request": case["confirmed_request"], "messages": list(messages)}
            record_path = DATA / mode / "api_records" / first["service"] / "json_object" / task_id / "record.json"
            record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else call_one(task, config, credentials, DATA / mode / "api_records", system)
            if record["status"] != "success":
                raise RuntimeError(f"A dialogue response needs recovery: {task_id}: {record['status']}")
            current = record.get("parsed_output") or {}
            total_seconds += float(record["latency_seconds"])
            messages.append({"role": "assistant", "content": json.dumps(current, ensure_ascii=False)})
            turns.append({"round": round_index, "questioned_fields": sorted(fields), "answer": response,
                          "supplied_fields": sorted(supplied), "task_id": task_id,
                          "record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
                          "matching_completed_plan": terminal_correct(current, expected, supplied)})
            if terminal_correct(current, expected, supplied):
                break
        summary = {"service": first["service"], "case_id": first["case_id"], "repeat": first["repeat"],
                   "initial_decision": (first.get("parsed_output") or {}).get("decision", "invalid"),
                   "initially_explicit_fields": len(initially_supplied),
                   "additional_turns": len(turns), "confirmed_fields": len(supplied),
                   "matching_completed_plan": int(terminal_correct(current, expected, supplied)),
                   "total_service_seconds": total_seconds, "answer_characters": characters,
                   "final_decision": current.get("decision", "invalid"), "all_initial_trials_retained": True}
        write_json(saved, {"initial_task_id": first["task_id"], "initial_response_sha256": first["response_sha256"],
                           "initial_record": first, "expected_confirmation": expected, "turns": turns,
                           "messages": messages, "summary": summary})
        return summary
    summaries = []
    service_limits = {service: Semaphore(3) for service in config["services"]}
    def limited_dialogue(first):
        with service_limits[first["service"]]:
            return dialogue(first)
    initial.sort(key=lambda row: (row["case_id"], row["repeat"], row["service"]))
    with ThreadPoolExecutor(max_workers=12) as pool:
        pending = [pool.submit(limited_dialogue, row) for row in initial]
        for future in as_completed(pending):
            summaries.append(future.result())
            if len(summaries) % 10 == 0 or args.smoke:
                print(json.dumps({"mode": mode, "completed": len(summaries), "planned": len(initial),
                                  "last": summaries[-1]}, ensure_ascii=False), flush=True)
    summaries.sort(key=lambda row: (row["service"], row["case_id"], row["repeat"]))
    write_csv(RESULTS / mode / "dialogue_trials.csv", summaries)
    counts = Counter(row["service"] for row in summaries)
    if sum(counts.values()) != len(initial):
        raise ValueError("Incomplete dialogue denominator")
    write_json(RESULTS / mode / "usability.json", {"passed": True, "initial_trials": len(initial),
        "completed_dialogues": len(summaries), "services": dict(counts), "all_initial_trials_retained": True,
        "answers_limited_to_requested_fields": True, "additional_response_count": sum(row["additional_turns"] for row in summaries)})
    print(json.dumps({"completed_dialogues": len(summaries), "mode": mode}), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
