from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import difflib
import hashlib
from itertools import product
import json
from pathlib import Path
import statistics
import time

import jsonschema
import numpy as np

from integrate_r1_evidence import load_records
from prepare_human_evidence import read_csv, write_csv, write_json
from run_six_field_extension import DATA as SIX_DATA, FIELDS, SERVICES, gate
from workspace_paths import PROJECT


DATA = PROJECT / "data" / "substantive_resolution_20261011"
RESULTS = PROJECT / "results" / "substantive_resolution_20261011"


def tariff(record: dict) -> dict:
    service = record["service"]
    usage = record.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens", 0))
    output_tokens = int(usage.get("completion_tokens", 0))
    cached = int(usage.get("prompt_cache_hit_tokens", (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)))
    assert 0 <= cached <= input_tokens
    if service == "deepseek":
        date = datetime.fromisoformat(record["request_started_at"]).astimezone(timezone.utc)
        peak = date.weekday() < 5 and (1 <= date.hour < 4 or 6 <= date.hour < 10)
        multiplier = 2 if peak else 1
        input_rate, output_rate, cache_rate = 0.15 * multiplier, 0.6 * multiplier, 0.003 * multiplier
        currency, model = "USD", "deepseek-flash"
        rate_condition = "published peak schedule" if peak else "published off-peak schedule"
    elif service == "qwen":
        input_rate, output_rate, cache_rate = 2.4, 9.6, 2.4
        currency, model, rate_condition = "CNY", "qwen-max", "mainland standard online inference tariff"
    elif service == "ernie":
        input_rate, output_rate, cache_rate = 0.8, 3.2, 0.2
        currency, model, rate_condition = "CNY", "ernie-4.5-turbo-32k", "online inference tariff"
    else:
        input_rate, output_rate, cache_rate = 1.0, 4.0, 0.25
        currency, model, rate_condition = "CNY", "hy3", "TokenHub online inference tariff"
    returned = str(record.get("returned_model") or "").lower()
    if record.get("status") == "success" and returned != model:
        raise ValueError("Returned model requires a separate tariff: " + returned)
    cost = ((input_tokens - cached) * input_rate + cached * cache_rate + output_tokens * output_rate) / 1e6
    return {"currency": currency, "input_tokens": input_tokens, "cached_tokens": cached,
            "output_tokens": output_tokens, "input_rate": input_rate, "cache_rate": cache_rate,
            "output_rate": output_rate, "price_condition": rate_condition, "list_price_cost": cost}


def pricing() -> list[dict]:
    manifest = {
        "snapshot_date": "2026-10-11", "unit": "published currency per million tokens",
        "deepseek": {"url": "https://api-docs.deepseek.com/quick_start/pricing", "returned_model": "deepseek-flash", "currency": "USD", "off_peak_rates": [0.15, 0.6, 0.003], "peak_multiplier": 2},
        "qwen": {"url": "https://help.aliyun.com/zh/model-studio/model-pricing", "returned_model": "qwen-max", "currency": "CNY", "rates": [2.4, 9.6, 2.4]},
        "ernie": {"url": "https://cloud.baidu.com/doc/qianfan/s/wmh4sv6ya", "returned_model": "ernie-4.5-turbo-32k", "currency": "CNY", "rates": [0.8, 3.2, 0.2]},
        "hunyuan": {"url": "https://cloud.tencent.com/document/product/1823/130055", "returned_model": "hy3", "currency": "CNY", "rates": [1.0, 4.0, 0.25]},
        "interpretation": "list-price estimates from observed usage; account credits and negotiated discounts affect invoices",
    }
    paths = list((DATA / "pricing").glob("*.html"))
    manifest["source_hashes"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    write_json(DATA / "pricing" / "tariffs.json", manifest)
    labels = {row["case_id"] for row in read_csv(PROJECT / "data/human_r1/evaluation_labels.csv") if row["packet"] == "independently_authored_48"}
    records = [record for record in load_records("repeated_four_services_v1") if record["case_id"] in labels]
    trials, summary = [], []
    for record in records:
        trials.append({"service": record["service"], "case_id": record["case_id"], "repeat": record["repeat"],
                       "requested_model": record["requested_model"], "returned_model": record["returned_model"],
                       "request_started_at": record["request_started_at"], **tariff(record)})
    for service in SERVICES:
        subset = [row for row in trials if row["service"] == service]
        assert len(subset) == 240
        summary.append({"service": service, "trials": len(subset), "currency": subset[0]["currency"],
                        **{field: sum(row[field] for row in subset) for field in ("input_tokens", "cached_tokens", "output_tokens", "list_price_cost")},
                        "mean_list_price_cost": statistics.mean(row["list_price_cost"] for row in subset),
                        "basis": "observed model and tokens, archived provider online tariff"})
    write_csv(RESULTS / "provider_cost_trials.csv", trials)
    write_csv(RESULTS / "provider_cost_summary.csv", summary)
    return summary


def workload() -> list[dict]:
    details = read_csv(PROJECT / "results/positive_revision_20261011/review_workload_trials.csv")
    labels = {row["case_id"]: row for row in read_csv(PROJECT / "data/human_r1/evaluation_labels.csv")}
    records = {(row["service"], row["case_id"], str(row["repeat"])): row for row in load_records("repeated_four_services_v1")}
    rows, trials = [], []
    for record in details:
        label = labels[record["case_id"]]
        output = records[(record["service"], record["case_id"], record["repeat"])].get("parsed_output") or {}
        candidate = output.get("study_schema") or {}
        specified = {name: label.get("gold_" + name) for name in ("region_id", "horizon_minutes", "cost_shortfall")
                     if label.get("gold_" + name) not in (None, "")}
        field_replacements = 0
        for name, value in specified.items():
            try:
                correct = str(candidate.get(name)).upper() == str(value).upper() if name == "region_id" else float(candidate.get(name)) == float(value)
            except (ValueError, TypeError):
                correct = False
            field_replacements += not correct
        total = len(specified) + 1
        replacements = field_replacements + int(record["disposition_correction"])
        trials.append({"service": record["service"], "case_id": record["case_id"], "repeat": record["repeat"],
                       "manual_entries": total, "required_replacements": replacements,
                       "retained_entries": total - replacements, "reviewed_entries": total,
                       "expert_estimate_seconds": float(record["expert_estimate_seconds"]),
                       "service_seconds": float(record["service_seconds"]),
                       "reference_input_reduction": (total - replacements) / total})
    for service in SERVICES:
        subset = [row for row in trials if row["service"] == service]
        baseline = sum(row["manual_entries"] for row in subset)
        replacements = sum(row["required_replacements"] for row in subset)
        identifiers = sorted({row["case_id"] for row in subset})
        counts = np.array([sum(row["manual_entries"] for row in subset if row["case_id"] == identifier) for identifier in identifiers])
        retained = np.array([sum(row["retained_entries"] for row in subset if row["case_id"] == identifier) for identifier in identifiers])
        generator = np.random.default_rng(20261011)
        selected = generator.integers(0, len(identifiers), size=(3000, len(identifiers)))
        lower, upper = np.quantile(retained[selected].sum(axis=1) / counts[selected].sum(axis=1), [0.025, 0.975])
        fractions = {}
        for seconds_per_entry in (5, 10, 20, 30):
            fractions[str(seconds_per_entry)] = statistics.mean(
                row["service_seconds"] + row["reviewed_entries"] * seconds_per_entry < row["expert_estimate_seconds"] for row in subset)
        rows.append({"service": service, "trials": len(subset), "manual_entries": baseline,
                     "required_replacements": replacements, "retained_entries": baseline - replacements,
                     "input_reduction": (baseline - replacements) / baseline,
                     "request_mean_reduction": statistics.mean(row["reference_input_reduction"] for row in subset),
                     "request_cluster_ci_low": lower, "request_cluster_ci_high": upper,
                     "review_assumption_fractions": json.dumps(fractions),
                     "interpretation": "reference-label minimum input operations; all entries still reviewed; time scenarios are conditional"})
    write_csv(RESULTS / "input_workload_trials.csv", trials)
    write_csv(RESULTS / "input_workload_summary.csv", rows)
    return rows


def schema(policy: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(policy),
            "properties": {name: {"enum": values} for name, values in policy.items()}}


def maintenance(smoke: bool) -> list[dict]:
    policy = {"region": ["DE", "AT"], "horizon_minutes": [60, 120, 180], "feature_mode": ["full", "history_calendar"],
              "shortfall_weight": [10, 20, 40], "required_coverage": [0.95, 0.975], "reporting": ["standard", "tail"]}
    changes = [("region", "NL"), ("horizon_minutes", 240), ("feature_mode", "observed_temperature"),
               ("shortfall_weight", 80), ("required_coverage", 0.99), ("reporting", "prediction_loss")]
    if smoke:
        changes = changes[:1]
    base = {name: values[0] for name, values in policy.items()}
    conditions = json.loads((SIX_DATA / "cases.json").read_text(encoding="utf-8"))
    rows = []
    for field, value in changes:
        updated = deepcopy(policy)
        updated[field].append(value)
        before = json.dumps(policy, ensure_ascii=False, indent=2).splitlines()
        after = json.dumps(updated, ensure_ascii=False, indent=2).splitlines()
        differences = list(difflib.ndiff(before, after))
        output = DATA / "maintenance" / field
        write_json(output / "before.json", policy)
        write_json(output / "after.json", updated)
        write_json(output / "generated_schema.json", schema(updated))
        write_json(output / "generated_form_choices.json", updated)
        write_json(output / "generated_parser_vocabulary.json", {name: {str(value): value for value in values} for name, values in updated.items()})
        (output / "change.diff").write_text("\n".join(difflib.unified_diff(before, after, fromfile="before.json", tofile="after.json")), encoding="utf-8")
        other_fields = [name for name in policy if name != field]
        combinations = list(product(*(policy[name] for name in other_fields)))[:30]
        new_plans = [{**dict(zip(other_fields, combination)), field: value} for combination in combinations]
        assert len({json.dumps(plan, sort_keys=True) for plan in new_plans}) == 30
        active_schema = json.loads((output / "generated_schema.json").read_text(encoding="utf-8"))
        form_choices = json.loads((output / "generated_form_choices.json").read_text(encoding="utf-8"))
        vocabulary = json.loads((output / "generated_parser_vocabulary.json").read_text(encoding="utf-8"))
        checks = []
        new_value_checks = []
        timings = []
        for plan_index, new_plan in enumerate(new_plans):
            started = time.perf_counter()
            assert not jsonschema.Draft202012Validator(schema(policy)).is_valid(new_plan)
            assert new_plan[field] not in policy[field]
            assert str(new_plan[field]) not in {str(candidate) for candidate in policy[field]}
            jsonschema.validate(new_plan, active_schema)
            assert all(new_plan[name] in values for name, values in form_choices.items())
            parser_record = {name: values[str(new_plan[name])] for name, values in vocabulary.items()}
            assert parser_record == new_plan
            new_value_checks.append({"plan_index": plan_index, "plan": new_plan,
                                     "before": {"form": "rejected", "typed_parser": "rejected", "schema": "rejected"},
                                     "after": {"form": "accepted", "typed_parser": "accepted", "schema": "accepted"}})
            timings.append((time.perf_counter() - started) * 1000)
        for condition in conditions:
            gold = condition["gold"]
            if gold["decision"] == "accept":
                jsonschema.validate(gold["fields"], schema(updated))
            checks.append({"case_id": condition["case_id"], "expected_decision": gold["decision"],
                           "validated_decision": gate(condition["user_request"], {"decision": gold["decision"], "study": {**gold["fields"], "human_authorization_required": True}})["decision"]})
        assert all(row["expected_decision"] == row["validated_decision"] for row in checks)
        write_json(output / "regression.json", {"all_preserved": True, "cases": checks,
                   "new_value_verified_interfaces": ["form", "deterministic typed parser", "generation schema"],
                   "distinct_new_value_plans": len(new_plans), "new_value_checks": new_value_checks,
                   "automation_seconds": [duration / 1000 for duration in timings]})
        rows.append({"changed_field": field, "new_value": value, "policy_files_changed": 1, "policy_values_added": 1,
                     "added_diff_lines": sum(line.startswith("+ ") for line in differences),
                     "removed_diff_lines": sum(line.startswith("- ") for line in differences),
                     "generated_interfaces": 3, "regression_requests": len(checks), "regression_passed": len(checks),
                     "new_value_checks": 90, "distinct_new_value_plans": len(new_plans),
                     "pre_change_rejections": 90, "median_apply_validate_ms": statistics.median(timings),
                     "measurement": "shared declaration edit and automated artifact verification; developer labor is a separate quantity"})
    if not smoke:
        write_csv(RESULTS / "maintenance_changes.csv", rows)
    return rows


def numerical(study: dict, reference: dict) -> dict | None:
    try:
        candidate_path = PROJECT / "data/public_validation_r1/prediction_cache" / f"{study['region']}_w0_H{study['horizon_minutes']}_cal30_K256_req{study['required_coverage']}_f{study['feature_mode']}_cs{study['shortfall_weight']}.npz"
        reference_path = PROJECT / "data/public_validation_r1/prediction_cache" / f"{reference['region']}_w0_H{reference['horizon_minutes']}_cal30_K256_req{reference['required_coverage']}_f{reference['feature_mode']}_cs{reference['shortfall_weight']}.npz"
        if not candidate_path.is_file() or not reference_path.is_file():
            return None
        candidate, correct = np.load(candidate_path), np.load(reference_path)
        common, correct_indices, candidate_indices = np.intersect1d(correct["timestamps"], candidate["timestamps"], return_indices=True)
        target, reserve, correct_reserve = correct["target"][correct_indices], candidate["Selected_shrinkage"][candidate_indices], correct["Selected_shrinkage"][correct_indices]
        weights = reference["shortfall_weight"]
        scales = read_csv(PROJECT / "results/public_validation_r1/main/window_results.csv")
        scale_row = next(row for row in scales if row["country"] == reference["region"] and row["window"] == "0" and row["method"] == "Selected shrinkage")
        scale = float(scale_row["cost_index"]) / float(scale_row["normalized_cost"])
        loss = float(np.mean(reserve + weights * np.maximum(target - reserve, 0)) / scale)
        correct_loss = float(np.mean(correct_reserve + weights * np.maximum(target - correct_reserve, 0)) / scale)
        evidence = {"coverage": float(np.mean(target <= reserve)), "mean_reserve_MW": float(np.mean(reserve)), "cost_index": loss}
        if study.get("reporting") == "tail":
            shortfalls = np.sort(np.maximum(target - reserve, 0))[::-1]
            mass = 0.05 * len(shortfalls)
            integer = int(mass)
            evidence["tail_shortfall_MW"] = float((shortfalls[:integer].sum() + (mass - integer) * shortfalls[integer]) / mass)
        return {"decisions": len(common), "coverage": float(np.mean(target <= reserve)), "reserve_MW": float(np.mean(reserve)),
                "cost_index": loss, "paired_cost_difference": loss - correct_loss,
                "reserve_equal": bool(np.array_equal(reserve, correct_reserve)),
                "reporting_correct": study.get("reporting") == reference["reporting"],
                "reported_evidence": evidence, "report_sha256": hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
                "target_sha256": hashlib.sha256(target.tobytes()).hexdigest(), "reserve_sha256": hashlib.sha256(reserve.tobytes()).hexdigest(),
                "source_sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
                "reference_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest()}
    except (KeyError, ValueError, TypeError):
        return None


def six_fields(smoke: bool) -> list[dict]:
    cases = json.loads((SIX_DATA / "cases.json").read_text(encoding="utf-8"))
    if smoke:
        outcome = numerical(cases[0]["gold"]["fields"], cases[0]["gold"]["fields"])
        assert outcome and outcome["paired_cost_difference"] == 0 and outcome["decisions"] > 0
        return [outcome]
    lookup = {case["case_id"]: case for case in cases}
    trials, fault_rows = [], []
    for path in sorted((SIX_DATA / "initial").glob("*/*/record.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        case = lookup[record["case_id"]]
        checked = record.get("checks", {})
        output = record.get("parsed_output") or {}
        study = output.get("study") or {}
        reference = case["gold"]["fields"]
        row = {"service": record["service"], "case_id": record["case_id"], "repeat": record["repeat"],
               "condition": case["condition"], "expected_decision": case["gold"]["decision"], "status": record["status"],
               "raw_decision_correct": output.get("decision") == case["gold"]["decision"],
               "validated_decision_correct": checked.get("decision") == case["gold"]["decision"],
               "initial_execution_ready": checked.get("execution_ready", False),
               "field_comparison_applicable": case["gold"]["decision"] != "reject",
               "field_replacements": sum(study.get(name) != value for name, value in reference.items()
                                         if value is not None) if case["gold"]["decision"] != "reject" else "",
               "terminal_execution_ready": False,
               "service_seconds": record["latency_seconds"], "additional_replies": 0,
               "input_tokens": (record.get("usage") or {}).get("prompt_tokens", 0),
               "output_tokens": (record.get("usage") or {}).get("completion_tokens", 0),
               "currency": tariff(record)["currency"], "list_price_cost": tariff(record)["list_price_cost"],
               "direct_cost_difference": "", "executed_cost_difference": "", "coverage": "", "reserve_MW": "", "source_sha256": ""}
        if case["gold"]["decision"] == "clarify":
            row["outcome"] = "Clarification"
        elif case["gold"]["decision"] == "reject":
            row["outcome"] = "Boundary rejection"
        elif checked.get("execution_ready"):
            row["outcome"] = "Correct accepted plan"
        elif any(study.get(name) is None for name in FIELDS):
            row["outcome"] = "Incomplete returned plan"
        else:
            row["outcome"] = "Incorrect returned plan"
        if case["gold"]["decision"] == "accept":
            candidate = numerical(study, reference)
            if candidate:
                row["direct_cost_difference"] = candidate["paired_cost_difference"]
            if checked.get("execution_ready"):
                assert candidate and candidate["reserve_equal"] and candidate["reporting_correct"]
                write_json(RESULTS / "executed_outputs" / f"{record['service']}_{case['case_id']}_{record['repeat']}.json",
                           {"phase": "initial", "source_response_sha256": record["response_sha256"], "study": study, "result": candidate})
                row.update({"terminal_execution_ready": True, "executed_cost_difference": candidate["paired_cost_difference"],
                            "coverage": candidate["coverage"], "reserve_MW": candidate["reserve_MW"], "source_sha256": candidate["source_sha256"]})
        elif "answer" in case:
            confirmation_path = SIX_DATA / "confirmation" / record["service"] / f"{case['case_id']}_{record['repeat']}" / "record.json"
            confirmation = json.loads(confirmation_path.read_text(encoding="utf-8"))
            row["additional_replies"] = 1
            row["service_seconds"] += confirmation["latency_seconds"]
            row["list_price_cost"] += tariff(confirmation)["list_price_cost"]
            row["input_tokens"] += (confirmation.get("usage") or {}).get("prompt_tokens", 0)
            row["output_tokens"] += (confirmation.get("usage") or {}).get("completion_tokens", 0)
            row["terminal_execution_ready"] = confirmation.get("checks", {}).get("execution_ready", False)
            terminal_study = (confirmation.get("parsed_output") or {}).get("study") or {}
            if row["terminal_execution_ready"]:
                reference = lookup["SF-01"]["gold"]["fields"]
                candidate = numerical(terminal_study, reference)
                assert candidate and candidate["reserve_equal"]
                write_json(RESULTS / "executed_outputs" / f"{record['service']}_{case['case_id']}_{record['repeat']}.json",
                           {"phase": "confirmation", "source_response_sha256": confirmation["response_sha256"], "study": terminal_study, "result": candidate})
                row.update({"executed_cost_difference": candidate["paired_cost_difference"], "coverage": candidate["coverage"],
                            "reserve_MW": candidate["reserve_MW"], "source_sha256": candidate["source_sha256"]})
        trials.append(row)
    assert len(trials) == 300
    summary = []
    for service in SERVICES:
        for expected in ("accept", "clarify", "reject"):
            subset = [row for row in trials if row["service"] == service and row["expected_decision"] == expected]
            summary.append({"service": service, "plan_class": expected, "trials": len(subset),
                            "raw_accuracy": statistics.mean(row["raw_decision_correct"] for row in subset),
                            "validated_accuracy": statistics.mean(row["validated_decision_correct"] for row in subset),
                            "initial_executed": sum(row["initial_execution_ready"] for row in subset),
                            "terminal_executed": sum(row["terminal_execution_ready"] for row in subset),
                            "median_service_seconds": statistics.median(row["service_seconds"] for row in subset),
                            "mean_field_replacements": statistics.mean(row["field_replacements"] for row in subset
                                                                       if row["field_comparison_applicable"])
                            if expected != "reject" else "",
                            "currency": subset[0]["currency"], "mean_list_price_cost": statistics.mean(row["list_price_cost"] for row in subset),
                            "numeric_observations": sum(row["executed_cost_difference"] != "" for row in subset)})
    reference = lookup["SF-01"]["gold"]["fields"]
    for condition in cases[:9]:
        output = numerical(condition["gold"]["fields"], reference)
        fault_rows.append({"condition": condition["condition"], **output})
    write_csv(RESULTS / "six_field_trials.csv", trials)
    write_csv(RESULTS / "six_field_summary.csv", summary)
    write_csv(RESULTS / "six_field_consequences.csv", fault_rows)
    outcomes = []
    for service in SERVICES:
        for outcome in sorted({row["outcome"] for row in trials if row["service"] == service}):
            subset = [row for row in trials if row["service"] == service and row["outcome"] == outcome]
            outcomes.append({"service": service, "outcome": outcome, "trials": len(subset),
                             "median_service_seconds": statistics.median(row["service_seconds"] for row in subset),
                             "mean_field_replacements": statistics.mean(row["field_replacements"] for row in subset
                                                                        if row["field_comparison_applicable"])
                             if outcome != "Boundary rejection" else "",
                             "currency": subset[0]["currency"], "mean_list_price_cost": statistics.mean(row["list_price_cost"] for row in subset),
                             "numeric_observations": sum(row["executed_cost_difference"] != "" for row in subset),
                             "additional_replies": sum(row["additional_replies"] for row in subset)})
    write_csv(RESULTS / "six_field_outcome_resources.csv", outcomes)
    by_condition = []
    for case in cases[:9]:
        subset = [row for row in trials if row["case_id"] == case["case_id"]]
        by_condition.append({"condition": case["condition"], "trials": len(subset),
                             "executed": sum(row["initial_execution_ready"] for row in subset),
                             "reserve_MW": numerical(case["gold"]["fields"], case["gold"]["fields"])["reserve_MW"],
                             "field_categories": list(FIELDS)})
    write_json(RESULTS / "six_field_coverage.json", by_condition)
    injections = []
    alternatives = {"region": "AT", "horizon_minutes": 120, "feature_mode": "history_calendar",
                    "shortfall_weight": 40, "required_coverage": 0.975, "reporting": "standard"}
    for path in sorted((SIX_DATA / "initial").glob("*/*/record.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["case_id"] not in ("SF-01", "SF-09") or not record.get("checks", {}).get("execution_ready"):
            continue
        case = lookup[record["case_id"]]
        for field, value in alternatives.items():
            if (field == "reporting") != (record["case_id"] == "SF-09"):
                continue
            candidate = deepcopy(record["parsed_output"])
            candidate["study"][field] = value
            checked = gate(case["user_request"], candidate)
            consequence = numerical(candidate["study"], case["gold"]["fields"])
            assert not checked["execution_ready"] and checked["corrections"] == 1
            injections.append({"service": record["service"], "case_id": record["case_id"], "repeat": record["repeat"],
                               "changed_field": field, "injected_value": value, "source_response_sha256": record["response_sha256"],
                               "source": "one-field fault injected into an actual accepted service response",
                               "blocked": True, "field_replacements": 1,
                               "potential_cost_difference": consequence["paired_cost_difference"] if consequence else "",
                               "potential_coverage": consequence["coverage"] if consequence else "",
                               "required_report_preserved": candidate["study"]["reporting"] == case["gold"]["fields"]["reporting"],
                               "post_validation_numerical_stage": "returned for field confirmation"})
    assert len({row["changed_field"] for row in injections}) == 6
    write_csv(RESULTS / "field_fault_injections.csv", injections)
    injection_summary = []
    for field in FIELDS:
        subset = [row for row in injections if row["changed_field"] == field]
        injection_summary.append({"field": field, "injections": len(subset), "blocked": sum(row["blocked"] for row in subset),
                                  "potential_cost_difference": statistics.mean(row["potential_cost_difference"] for row in subset),
                                  "potential_coverage": statistics.mean(row["potential_coverage"] for row in subset),
                                  "source": "controlled fault injection, separate from natural service-error rates"})
    write_csv(RESULTS / "field_fault_summary.csv", injection_summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--offline-only", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    costs = pricing()
    work = workload()
    changes = maintenance(args.smoke)
    numeric = six_fields(args.smoke) if args.smoke or not args.offline_only else []
    if args.smoke:
        write_json(RESULTS / "analysis_smoke.json", {"passed": True, "providers": len(costs), "matched_workload_trials": 480,
                   "maintenance_smoke_changes": len(changes), "numeric_handoff_verified": bool(numeric)})
    else:
        write_json(RESULTS / "analysis_contract.json", {"provider_specific_pricing": True,
                   "maintenance": "six observed declaration changes with generated interfaces and regression",
                   "human": "minimum reference input changes and conditional review scenarios",
                   "human_time": "participant self-estimates; service latency measured; full analyst workflow remains a distinct measurement",
                   "six_field_source": "author-designed requests and actual service responses, separate from independent request cohort",
                   "no_model_refits": True, "numeric_summary_rows": len(numeric)})
    print(json.dumps({"smoke": args.smoke, "pricing": costs, "workload": work, "maintenance": changes,
                      "six_fields_rows": len(numeric)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
