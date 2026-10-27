from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from itertools import combinations
import json
from pathlib import Path
import sys
import time

import numpy as np

from deterministic_interfaces import deterministic_parse, validate_plan
from prepare_human_evidence import read_csv, write_csv, write_json
from recovery_overlay import overlay_records
from run_paired_services import PROJECT, WORKSPACE
from workspace_paths import FORMAL_DATA, ORIGINAL_DATA

SERVICES = ("deepseek", "qwen", "ernie", "hunyuan")
CLASSES = ("accept", "clarify", "reject", "partial_accept", "invalid")
RESULTS = PROJECT / "results" / "paired_evidence"


def normalize(field: str, value: object) -> object:
    if value in (None, ""):
        return None
    if field == "region_id":
        return str(value).strip().upper()
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def field_accuracy(schema: dict | None, gold: dict) -> tuple[int, int]:
    schema = schema or {}
    correct = total = 0
    for field in ("region_id", "horizon_minutes", "cost_reserve", "cost_shortfall"):
        expected = normalize(field, gold.get("gold_" + field))
        if expected is None:
            continue
        total += 1
        correct += normalize(field, schema.get(field)) == expected
    return correct, total


def bootstrap_mean(values: np.ndarray, clusters: list[str], draws: int = 3000) -> tuple[float, float]:
    grouped = defaultdict(list)
    for cluster, value in zip(clusters, values):
        grouped[cluster].append(float(value))
    totals = np.array([sum(group) for group in grouped.values()])
    counts = np.array([len(group) for group in grouped.values()])
    generator = np.random.default_rng(20261010)
    selected = generator.integers(0, len(totals), size=(draws, len(totals)))
    means = totals[selected].sum(axis=1) / counts[selected].sum(axis=1)
    lower, upper = np.quantile(means, [0.025, 0.975])
    return float(lower), float(upper)


def paired_test(first: dict, second: dict, metric: str) -> tuple[float, float, int]:
    identifiers = sorted(set(first) & set(second))
    grouped = defaultdict(list)
    for identifier in identifiers:
        grouped[first[identifier]["text_cluster"]].append(first[identifier][metric] - second[identifier][metric])
    differences = np.array([sum(values) for values in grouped.values()])
    observed = float(differences.sum())
    generator = np.random.default_rng(20261010)
    permutations = generator.choice([-1, 1], size=(20000, len(differences))) @ differences
    probability = (1 + np.sum(np.abs(permutations) >= abs(observed) - 1e-12)) / 20001
    return observed / len(identifiers), float(probability), len(grouped)


def holm(rows: list[dict]) -> None:
    ordered = sorted(rows, key=lambda row: row["p_value"])
    running = 0.0
    for rank, row in enumerate(ordered):
        running = max(running, min(1.0, row["p_value"] * (len(ordered) - rank)))
        row["p_holm"] = running


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--complete-services-only", action="store_true")
    args = parser.parse_args()
    human = read_csv(PROJECT / "data" / "human_r1" / "evaluation_labels.csv")
    human_map = {row["case_id"]: row for row in human}
    original = read_csv(ORIGINAL_DATA / "supplementary_artifacts" / "llm_benchmark" / "case_labels_blind.csv")
    labels = {}
    import hashlib

    for row in original:
        labels[row["case_id"]] = {**row, "packet": "blind_original_200",
            "text_cluster": hashlib.sha256(row["user_request"].encode("utf-8")).hexdigest()}
    labels.update({row["case_id"]: row for row in human if row["packet"] == "independently_authored_48"})
    source = FORMAL_DATA / "repeated_four_services_v1"
    records = []
    paths = list(source.rglob("record.json"))
    paths.extend(path for root in sorted(source.parent.glob("repeated_hunyuan_resume_*")) for path in root.rglob("record.json"))
    for path in paths:
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    records = overlay_records("repeated_four_services_v1", records)
    archived_record_count = len(records)
    service_counts = Counter(record["service"] for record in records)
    complete_services = [service for service in SERVICES if service_counts[service] == 1240]
    if args.complete_services_only:
        records = [record for record in records if record["service"] in complete_services]
        if len(complete_services) < 2:
            raise ValueError("At least two complete services are required for paired inference")
        observed = Counter((record["service"], record["case_id"]) for record in records)
        if any(count != 5 for count in observed.values()) or len(observed) != 248 * len(complete_services):
            raise ValueError("Complete services do not contain five responses for every frozen request")
    elif not args.allow_partial and len(records) != 4960:
        raise ValueError(f"Expected 4960 formal response records, found {len(records)}")
    rows = []
    for record in records:
        identifier = record["case_id"]
        golds = [labels[identifier]]
        if identifier in human_map and human_map[identifier]["packet"] == "blind_stratified_120":
            golds.append(human_map[identifier])
        for gold in golds:
            output = record.get("parsed_output")
            checks = record.get("checks", {})
            raw_decision = (output or {}).get("decision", "invalid")
            if raw_decision not in CLASSES:
                raw_decision = "invalid"
            gate = validate_plan(gold["user_request"], output, checks.get("numerical_contamination", False))
            correct, total = field_accuracy((output or {}).get("study_schema"), gold)
            usage = record.get("usage") or {}
            expected = gold["expected_decision"]
            rows.append({"case_id": identifier, "packet": gold["packet"], "text_cluster": gold["text_cluster"],
                "service": record["service"], "interface": record["interface"], "repeat": record["repeat"],
                "expected_decision": expected, "raw_decision": raw_decision, "validated_decision": gate["decision"],
                "decision_correct": int(raw_decision == expected), "validated_decision_correct": int(gate["decision"] == expected),
                "legacy_joint_success": int(checks.get("joint_success", False)) if gold["packet"] == "blind_original_200" else "",
                "structural_validity": int(checks.get("schema_completeness", False)),
                "exact_schema_validity": int(checks.get("exact_json_schema_valid", False)),
                "execution_ready": int(gate["execution_ready"]),
                "unsafe_ready": int(gate["execution_ready"] and expected != "accept"),
                "raw_unsafe_acceptance": int(raw_decision == "accept" and expected != "accept"),
                "valid_ready": int(gate["execution_ready"] and expected == "accept"),
                "false_clarification": int(expected == "accept" and gate["decision"] == "clarify"),
                "missed_ambiguity": int(expected == "clarify" and raw_decision == "accept"),
                "field_correct": correct, "field_total": total, "numerical_contamination": int(checks.get("numerical_contamination", False)),
                "latency_seconds": record["latency_seconds"], "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0), "total_tokens": usage.get("total_tokens", 0),
                "status": record["status"], "blocking_rules": ";".join(gate["blocking_rules"])})
    if not rows:
        raise ValueError("No completed formal records")
    write_csv(RESULTS / "trial_scores.csv", rows)
    case_groups = defaultdict(list)
    for row in rows:
        case_groups[(row["packet"], row["service"], row["case_id"])].append(row)
    case_rows = []
    for (packet, service, identifier), subset in sorted(case_groups.items()):
        record = {"packet": packet, "service": service, "case_id": identifier,
            "text_cluster": subset[0]["text_cluster"], "expected_decision": subset[0]["expected_decision"], "observed_repeats": len(subset)}
        for metric in ("decision_correct", "validated_decision_correct", "structural_validity", "exact_schema_validity",
            "execution_ready", "unsafe_ready", "raw_unsafe_acceptance", "valid_ready", "false_clarification", "missed_ambiguity",
            "numerical_contamination", "latency_seconds", "prompt_tokens", "completion_tokens", "total_tokens"):
            record[metric] = float(np.mean([row[metric] for row in subset]))
        record["field_accuracy"] = sum(row["field_correct"] for row in subset) / max(1, sum(row["field_total"] for row in subset))
        record["always_correct"] = int(all(row["decision_correct"] for row in subset))
        record["never_correct"] = int(not any(row["decision_correct"] for row in subset))
        record["mixed_correctness"] = int(bool(any(row["decision_correct"] for row in subset)) and not all(row["decision_correct"] for row in subset))
        record["distinct_decisions"] = len({row["raw_decision"] for row in subset})
        record["same_decision_all_runs"] = int(record["distinct_decisions"] == 1)
        record["legacy_joint_success"] = float(np.mean([row["legacy_joint_success"] for row in subset])) if packet == "blind_original_200" else ""
        case_rows.append(record)
    write_csv(RESULTS / "case_scores.csv", case_rows)
    summary = []
    confusions = []
    for packet in sorted({row["packet"] for row in rows}):
        for service in SERVICES:
            cases = [row for row in case_rows if row["packet"] == packet and row["service"] == service]
            trials = [row for row in rows if row["packet"] == packet and row["service"] == service]
            if not cases:
                continue
            lower, upper = bootstrap_mean(np.array([row["decision_correct"] for row in cases]), [row["text_cluster"] for row in cases])
            accept_n = sum(row["expected_decision"] == "accept" for row in trials)
            clarify_n = sum(row["expected_decision"] == "clarify" for row in trials)
            summary.append({"packet": packet, "service": service, "n_cases": len(cases), "n_trials": len(trials),
                "n_text_clusters": len({row["text_cluster"] for row in cases}),
                "decision_accuracy": float(np.mean([row["decision_correct"] for row in cases])), "accuracy_ci_low": lower, "accuracy_ci_high": upper,
                "validated_accuracy": float(np.mean([row["validated_decision_correct"] for row in cases])),
                "legacy_joint_success": float(np.mean([row["legacy_joint_success"] for row in cases])) if packet == "blind_original_200" else "",
                "structural_validity": float(np.mean([row["structural_validity"] for row in cases])),
                "unsafe_ready_rate": float(np.mean([row["unsafe_ready"] for row in cases])),
                "raw_unsafe_acceptance": float(np.mean([row["raw_unsafe_acceptance"] for row in cases])),
                "valid_completion_readiness": sum(row["valid_ready"] for row in trials) / max(1, accept_n),
                "false_clarification_rate": sum(row["false_clarification"] for row in trials) / max(1, accept_n),
                "missed_ambiguity_rate": sum(row["missed_ambiguity"] for row in trials) / max(1, clarify_n),
                "field_accuracy": sum(row["field_correct"] for row in trials) / max(1, sum(row["field_total"] for row in trials)),
                "always_correct_cases": sum(row["always_correct"] for row in cases), "never_correct_cases": sum(row["never_correct"] for row in cases),
                "mixed_cases": sum(row["mixed_correctness"] for row in cases),
                "same_decision_all_runs": sum(row["same_decision_all_runs"] for row in cases),
                "mean_latency_seconds": float(np.mean([row["latency_seconds"] for row in trials])),
                "median_latency_seconds": float(np.median([row["latency_seconds"] for row in trials])),
                "p95_latency_seconds": float(np.quantile([row["latency_seconds"] for row in trials], 0.95)),
                "mean_prompt_tokens": float(np.mean([row["prompt_tokens"] for row in trials])),
                "mean_completion_tokens": float(np.mean([row["completion_tokens"] for row in trials])),
                "total_tokens": sum(row["total_tokens"] for row in trials),
                "api_failures": sum(row["status"] != "success" for row in trials)})
            counts = Counter((row["expected_decision"], row["raw_decision"]) for row in trials)
            confusions.extend({"packet": packet, "service": service, "expected": expected, "predicted": predicted, "count": counts[(expected, predicted)]}
                for expected in CLASSES[:-1] for predicted in CLASSES)
    write_csv(RESULTS / "service_summary.csv", summary)
    write_csv(RESULTS / "confusion_matrices.csv", confusions)
    comparisons = []
    for packet in sorted({row["packet"] for row in rows}):
        for metric in ("decision_correct", "validated_decision_correct"):
            family = []
            for first, second in combinations(SERVICES, 2):
                first_rows = {row["case_id"]: row for row in case_rows if row["packet"] == packet and row["service"] == first}
                second_rows = {row["case_id"]: row for row in case_rows if row["packet"] == packet and row["service"] == second}
                if not set(first_rows) & set(second_rows):
                    continue
                difference, probability, clusters = paired_test(first_rows, second_rows, metric)
                family.append({"packet": packet, "metric": metric, "first_service": first, "second_service": second,
                    "mean_difference": difference, "paired_text_clusters": clusters, "p_value": probability, "p_holm": 0.0})
            holm(family)
            comparisons.extend(family)
    if comparisons:
        write_csv(RESULTS / "paired_service_tests.csv", comparisons)
    baseline = []
    for gold in human:
        started = time.perf_counter()
        output = deterministic_parse(gold["user_request"])
        elapsed = time.perf_counter() - started
        gate = validate_plan(gold["user_request"], output)
        correct, total = field_accuracy(output.get("study_schema"), gold)
        baseline.append({"case_id": gold["case_id"], "packet": gold["packet"], "expected_decision": gold["expected_decision"],
            "decision": output["decision"], "validated_decision": gate["decision"], "decision_correct": int(output["decision"] == gold["expected_decision"]),
            "execution_ready": int(gate["execution_ready"]), "unsafe_ready": int(gate["execution_ready"] and gold["expected_decision"] != "accept"),
            "field_correct": correct, "field_total": total, "latency_seconds": elapsed,
            "blocking_rules": ";".join(gate["blocking_rules"])})
    write_csv(RESULTS / "deterministic_parser_scores.csv", baseline)
    experts = read_csv(PROJECT / "data" / "human_r1" / "expert_plans_normalized.csv")
    expert_ids = {row["case_id"] for row in experts}
    paired = []
    for expert in sorted({row["expert_id"] for row in experts}):
        subset = [row for row in experts if row["expert_id"] == expert]
        counts = [field_accuracy(row, human_map[row["case_id"]]) for row in subset]
        paired.append({"method": expert, "n_cases": len(subset), "decision_accuracy": np.mean([row["label"] == human_map[row["case_id"]]["expected_decision"] for row in subset]),
            "field_accuracy": sum(correct for correct, total in counts) / max(1, sum(total for correct, total in counts)),
            "execution_ready": sum(row["would_execute"] == "yes" for row in subset), "unsafe_ready": sum(row["would_execute"] == "yes" and human_map[row["case_id"]]["expected_decision"] != "accept" for row in subset),
            "estimated_human_mean_minutes": np.mean([float(row["elapsed_minutes"]) for row in subset]), "measured_API_median_seconds": "", "observed_trials": len(subset)})
    for service in SERVICES:
        subset = [row for row in rows if row["packet"] == "blind_stratified_120" and row["case_id"] in expert_ids and row["service"] == service]
        if not subset:
            continue
        paired.append({"method": service, "n_cases": len({row["case_id"] for row in subset}), "decision_accuracy": np.mean([row["decision_correct"] for row in subset]),
            "field_accuracy": sum(row["field_correct"] for row in subset) / max(1, sum(row["field_total"] for row in subset)),
            "execution_ready": np.mean([row["execution_ready"] for row in subset]) * 24,
            "unsafe_ready": np.mean([row["unsafe_ready"] for row in subset]) * 24,
            "estimated_human_mean_minutes": "", "measured_API_median_seconds": np.median([row["latency_seconds"] for row in subset]), "observed_trials": len(subset)})
    write_csv(RESULTS / "expert_matched_summary.csv", paired)
    write_json(RESULTS / "analysis_manifest.json", {"formal_records": len(records), "complete": len(records) == 4960,
        "bootstrap_draws": 3000, "permutation_draws": 20000, "seed": 20261010,
        "confidence_unit": "exact request text cluster", "repeated_responses_averaged_within_case": True,
        "archived_record_count": archived_record_count, "service_counts": dict(service_counts),
        "complete_services": complete_services, "complete_services_only": args.complete_services_only,
        "multiplicity": "Holm within packet and endpoint over all included service pairs", "human_time_is_estimated": True,
        "billed_cost_not_inferred_from_usage": True, "experts_do_not_show_reduced_classification_errors_relative_to_the_reference_labels": True})
    print(json.dumps({"formal_records": len(records), "complete": len(records) == 4960,
        "service_summary": summary}, ensure_ascii=False, default=float))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
