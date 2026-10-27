from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from analyze_paired_evidence import normalize
from analyze_substantive_resolution import tariff
from run_online_draft_audit import DATA, FIELDS, RESULTS, SERVICES, adapted_output, diagnostics, read_csv, save
from deterministic_interfaces import request_rules, validate_plan
from workspace_paths import PROJECT


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def assess(output: dict | None, label: dict) -> dict:
    candidate = output if isinstance(output, dict) else {}
    fields = candidate.get("fields") or {}
    if not isinstance(fields, dict):
        fields = {}
    field_pairs = [(name, label.get("gold_" + name)) for name in FIELDS if label.get("gold_" + name) not in (None, "")]
    variable_pairs = [(name, value) for name, value in field_pairs if name != "cost_reserve"]
    correct = sum(normalize(name, fields.get(name)) == normalize(name, value) for name, value in field_pairs)
    variable_correct = sum(normalize(name, fields.get(name)) == normalize(name, value) for name, value in variable_pairs)
    gate = validate_plan(label["user_request"], adapted_output(output))
    schema_valid = isinstance(output, dict) and set(candidate) == {"decision", "fields", "clarification_question", "reason", "human_approval_required"} and set(fields) == set(FIELDS)
    disposition_correct = candidate.get("decision") == label["expected_decision"]
    return {"raw_correct": int(disposition_correct), "validated_correct": int(gate["decision"] == label["expected_decision"]),
        "field_correct": correct, "field_total": len(field_pairs), "manual_entries": 1 + len(variable_pairs),
        "retained_entries": int(disposition_correct) + variable_correct,
        "required_replacements": int(not disposition_correct) + len(variable_pairs) - variable_correct,
        "schema_valid": int(schema_valid), "approval_retained": int(candidate.get("human_approval_required") is True),
        "unsafe_ready": int(gate["execution_ready"] and label["expected_decision"] != "accept"),
        "valid_ready": int(gate["execution_ready"] and label["expected_decision"] == "accept"),
        "reference_accept": int(label["expected_decision"] == "accept"),
        "diagnostic_count": len(diagnostics(label["user_request"], output)["messages"])}


def interval(rows: list[dict], numerator: str, denominator: str, draws: int) -> tuple[float, float]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["text_cluster"]].append(row)
    totals = np.array([sum(float(row[numerator]) for row in group) for group in groups.values()])
    counts = np.array([sum(float(row[denominator]) for row in group) for group in groups.values()])
    selected = np.random.default_rng(20261011).integers(0, len(groups), (draws, len(groups)))
    return tuple(float(value) for value in np.quantile(totals[selected].sum(axis=1) / counts[selected].sum(axis=1), [0.025, 0.975]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    arguments = parser.parse_args()
    labels = {row["case_id"]: row for row in read_csv(PROJECT / "data/human_r1/evaluation_labels.csv")}
    source = DATA / ("smoke_trials" if arguments.smoke else "trials")
    trials = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(source.rglob("*.json"))]
    assert len(trials) == (12 if arguments.smoke else 480)
    output = RESULTS / "smoke" if arguments.smoke else RESULTS
    output.mkdir(parents=True, exist_ok=True)
    details = []
    prices = []
    for trial in trials:
        label = labels[trial["case_id"]]
        for stage in ("initial", "terminal"):
            record = trial[stage + "_record"]
            details.append({"service": trial["service"], "case_id": trial["case_id"], "repeat": trial["repeat"],
                "stage": stage, "text_cluster": label["text_cluster"], "expected_decision": label["expected_decision"],
                "unit": 1, **assess(record.get("parsed_output"), label),
                "online_calls": trial["online_calls"] if stage == "terminal" else 1,
                "service_seconds": trial["total_service_seconds"] if stage == "terminal" else record["latency_seconds"],
                "transport_complete": int(trial["transport_complete"]), "response_sha256": record.get("response_sha256", "")})
        calls = [trial["initial_record"]]
        if trial["online_calls"] == 2:
            calls.append(trial["terminal_record"])
        for record in calls:
            adjusted = {**record, "request_started_at": record["started_at"]}
            prices.append({"service": trial["service"], "case_id": trial["case_id"], "repeat": trial["repeat"],
                           "phase": record["phase"], "returned_model": record.get("returned_model", ""), **tariff(adjusted)})
    summary = []
    draws = 100 if arguments.smoke else 5000
    for service in SERVICES:
        for stage in ("initial", "terminal"):
            subset = [row for row in details if row["service"] == service and row["stage"] == stage]
            lower, upper = interval(subset, "retained_entries", "manual_entries", draws)
            entries = sum(row["manual_entries"] for row in subset)
            summary.append({"service": service, "stage": stage, "requests": len({row["case_id"] for row in subset}),
                "distinct_texts": len({row["text_cluster"] for row in subset}), "trials": len(subset),
                **{name: sum(row[name] for row in subset) for name in ("raw_correct", "validated_correct", "field_correct", "field_total", "manual_entries", "retained_entries", "required_replacements", "unsafe_ready", "valid_ready", "reference_accept", "schema_valid", "approval_retained")},
                "retained_fraction": sum(row["retained_entries"] for row in subset) / entries,
                "retained_ci_low": lower, "retained_ci_high": upper,
                "median_service_seconds": float(np.median([row["service_seconds"] for row in subset])),
                "online_calls": sum(row["online_calls"] for row in subset)})
    comparator = []
    identifiers = {row["case_id"] for row in trials}
    for identifier in sorted(identifiers):
        label = labels[identifier]
        rules = request_rules(label["user_request"])
        draft = {"decision": rules["decision"], "fields": rules["fields"], "clarification_question": "", "reason": "Frozen rules", "human_approval_required": True}
        comparator.append({"method": "field-preserving deterministic parser", "case_id": identifier, **assess(draft, label)})
    expert_times = defaultdict(list)
    for expert in read_csv(PROJECT / "data/human_r1/expert_plans_normalized.csv"):
        if expert["case_id"] in identifiers:
            label = labels[expert["case_id"]]
            draft = {"decision": expert["label"], "fields": {name: normalize(name, expert[name]) for name in FIELDS},
                     "clarification_question": expert["clarification_question"], "reason": expert["notes"], "human_approval_required": True}
            comparator.append({"method": expert["expert_id"], "case_id": expert["case_id"], **assess(draft, label)})
            expert_times[expert["case_id"]].append(float(expert["elapsed_minutes"]) * 60)
    comparator_summary = []
    for method in sorted({row["method"] for row in comparator}):
        subset = [row for row in comparator if row["method"] == method]
        comparator_summary.append({"method": method, "requests": len(subset), **{name: sum(row[name] for row in subset) for name in ("raw_correct", "validated_correct", "field_correct", "field_total", "manual_entries", "retained_entries", "required_replacements", "unsafe_ready", "valid_ready", "reference_accept")}})
    costs = []
    for service in SERVICES:
        selected = [row for row in prices if row["service"] == service]
        costs.append({"service": service, "online_calls": len(selected), "currency": selected[0]["currency"],
            "total_list_price_cost": sum(row["list_price_cost"] for row in selected),
            "mean_fee_per_trial": sum(row["list_price_cost"] for row in selected) / len([row for row in trials if row["service"] == service]),
            "input_tokens": sum(row["input_tokens"] for row in selected), "output_tokens": sum(row["output_tokens"] for row in selected)})
    expert_by_case = defaultdict(list)
    for row in comparator:
        if row["method"].startswith("EXP-"):
            expert_by_case[row["case_id"]].append(row)
    field_pairs = []
    for service in SERVICES:
        paired = []
        for identifier in sorted(identifiers):
            service_rows = [row for row in details if row["service"] == service and row["stage"] == "terminal" and row["case_id"] == identifier]
            expert_rows = expert_by_case[identifier]
            service_correct = np.mean([row["field_correct"] for row in service_rows])
            expert_correct = np.mean([row["field_correct"] for row in expert_rows])
            paired.append({"text_cluster": labels[identifier]["text_cluster"], "field_gain": float(service_correct - expert_correct),
                           "field_total": service_rows[0]["field_total"]})
        nonempty = [row for row in paired if row["field_total"]]
        lower, upper = interval(nonempty, "field_gain", "field_total", draws)
        grouped_gain = defaultdict(float)
        for row in nonempty:
            grouped_gain[row["text_cluster"]] += row["field_gain"]
        gains = np.array(list(grouped_gain.values()))
        permutations = np.random.default_rng(20261011).choice([-1, 1], (100 if arguments.smoke else 20000, len(gains))) @ gains
        probability = (1 + np.sum(np.abs(permutations) >= abs(gains.sum()) - 1e-12)) / (len(permutations) + 1)
        field_pairs.append({"service": service, "requests_with_fields": len(nonempty),
            "field_accuracy_difference": sum(row["field_gain"] for row in nonempty) / sum(row["field_total"] for row in nonempty),
            "ci_low": lower, "ci_high": upper, "p_value": float(probability), "p_holm": 0.0,
            "expert_reference": "mean of three existing expert plans per request",
            "scope": "field agreement in the recorded packet; human verification time remains separate"})
    running = 0.0
    for rank, row in enumerate(sorted(field_pairs, key=lambda record: record["p_value"])):
        running = max(running, min(1.0, row["p_value"] * (len(field_pairs) - rank)))
        row["p_holm"] = running
    sensitivity = []
    for service in SERVICES:
        selected = [row for row in details if row["service"] == service and row["stage"] == "terminal"]
        for review in (10, 20, 30, 40, 60):
            for correction in (5, 15, 30):
                for overhead in (0, 30, 60):
                    durations = [row["service_seconds"] + review * row["manual_entries"] + correction * row["required_replacements"] + overhead for row in selected]
                    margins = [np.mean(expert_times[row["case_id"]]) - duration for row, duration in zip(selected, durations)]
                    sensitivity.append({"service": service, "review_seconds_per_entry": review, "correction_seconds_per_replacement": correction,
                        "overhead_seconds": overhead, "median_modeled_seconds": float(np.median(durations)),
                        "fraction_below_expert_estimate": float(np.mean(np.array(margins) > 0)),
                        "basis": "conditional sensitivity with measured online time and expert self-estimates"})
    for filename, rows in (("trial_scores.csv", details), ("stage_summary.csv", summary), ("comparator_scores.csv", comparator),
                           ("comparator_summary.csv", comparator_summary), ("provider_cost_trials.csv", prices),
                           ("provider_cost_summary.csv", costs), ("conditional_time_sensitivity.csv", sensitivity),
                           ("paired_expert_field_difference.csv", field_pairs)):
        write_csv(output / filename, rows)
    save(output / "analysis_manifest.json", {"trials": len(trials), "online_calls": len(prices),
        "transport_complete": all(row["transport_complete"] for row in trials), "independent_repeats": 1 if arguments.smoke else 5,
        "bootstrap_draws": draws, "resampling_unit": "exact request text cluster", "reference_labels_used_only_for_scoring": True,
        "expert_field_multiplicity": "Holm over four service comparisons; 95-percent bootstrap intervals reported separately",
        "human_measurements_added": 0, "automated_feedback_calls_separately_counted": True,
        "protocol_sha256": hashlib.sha256((DATA / "protocol.json").read_bytes()).hexdigest(),
        "sources_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
            (PROJECT / "data/human_r1/evaluation_labels.csv", PROJECT / "data/human_r1/expert_plans_normalized.csv")}})
    print(json.dumps({"stages": summary, "comparators": comparator_summary, "costs": costs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
