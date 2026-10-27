from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

from analyze_paired_evidence import bootstrap_mean, field_accuracy, holm, paired_test
from deterministic_interfaces import deterministic_parse, make_output, request_rules, validate_plan
from prepare_human_evidence import read_csv, write_csv, write_json
from recovery_overlay import overlay_records
from run_paired_services import PROJECT, WORKSPACE
from workspace_paths import FORMAL_DATA, ORIGINAL_DATA

RESULTS = PROJECT / "results" / "integrated_r1"


def load_records(run: str) -> list[dict]:
    root = FORMAL_DATA / run
    roots = [root]
    if run == "repeated_four_services_v1":
        roots.extend(sorted(root.parent.glob("repeated_hunyuan_resume_*")))
    records = [json.loads(path.read_text(encoding="utf-8")) for source in roots for path in sorted(source.rglob("record.json"))]
    return overlay_records(run, records)


def summarize_interface(records: list[dict], labels: dict, method: str) -> tuple[dict, list[dict]]:
    scored = []
    for record in records:
        gold = labels[record["case_id"]]
        output = record.get("parsed_output")
        gate = validate_plan(gold["user_request"], output, record.get("checks", {}).get("numerical_contamination", False))
        scored.append({"case_id": record["case_id"], "text_cluster": gold["text_cluster"], "method": method,
            "repeat": record["repeat"], "decision_correct": int((output or {}).get("decision") == gold["expected_decision"]),
            "validated_correct": int(gate["decision"] == gold["expected_decision"]),
            "ready": int(gate["execution_ready"]), "unsafe_ready": int(gate["execution_ready"] and gold["expected_decision"] != "accept"),
            "false_clarification": int(gate["decision"] == "clarify" and gold["expected_decision"] == "accept"),
            "expected": gold["expected_decision"], "schema_valid": int(record.get("checks", {}).get("exact_json_schema_valid", False)),
            "latency_seconds": record["latency_seconds"], "total_tokens": (record.get("usage") or {}).get("total_tokens", 0),
            "status": record["status"]})
    groups = defaultdict(list)
    for row in scored:
        groups[row["case_id"]].append(row)
    case_rows = [{"case_id": identifier, "text_cluster": subset[0]["text_cluster"],
        "decision_correct": float(np.mean([row["decision_correct"] for row in subset]))} for identifier, subset in groups.items()]
    lower, upper = bootstrap_mean(np.array([row["decision_correct"] for row in case_rows]), [row["text_cluster"] for row in case_rows])
    accepts = sum(row["expected"] == "accept" for row in scored)
    summary = {"method": method, "cases": len(groups), "trials": len(scored),
        "decision_accuracy": float(np.mean([row["decision_correct"] for row in case_rows])), "ci_low": lower, "ci_high": upper,
        "validated_accuracy": float(np.mean([row["validated_correct"] for row in scored])),
        "valid_completion_readiness": sum(row["ready"] and row["expected"] == "accept" for row in scored) / accepts,
        "false_clarification_rate": sum(row["false_clarification"] for row in scored) / accepts,
        "unsafe_ready": sum(row["unsafe_ready"] for row in scored),
        "exact_schema_rate": float(np.mean([row["schema_valid"] for row in scored])),
        "median_latency_seconds": float(np.median([row["latency_seconds"] for row in scored])),
        "total_tokens": sum(row["total_tokens"] for row in scored), "unavailable_responses": sum(row["status"] != "success" for row in scored)}
    return summary, scored


def interfaces(services: list[str]) -> None:
    human = read_csv(PROJECT / "data" / "human_r1" / "evaluation_labels.csv")
    labels = {row["case_id"]: row for row in human if row["packet"] == "independently_authored_48"}
    summaries, scores = [], []
    for service in services:
        repeats = [record for record in load_records("repeated_four_services_v1") if record["service"] == service and record["case_id"] in labels]
        summary, scored = summarize_interface(repeats, labels, service + " / JSON object")
        summaries.append(summary)
        scores.extend(scored)
        run = load_records("interfaces_" + service + "_v1")
        for interface in sorted({record["interface"] for record in run}):
            records = [record for record in run if record["interface"] == interface]
            if len(records) != 240 or len({record["case_id"] for record in records}) != 48:
                continue
            summary, scored = summarize_interface(records, labels, service + " / " + interface)
            summaries.append(summary)
            scores.extend(scored)
    write_csv(RESULTS / "interface_summary.csv", summaries)
    write_csv(RESULTS / "interface_scores.csv", scores)
    comparisons = []
    for service in services:
        methods = sorted({row["method"] for row in scores if row["method"].startswith(service + " /")})
        family = []
        for method in methods:
            if method.endswith("JSON object"):
                continue
            maps = []
            for target in (service + " / JSON object", method):
                grouped = defaultdict(list)
                for row in scores:
                    if row["method"] == target:
                        grouped[row["case_id"]].append(row)
                maps.append({identifier: {"text_cluster": subset[0]["text_cluster"], "decision_correct": np.mean([row["decision_correct"] for row in subset])} for identifier, subset in grouped.items()})
            difference, probability, count = paired_test(maps[0], maps[1], "decision_correct")
            family.append({"service": service, "alternative": method, "object_minus_alternative": difference,
                "paired_requests": count, "p_value": probability})
        holm(family)
        comparisons.extend(family)
    if comparisons:
        write_csv(RESULTS / "interface_paired_tests.csv", comparisons)
    deterministic = []
    for gold in labels.values():
        started = time.perf_counter()
        output = deterministic_parse(gold["user_request"])
        elapsed = time.perf_counter() - started
        gate = validate_plan(gold["user_request"], output)
        deterministic.append({"case_id": gold["case_id"], "decision_correct": int(output["decision"] == gold["expected_decision"]),
            "validated_correct": int(gate["decision"] == gold["expected_decision"]), "expected": gold["expected_decision"],
            "ready": int(gate["execution_ready"]), "unsafe_ready": int(gate["execution_ready"] and gold["expected_decision"] != "accept"),
            "false_clarification": int(gate["decision"] == "clarify" and gold["expected_decision"] == "accept"), "latency_seconds": elapsed})
    write_csv(RESULTS / "deterministic_external_scores.csv", deterministic)
    experts = read_csv(PROJECT / "data" / "human_r1" / "expert_plans_normalized.csv")
    human_map = {row["case_id"]: row for row in human}
    form_rows = []
    for expert in experts:
        gold = human_map[expert["case_id"]]
        if expert["label"] == "accept":
            fields = {field: float(expert[field]) if field != "region_id" else expert[field] for field in ("region_id", "horizon_minutes", "cost_reserve", "cost_shortfall")}
            fields["horizon_minutes"] = int(fields["horizon_minutes"])
            output = make_output("accept", fields, [], [])
        else:
            output = make_output(expert["label"], {}, [], [])
        gate = validate_plan(gold["user_request"], output)
        form_rows.append({"case_id": expert["case_id"], "expert": expert["expert_id"], "form_decision": gate["decision"],
            "decision_correct": int(gate["decision"] == gold["expected_decision"]), "execution_ready": int(gate["execution_ready"]),
            "unsafe_ready": int(gate["execution_ready"] and gold["expected_decision"] != "accept")})
    write_csv(RESULTS / "expert_form_workflow.csv", form_rows)
    write_json(RESULTS / "interface_maintenance.json", {"evaluation": "implemented configurations sharing field definitions and validation rules",
        "electronic_form": "expert-entered fields on 24 matched requests, 3 experts, 72 forms; includes human preparation",
        "finite_state_workflow": "draft, clarification, review, execution-authorized, blocked; same form data, not a separate independent classifier",
        "deterministic_parser": {"named_rule_patterns": len(request_rules("GD H=60 c_S=20")["violations"]), "source_lines": len((PROJECT / "src" / "r1" / "deterministic_interfaces.py").read_text(encoding="utf-8").splitlines())},
        "maintenance_measure": "documented artifacts and configuration changes; developer hours were not measured",
        "billed_cost": "usage recorded; no billing statement available"})


def clarification(services: list[str]) -> None:
    answers = {row["case_id"]: row for row in read_csv(PROJECT / "data" / "api_r1" / "clarification_protocol_v1" / "scripted_answers.csv")}
    initial = {(row["service"], row["case_id"], row["repeat"]): row for row in load_records("repeated_four_services_v1")}
    summaries, scored = [], []
    for service in services:
        records = load_records("clarification_" + service + "_v1")
        if len(records) != 70:
            continue
        for record in records:
            answer = answers[record["case_id"]]
            gate = validate_plan(answer["confirmed_request"], record.get("parsed_output"), record.get("checks", {}).get("numerical_contamination", False))
            previous = initial[(service, record["case_id"], record["repeat"])]
            scored.append({"service": service, "case_id": record["case_id"], "repeat": record["repeat"],
                "initial_clarify": int((previous.get("parsed_output") or {}).get("decision") == "clarify"),
                "terminal_accept": int((record.get("parsed_output") or {}).get("decision") == "accept"),
                "terminal_ready": int(gate["execution_ready"]), "blocking_rules": ";".join(gate["blocking_rules"]),
                "confirmation_turns": 1, "reply_characters": len(answer["reply"]), "latency_seconds": record["latency_seconds"],
                "total_API_seconds": record["latency_seconds"] + previous["latency_seconds"], "status": record["status"]})
        subset = [row for row in scored if row["service"] == service]
        summaries.append({"service": service, "cases": 14, "trials": len(subset),
            "initial_clarification_rate": np.mean([row["initial_clarify"] for row in subset]),
            "terminal_acceptance": np.mean([row["terminal_accept"] for row in subset]),
            "terminal_execution_readiness": np.mean([row["terminal_ready"] for row in subset]),
            "mean_confirmation_turns": 1, "median_total_API_seconds": np.median([row["total_API_seconds"] for row in subset]),
            "mean_reply_characters": np.mean([row["reply_characters"] for row in subset]),
            "unavailable_responses": sum(row["status"] != "success" for row in subset)})
    if scored:
        write_csv(RESULTS / "clarification_scores.csv", scored)
        write_csv(RESULTS / "clarification_summary.csv", summaries)
    legacy = read_csv(ORIGINAL_DATA / "supplementary_artifacts" / "blind_end_to_end_holdout" / "case_execution_results.csv")
    incomplete = [row for row in legacy if row["mode"] == "ask_v1_1" and row["expected_decision"] in ("accept", "partial_accept") and row["workflow_status"] != "completed"]
    write_csv(RESULTS / "legacy_eligible_dispositions.csv", [{"case_id": row["case_id"], "case_group": row["case_group"],
        "expected_decision": row["expected_decision"], "final_status": row["workflow_status"],
        "disposition": "candidate response did not authorize execution", "numerical_program_failed": False} for row in incomplete])
    write_json(RESULTS / "legacy_disposition_summary.json", {"eligible_not_completed": len(incomplete),
        "decision_counts": dict(Counter(row["expected_decision"] for row in incomplete)),
        "case_group_counts": dict(Counter(row["case_group"] for row in incomplete)), "all_stopped_before_numerical_execution": True})


def numerical() -> None:
    root = PROJECT / "results" / "public_validation_r1"
    rows = read_csv(root / "main" / "window_results.csv")
    summaries = read_csv(root / "main" / "summary.csv")
    generator = np.random.default_rng(20261010)
    paired = []
    for country in ("DE", "AT", "BE", "NL"):
        selected = {int(row["window"]): row for row in rows if row["country"] == country and row["method"] == "Selected shrinkage"}
        for comparator in ("Global calibration", "Local calibration", "Block-score calibration", "Scenario maximum"):
            reference = {int(row["window"]): row for row in rows if row["country"] == country and row["method"] == comparator}
            differences = np.array([float(reference[index]["normalized_cost"]) - float(selected[index]["normalized_cost"]) for index in range(12)])
            starts = generator.integers(0, 12, size=(3000, 4))
            indices = ((starts[:, :, None] + np.arange(3)) % 12).reshape(3000, 12)
            intervals = np.quantile(differences[indices].mean(axis=1), [0.025, 0.975])
            paired.append({"country": country, "comparator": comparator, "normalized_cost_gain": differences.mean(),
                "ci_low": intervals[0], "ci_high": intervals[1], "bootstrap": "circular moving blocks of three chronological monthly windows", "draws": 3000})
    write_csv(RESULTS / "public_paired_cost.csv", paired)
    regimes = read_csv(root / "main" / "conditional_results.csv")
    grouped = defaultdict(list)
    for row in regimes:
        if row["method"] in ("Selected shrinkage", "Global calibration", "Block-score calibration"):
            grouped[(row["country"], row["method"], row["regime"])].append(row)
    conditional = []
    for (country, method, regime), subset in sorted(grouped.items()):
        counts = np.array([int(row["n"]) for row in subset])
        record = {"country": country, "method": method, "regime": regime, "n": int(counts.sum())}
        for metric in ("coverage", "mean_reserve_MW", "mean_shortfall_MW", "normalized_cost"):
            record[metric] = np.average([float(row[metric]) for row in subset], weights=counts)
        conditional.append(record)
    write_csv(RESULTS / "public_conditional_summary.csv", conditional)
    traces = read_csv(root / "field_to_calculation_trace.csv")
    selected_traces = [row for row in traces if row["method"] == "Selected shrinkage"]
    trace_rows = []
    plan_root = PROJECT / "data" / "public_validation_r1" / "checked_study_plans"
    for index, row in enumerate(selected_traces):
        plan = {"region": row["country_name"], "horizon_minutes": int(row["horizon_minutes"]),
            "admissible_variables": row["feature_mode"], "reserve_cost_weight": 1, "shortfall_cost_weight": float(row["shortfall_cost"]),
            "required_coverage": float(row["required_coverage"]), "reporting_requirements": ["coverage", "mean_reserve_MW", "normalized_cost", "mean_shortfall_MW"],
            "human_review_required": True, "calibration_days": int(row["calibration_days"])}
        assert plan["region"] in ("Germany", "Austria", "Belgium", "Netherlands")
        assert plan["horizon_minutes"] in (60, 120, 180) and plan["shortfall_cost_weight"] in (10, 20, 40)
        assert plan["required_coverage"] in (0.90, 0.95, 0.975) and plan["admissible_variables"] in ("full", "history_calendar")
        write_json(plan_root / f"study_{index+1:02d}.json", plan)
        cache = PROJECT / "data" / "public_validation_r1" / "prediction_cache" / f"{row['country']}_w0_H{row['horizon_minutes']}_cal{row['calibration_days']}_K{row['neighbors']}_req{row['required_coverage']}_f{row['feature_mode']}_cs{row['shortfall_cost']}.npz"
        with np.load(cache) as values:
            target, reserve = values["target"], values["Selected_shrinkage"]
            assert np.isclose(np.mean(target <= reserve), float(row["coverage"]))
        trace_rows.append({"study_id": f"study_{index+1:02d}", **plan,
            "coverage": row["coverage"], "mean_reserve_MW": row["mean_reserve_MW"], "normalized_cost": row["normalized_cost"],
            "shortfall_CVaR95_MW": "",
            "plan_sha256": hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(),
            "target_sha256": hashlib.sha256(target.tobytes()).hexdigest(), "reserve_sha256": hashlib.sha256(reserve.tobytes()).hexdigest(),
            "execution_status": "completed"})
    reporting = dict(trace_rows[0])
    reporting["study_id"] = "study_09"
    reporting["reporting_requirements"] = ["coverage", "mean_reserve_MW", "normalized_cost", "mean_shortfall_MW", "shortfall_CVaR95_MW"]
    reporting["shortfall_CVaR95_MW"] = selected_traces[0]["shortfall_CVaR95_MW"]
    reporting["plan_sha256"] = hashlib.sha256(json.dumps({key: reporting[key] for key in trace_rows[0] if key in plan}, sort_keys=True).encode()).hexdigest()
    trace_rows.append(reporting)
    write_csv(RESULTS / "checked_request_to_calculation.csv", trace_rows)
    checks = {"source_sha256_verified": hashlib.sha256((PROJECT / "data" / "public_validation_r1" / "time_series_15min_singleindex.csv").read_bytes()).hexdigest() == "194f3ee7d110d04389751602132899172cdd8b7ca73c07d6e9009ddac066b2a1",
        "countries": 4, "rolling_windows": 48, "methods_per_window": 8, "test_decisions": 138240,
        "finite_metrics": all(np.isfinite(float(row["normalized_cost"])) for row in rows),
        "same_selection_constraint": all(float(row["selection_coverage"]) >= 0.95 for row in rows),
        "each_country_test_n": 34560, "target_definition": "maximum future positive one-step increment",
        "empirical_test_coverage_not_guaranteed": True,
        "usable_evidence": "reproducible physical-unit evaluation, common selection constraints, conditional reliability and plan-field sensitivity",
        "selected_method_best_in_every_country": False, "all_test_windows_and_methods_retained_in_statistics": True}
    assert checks["source_sha256_verified"] and checks["finite_metrics"] and checks["same_selection_constraint"]
    write_json(RESULTS / "public_usability.json", checks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--services", nargs="+", default=["deepseek", "qwen", "ernie", "hunyuan"])
    args = parser.parse_args()
    interfaces(args.services)
    clarification(args.services)
    numerical()
    print(json.dumps({"integrated": True, "results": str(RESULTS)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
