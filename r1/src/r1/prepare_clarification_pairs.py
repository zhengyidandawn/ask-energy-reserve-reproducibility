from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from prepare_human_evidence import read_csv, write_csv, write_json
from run_paired_services import PROJECT
from deterministic_interfaces import make_output


def dump_tasks(path: Path, tasks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=("deepseek", "qwen", "ernie", "hunyuan"))
    parser.add_argument("--smoke-recheck", action="store_true")
    args = parser.parse_args()
    root = PROJECT / "data" / "api_r1" / "clarification_protocol_v1"
    protocol = json.loads((PROJECT / "data" / "api_r1" / "paired_protocol_v1" / "protocol.json").read_text(encoding="utf-8"))
    cases = [row for row in read_csv(PROJECT / "data" / "human_r1" / "evaluation_labels.csv")
        if row["packet"] == "independently_authored_48" and row["expected_decision"] == "clarify"]
    replies = []
    for case in cases:
        region = case["gold_region_id"] or "GD"
        horizon = int(float(case["gold_horizon_minutes"] or "60"))
        penalty = int(float(case["gold_cost_shortfall"] or "20"))
        confirmed = f"The final confirmed study is for {region}, horizon {horizon} minutes, c_R=1 and c_S={penalty}. Prepare the upward-reserve study plan with human approval, calendar, current and lagged load, recent ramp, load statistics and observed weather. The verified numerical workflow will produce all numerical results."
        reply = "The following confirmation supersedes the earlier unspecified or alternative field values. " + confirmed
        replies.append({"case_id": case["case_id"], "initial_request": case["user_request"], "reply": reply,
            "confirmed_request": confirmed, "region_id": region, "horizon_minutes": horizon,
            "cost_reserve": 1, "cost_shortfall": penalty, "answer_source": "prespecified experiment script"})
    if not args.service:
        protocol.update({"protocol_version": "aei-r1-clarification-v1", "frozen_at": datetime.now(timezone.utc).isoformat(),
            "cases": [row["case_id"] for row in replies], "answer_source": "scripted analyst confirmation, not observed operator dialogue",
            "initial_trial_source": "repeated_four_services_v1, five responses per case and service",
            "turns": "original request, saved service response, scripted confirmation, new service response",
            "initial_response_not_dropped_when_wrong": True, "terminal_scoring": "confirmed request under unchanged validation rules"})
        if not args.smoke_recheck:
            write_json(root / "protocol.json", protocol)
            write_csv(root / "scripted_answers.csv", replies)
        tasks = []
        for service in protocol["services"]:
            if args.smoke_recheck and service == "hunyuan":
                continue
            confirmed = replies[0]["confirmed_request"]
            tasks.append({"task_id": f"{service}_clarification_development", "case_id": "DEV_CLARIFICATION",
                "service": service, "interface": "json_object", "repeat": 1, "packet": "development",
                "expected_decision": "accept", "user_request": confirmed,
                "messages": [{"role": "user", "content": "Prepare an upward-reserve study; region and horizon are to be confirmed."},
                    {"role": "assistant", "content": json.dumps(make_output("clarify", {}, [], ["region_id", "horizon_minutes", "cost_shortfall"]), ensure_ascii=False)},
                    {"role": "user", "content": confirmed}]})
        dump_tasks(root / ("smoke_recheck_tasks.jsonl" if args.smoke_recheck else "smoke_tasks.jsonl"), tasks)
    else:
        tasks = []
        service = args.service
        for row in replies:
            for repeat in range(1, 6):
                task_id = f"{service}_json_object_{row['case_id']}_r{repeat}"
                path = PROJECT / "data" / "api_r1" / "paired" / "repeated_four_services_v1" / service / "json_object" / task_id / "record.json"
                if not path.exists():
                    matches = list((PROJECT / "data" / "api_r1" / "paired").glob("repeated_hunyuan_resume_*/" + service + "/json_object/" + task_id + "/record.json"))
                    if len(matches) != 1:
                        raise ValueError("The paired initial response is unavailable")
                    path = matches[0]
                initial = json.loads(path.read_text(encoding="utf-8"))
                content = json.dumps(initial.get("parsed_output") or {"decision": "clarify", "reason": "The initial response was unavailable; confirmation is required."}, ensure_ascii=False)
                tasks.append({"task_id": f"{service}_clarification_{row['case_id']}_r{repeat}", "case_id": row["case_id"],
                    "service": service, "interface": "json_object", "repeat": repeat, "packet": "scripted_clarification_14",
                    "expected_decision": "accept", "user_request": row["confirmed_request"], "initial_record_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "messages": [{"role": "user", "content": row["initial_request"]},
                        {"role": "assistant", "content": content}, {"role": "user", "content": row["reply"]}]})
        dump_tasks(root / (service + "_tasks.jsonl"), tasks)
    print(json.dumps({"prepared": True, "clarification_cases": len(cases), "tasks": len(tasks), "service": args.service}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
