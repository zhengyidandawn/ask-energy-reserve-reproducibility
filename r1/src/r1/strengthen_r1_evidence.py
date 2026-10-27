from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

from analyze_paired_evidence import bootstrap_mean, field_accuracy, holm, paired_test
from deterministic_interfaces import request_rules
from integrate_r1_evidence import load_records
from prepare_human_evidence import read_csv, write_csv, write_json
from run_paired_services import PROJECT, WORKSPACE
from workspace_paths import ORIGINAL_DATA


RESULTS = PROJECT / "results" / "strengthening_20261011"
DATA = PROJECT / "data" / "strengthening_20261011"
PUBLIC_DATA = PROJECT / "data" / "public_validation_r1"


def cache(country="DE", horizon=60, mode="full", penalty=20, required=0.95):
    path = PUBLIC_DATA / "prediction_cache" / f"{country}_w0_H{horizon}_cal30_K256_req{required}_f{mode}_cs{penalty}.npz"
    return np.load(path), path


def controlled_calculations() -> list[dict]:
    reference, reference_path = cache()
    configurations = [("Reference", "DE", 60, "full", 20, 0.95),
        ("Region", "AT", 60, "full", 20, 0.95), ("Horizon 120", "DE", 120, "full", 20, 0.95),
        ("Horizon 180", "DE", 180, "full", 20, 0.95), ("Variables", "DE", 60, "history_calendar", 20, 0.95),
        ("Shortfall weight 10", "DE", 60, "full", 10, 0.95), ("Shortfall weight 40", "DE", 60, "full", 40, 0.95),
        ("Required coverage 0.975", "DE", 60, "full", 20, 0.975), ("Tail reporting", "DE", 60, "full", 20, 0.95)]
    scale_row = next(row for row in read_csv(PROJECT / "results" / "public_validation_r1" / "main" / "window_results.csv")
        if row["country"] == "DE" and row["window"] == "0" and row["method"] == "Selected shrinkage")
    scale = float(scale_row["cost_index"]) / float(scale_row["normalized_cost"])
    rows = []
    for field, country, horizon, mode, penalty, required in configurations:
        candidate, candidate_path = cache(country, horizon, mode, penalty, required)
        common, reference_indices, candidate_indices = np.intersect1d(reference["timestamps"], candidate["timestamps"], return_indices=True)
        target = reference["target"][reference_indices]
        correct = reference["Selected_shrinkage"][reference_indices]
        reserve = candidate["Selected_shrinkage"][candidate_indices]
        cost = np.mean(reserve + 20 * np.maximum(target - reserve, 0)) / scale
        reference_cost = np.mean(correct + 20 * np.maximum(target - correct, 0)) / scale
        rows.append({"field": field, "decisions": len(common), "coverage_on_reference_target": np.mean(target <= reserve),
            "reserve_MW": np.mean(reserve), "cost_under_reference_objective": cost, "cost_difference": cost - reference_cost,
            "reserve_difference_MW": np.mean(reserve - correct), "source": "controlled study specification",
            "reference_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest()})
    return rows


def matched_comparisons() -> list[dict]:
    experts = read_csv(PROJECT / "data" / "human_r1" / "expert_plans_normalized.csv")
    identifiers = {row["case_id"] for row in experts}
    trials = read_csv(PROJECT / "results" / "paired_evidence" / "trial_scores.csv")
    parser_rows = read_csv(PROJECT / "results" / "paired_evidence" / "deterministic_parser_scores.csv")
    matched = read_csv(PROJECT / "results" / "paired_evidence" / "expert_matched_summary.csv")
    rows = []
    for item in matched:
        if item["method"].startswith("EXP"):
            rows.append({"method": item["method"], "requests": 24, "trials": 24, "decision_accuracy": item["decision_accuracy"],
                "field_accuracy": item["field_accuracy"], "unsafe_ready": item["unsafe_ready"], "false_clarification": 0,
                "time_value": item["estimated_human_mean_minutes"], "time_unit": "estimated minutes"})
    subset = [row for row in parser_rows if row["case_id"] in identifiers and row["packet"] == "blind_stratified_120"]
    rows.append({"method": "Deterministic parser", "requests": 24, "trials": len(subset),
        "decision_accuracy": np.mean([int(row["decision_correct"]) for row in subset]),
        "field_accuracy": sum(int(row["field_correct"]) for row in subset) / sum(int(row["field_total"]) for row in subset),
        "unsafe_ready": sum(int(row["unsafe_ready"]) for row in subset),
        "false_clarification": sum(row["validated_decision"] == "clarify" and row["expected_decision"] == "accept" for row in subset),
        "time_value": np.median([float(row["latency_seconds"]) for row in subset]) * 1000, "time_unit": "measured milliseconds"})
    for service in ("deepseek", "qwen", "ernie", "hunyuan"):
        subset = [row for row in trials if row["case_id"] in identifiers and row["packet"] == "blind_stratified_120" and row["service"] == service]
        rows.append({"method": service, "requests": 24, "trials": len(subset),
            "decision_accuracy": np.mean([int(row["decision_correct"]) for row in subset]),
            "field_accuracy": sum(int(row["field_correct"]) for row in subset) / sum(int(row["field_total"]) for row in subset),
            "unsafe_ready": sum(int(row["unsafe_ready"]) for row in subset),
            "false_clarification": sum(int(row["false_clarification"]) for row in subset),
            "time_value": np.median([float(row["latency_seconds"]) for row in subset]), "time_unit": "measured seconds"})
    return rows


def joint_statistics() -> tuple[list[dict], list[dict]]:
    cases = [row for row in read_csv(PROJECT / "results" / "paired_evidence" / "case_scores.csv") if row["packet"] == "blind_original_200"]
    summaries, maps = [], {}
    for service in ("deepseek", "qwen", "ernie", "hunyuan"):
        subset = [row for row in cases if row["service"] == service]
        values = np.array([float(row["legacy_joint_success"]) for row in subset])
        lower, upper = bootstrap_mean(values, [row["text_cluster"] for row in subset])
        summaries.append({"service": service, "requests": len(subset), "joint_success": values.mean(), "ci_low": lower, "ci_high": upper})
        maps[service] = {row["case_id"]: {**row, "legacy_joint_success": float(row["legacy_joint_success"])} for row in subset}
    comparisons = []
    names = list(maps)
    for position, first in enumerate(names):
        for second in names[position + 1:]:
            difference, probability, clusters = paired_test(maps[first], maps[second], "legacy_joint_success")
            comparisons.append({"first": first, "second": second, "difference": difference, "clusters": clusters, "p_value": probability})
    holm(comparisons)
    return summaries, comparisons


def block_sensitivity() -> list[dict]:
    source = read_csv(PROJECT / "results" / "public_validation_r1" / "main" / "window_results.csv")
    rows = []
    for country in ("DE", "AT", "BE", "NL"):
        grouped = {(int(row["window"]), row["method"]): float(row["normalized_cost"]) for row in source if row["country"] == country}
        gains = np.array([grouped[(window, "Global calibration")] - grouped[(window, "Selected shrinkage")] for window in range(12)])
        for length in (1, 2, 3, 4, 6):
            generator = np.random.default_rng(20261011)
            starts = generator.integers(0, 12, size=(3000, int(np.ceil(12 / length))))
            indices = (starts[:, :, None] + np.arange(length)) % 12
            indices = indices.reshape(3000, -1)[:, :12]
            means = gains[indices].mean(axis=1)
            lower, upper = np.quantile(means, [0.025, 0.975])
            rows.append({"country": country, "block_months": length, "mean_gain": gains.mean(), "ci_low": lower, "ci_high": upper})
    return rows


def clarification_alignment() -> list[dict]:
    labels = {row["case_id"]: row for row in read_csv(PROJECT / "data" / "human_r1" / "evaluation_labels.csv")}
    answers = {row["case_id"]: row for row in read_csv(PROJECT / "data" / "api_r1" / "clarification_protocol_v1" / "scripted_answers.csv")}
    patterns = {"region_id": r"region|area|system|区域|地区|省|ERCO|CISO|GD|MISO|ISNE|SWPP",
        "horizon_minutes": r"horizon|minute|hour|时域|分钟|小时|时长",
        "cost_shortfall": r"cost|penalty|ratio|shortfall|c[_ ]?s|成本|罚|缺额|惩罚"}
    rows = []
    for record in load_records("repeated_four_services_v1"):
        if record["case_id"] not in answers:
            continue
        gold = labels[record["case_id"]]
        missing = request_rules(gold["user_request"])["missing_fields"]
        output = record.get("parsed_output") or {}
        question = " ".join(str(output.get(field, "")) for field in ("reason", "explanation"))
        mentioned = [field for field in missing if re.search(patterns[field], question, re.I)]
        rows.append({"case_id": record["case_id"], "service": record["service"], "repeat": record["repeat"],
            "initial_decision": output.get("decision", "invalid"), "required_fields": ";".join(missing),
            "mentioned_required_fields": ";".join(mentioned), "required_count": len(missing), "mentioned_count": len(mentioned),
            "all_required_fields_mentioned": int(bool(missing) and len(mentioned) == len(missing)),
            "clarification_with_all_fields": int(output.get("decision") == "clarify" and bool(missing) and len(mentioned) == len(missing)),
            "confirmation_characters": len(answers[record["case_id"]]["reply"]), "assessment": "explicit field mentions in clarification text"})
    return rows


def legacy_details() -> list[dict]:
    legacy = read_csv(ORIGINAL_DATA / "supplementary_artifacts" / "blind_end_to_end_holdout" / "case_execution_results.csv")
    labels = {row["case_id"]: row for row in read_csv(ORIGINAL_DATA / "supplementary_artifacts" / "llm_benchmark" / "case_labels_blind.csv")}
    records_path = ORIGINAL_DATA / "experiments" / "outputs" / "llm_benchmark" / "blind" / "deepseek" / "model_outputs.jsonl"
    model_records = {}
    for line in records_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        try:
            content = record["provider_response"]["choices"][0]["message"]["content"]
            model_records[record["case_id"]] = json.loads(content)
        except (KeyError, IndexError, json.JSONDecodeError):
            model_records[record["case_id"]] = {}
    rows = []
    for row in legacy:
        if row["mode"] != "ask_v1_1" or row["expected_decision"] not in ("accept", "partial_accept") or row["workflow_status"] == "completed":
            continue
        label = labels[row["case_id"]]
        model = model_records.get(row["case_id"], {})
        audit = model.get("audit_log") or {}
        schema = model.get("study_schema") or {}
        unresolved = row["explicit_default_guard_fields"] or ""
        if not unresolved and model.get("decision") == "clarify":
            absent = [name for name in ("region_id", "horizon_minutes", "cost_shortfall") if schema.get(name) in (None, "")]
            unresolved = ";".join(absent)
        rows.append({"case_id": row["case_id"], "group": row["case_group"], "reference_decision": row["expected_decision"],
            "request": label.get("user_request", label.get("request", "")), "terminal_stage": row["workflow_status"],
            "schema_error": row["schema_error"], "forbidden_variable": row["forbidden_variable"],
            "unresolved_fields": unresolved, "accepted": row["accepted"],
            "llm_decision": model.get("decision", "unavailable"),
            "triggered_rules": ";".join(str(item) for item in audit.get("triggered_rules", [])),
            "recorded_reason": model.get("reason", "workflow stopped before numerical execution")})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    arguments = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    controlled = controlled_calculations()
    if arguments.smoke:
        assert len(controlled) == 9
        assert controlled[0]["cost_difference"] == 0
        assert controlled[-1]["cost_difference"] == 0
        assert all(np.isfinite(row["cost_difference"]) and 0 <= row["coverage_on_reference_target"] <= 1 for row in controlled)
        write_json(RESULTS / "smoke.json", {"passed": True, "cached_decisions": controlled[0]["decisions"], "full_model_training": False})
        print(json.dumps({"smoke_passed": True, "controlled_calculations": len(controlled)}))
        return
    if not (RESULTS / "smoke.json").exists():
        raise ValueError("A successful smoke is required")
    write_csv(RESULTS / "controlled_calculations.csv", controlled)
    write_csv(RESULTS / "matched_24.csv", matched_comparisons())
    summaries, comparisons = joint_statistics()
    write_csv(RESULTS / "joint_summary.csv", summaries)
    write_csv(RESULTS / "joint_tests.csv", comparisons)
    write_csv(RESULTS / "block_length_sensitivity.csv", block_sensitivity())
    clarification = clarification_alignment()
    write_csv(RESULTS / "clarification_field_alignment.csv", clarification)
    summary = []
    for service in ("deepseek", "qwen", "ernie", "hunyuan"):
        subset = [row for row in clarification if row["service"] == service]
        summary.append({"service": service, "trials": len(subset),
            "initial_clarification_rate": np.mean([row["initial_decision"] == "clarify" for row in subset]),
            "field_mention_recall": sum(row["mentioned_count"] for row in subset) / sum(row["required_count"] for row in subset),
            "clarification_with_all_fields": np.mean([row["clarification_with_all_fields"] for row in subset])})
    write_csv(RESULTS / "clarification_alignment_summary.csv", summary)
    write_csv(RESULTS / "legacy_case_details.csv", legacy_details())
    write_json(RESULTS / "usability.json", {"passed": True, "controlled_source_explicit": True,
        "common_reference_objective": True, "matched_requests": 24, "clarification_trials": len(clarification)})
    print(json.dumps({"completed": True, "joint_summary": summaries, "clarification_alignment": summary, "controlled": controlled}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
