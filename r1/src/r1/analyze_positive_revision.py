from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from workspace_paths import PROJECT


OUTPUT = PROJECT / "results" / "positive_revision_20261011"


def read_rows(relative: str) -> list[dict]:
    with (PROJECT / relative).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def save_rows(name: str, rows: list[dict]) -> None:
    with (OUTPUT / name).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def block_interval(values: np.ndarray, length: int, draws: int, alpha: float = 0.05) -> tuple[float, float]:
    generator = np.random.default_rng(20261011)
    starts = generator.integers(0, len(values), size=(draws, int(np.ceil(len(values) / length))))
    indices = ((starts[:, :, None] + np.arange(length)) % len(values)).reshape(draws, -1)[:, :len(values)]
    lower, upper = np.quantile(values[indices].mean(axis=1), [alpha / 2, 1 - alpha / 2])
    return float(lower), float(upper)


def reliability(draws: int) -> tuple[list[dict], list[dict]]:
    rows = read_rows("results/evidence_completion_20261011/reliability/main/window_results.csv")
    rows = [row for row in rows if row["margin_applied"] == "True"]
    assert len(rows) == 256
    assert all(float(row["coverage"]) >= 0.95 for row in rows)
    summaries, intervals = [], []
    for country in ("DE", "AT", "BE", "NL"):
        country_rows = [row for row in rows if row["country"] == country]
        methods = sorted({row["method"] for row in country_rows})
        for method in methods:
            subset = [row for row in country_rows if row["method"] == method]
            assert len(subset) == 8
            summaries.append({"country": country, "method": method, "windows": len(subset),
                "minimum_coverage": min(float(row["coverage"]) for row in subset),
                **{field: float(np.mean([float(row[field]) for row in subset])) for field in
                   ("coverage", "normalized_cost", "mean_reserve_MW", "shortfall_CVaR95_MW", "base_fit_seconds")}})
        lookup = {(int(row["window"]), row["method"]): row for row in country_rows}
        for comparator in methods:
            if comparator == "Selected shrinkage":
                continue
            for metric in ("normalized_cost", "shortfall_CVaR95_MW"):
                gains = np.array([float(lookup[(window, comparator)][metric]) -
                                  float(lookup[(window, "Selected shrinkage")][metric]) for window in range(8)])
                for length in (1, 2, 3, 4):
                    lower, upper = block_interval(gains, length, draws)
                    family_lower, family_upper = block_interval(gains, length, draws, 0.05 / 4)
                    intervals.append({"country": country, "comparator": comparator, "metric": metric,
                        "block_months": length, "windows": 8, "draws": draws,
                        "mean_gain": float(gains.mean()), "ci_low": lower, "ci_high": upper,
                        "four_country_ci_low": family_lower, "four_country_ci_high": family_upper})
    return summaries, intervals


def workload() -> tuple[list[dict], list[dict]]:
    experts = read_rows("data/human_r1/expert_plans_normalized.csv")
    identifiers = {row["case_id"] for row in experts}
    estimates = {identifier: float(np.mean([float(row["elapsed_minutes"]) * 60
                for row in experts if row["case_id"] == identifier])) for identifier in identifiers}
    trials = read_rows("results/paired_evidence/trial_scores.csv")
    matched = [row for row in trials if row["case_id"] in identifiers and row["packet"] == "blind_stratified_120"]
    details, summaries = [], []
    for row in matched:
        budget = estimates[row["case_id"]] - float(row["latency_seconds"])
        details.append({"service": row["service"], "case_id": row["case_id"], "repeat": row["repeat"],
            "reference_fields": int(row["field_total"]), "correct_fields": int(row["field_correct"]),
            "field_corrections": int(row["field_total"]) - int(row["field_correct"]),
            "disposition_correction": 1 - int(row["decision_correct"]),
            "incorrect_ready": int(row["unsafe_ready"]), "service_seconds": float(row["latency_seconds"]),
            "expert_estimate_seconds": estimates[row["case_id"]], "review_budget_seconds": budget,
            "budget_basis": "expert self-estimate minus measured service return; derived threshold"})
    for service in ("deepseek", "qwen", "ernie", "hunyuan"):
        subset = [row for row in details if row["service"] == service]
        assert len(subset) == 120
        summaries.append({"service": service, "requests": 24, "trials": len(subset),
            "reference_fields": sum(row["reference_fields"] for row in subset),
            "correct_fields": sum(row["correct_fields"] for row in subset),
            "field_corrections": sum(row["field_corrections"] for row in subset),
            "disposition_corrections": sum(row["disposition_correction"] for row in subset),
            "incorrect_ready": sum(row["incorrect_ready"] for row in subset),
            "median_service_seconds": float(np.median([row["service_seconds"] for row in subset])),
            "mean_review_budget_seconds": float(np.mean([row["review_budget_seconds"] for row in subset])),
            "median_review_budget_seconds": float(np.median([row["review_budget_seconds"] for row in subset])),
            "positive_budget_fraction": float(np.mean([row["review_budget_seconds"] > 0 for row in subset]))})
    return summaries, details


def accounting() -> list[dict]:
    scores = read_rows("results/paired_evidence/trial_scores.csv")
    lookup = {(row["service"], row["case_id"], row["repeat"]): row for row in scores
              if row["packet"] == "independently_authored_48"}
    replay = read_rows("results/paired_public_execution/paired_trials.csv")
    rows = []
    for service in ("deepseek", "qwen", "ernie", "hunyuan"):
        for stage in ("Authorized calculation", "Returned preparation"):
            subset = [row for row in replay if row["service"] == service and
                      (row["execution_ready"] == "1") == (stage == "Authorized calculation")]
            observed = [lookup[(row["service"], row["case_id"], row["repeat"])] for row in subset]
            differences = [float(row["validated_cost_difference"]) for row in subset if row["validated_cost_difference"]]
            rows.append({"service": service, "stage": stage, "trials": len(subset),
                "median_service_seconds": float(np.median([float(row["latency_seconds"]) for row in observed])),
                "mean_input_tokens": float(np.mean([float(row["prompt_tokens"]) for row in observed])),
                "mean_output_tokens": float(np.mean([float(row["completion_tokens"]) for row in observed])),
                "mean_field_corrections": float(np.mean([int(row["field_total"]) - int(row["field_correct"]) for row in observed])),
                "numerical_cost_observations": len(differences),
                "mean_numerical_cost_difference": float(np.mean(differences)) if differences else "",
                "numerical_stage": "executed" if differences else "preparation"})
    return rows


def budget_costs() -> list[dict]:
    scores = read_rows("results/paired_evidence/trial_scores.csv")
    rows = []
    for service in ("deepseek", "qwen", "ernie", "hunyuan"):
        subset = [row for row in scores if row["service"] == service and row["packet"] == "independently_authored_48"]
        input_tokens = sum(float(row["prompt_tokens"]) for row in subset)
        output_tokens = sum(float(row["completion_tokens"]) for row in subset)
        for input_rate, output_rate in ((1.0, 1.0), (2.4, 9.6), (5.0, 20.0)):
            rows.append({"service": service, "trials": len(subset), "input_tokens": input_tokens,
                "output_tokens": output_tokens, "input_CNY_per_million": input_rate,
                "output_CNY_per_million": output_rate,
                "mean_budget_CNY": (input_tokens * input_rate + output_tokens * output_rate) / 1e6 / len(subset),
                "total_budget_CNY": (input_tokens * input_rate + output_tokens * output_rate) / 1e6,
                "rate_basis": "common rate sensitivity; 2.4/9.6 is published mainland qwen-max tariff"})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summaries, intervals = reliability(64 if args.smoke else 3000)
    workers, detail = workload()
    stages = accounting()
    costs = budget_costs()
    assert sum(row["trials"] for row in stages) == 440
    assert sum(row["numerical_cost_observations"] for row in stages) == 266
    assert all(np.isfinite(row["mean_review_budget_seconds"]) for row in workers)
    assert all(row["mean_budget_CNY"] > 0 for row in costs)
    if args.smoke:
        print(json.dumps({"smoke": "passed", "reliability_rows": len(summaries), "workload_trials": len(detail),
                          "accounted_trials": 440, "analysis": "archived records and cached results"}))
        return
    for name, result in (("frozen_policy_summary.csv", summaries), ("frozen_paired_intervals.csv", intervals),
                         ("review_workload_summary.csv", workers), ("review_workload_trials.csv", detail),
                         ("execution_resource_accounting.csv", stages), ("api_budget_sensitivity.csv", costs)):
        save_rows(name, result)
    (OUTPUT / "analysis_contract.json").write_text(json.dumps({
        "smoke_passed": True, "hosted_calls": 0, "model_refits": 0,
        "reliability": "256 frozen-margin policy-window outcomes; eight chronological windows per method-country",
        "confidence_interval": "circular moving-block bootstrap; 3000 draws; block lengths 1,2,3,4 months",
        "human_time": "self-estimated expert preparation; review thresholds derived per request",
        "service_time": "measured return latency; case-paired with expert estimates",
        "field_workload": "reference-labelled fields requiring correction; 480 matched service trials",
        "cost": "token-based rate sensitivity; quoted tariff applies to mainland qwen-max",
        "retention": "all recorded observations in the stated denominators"}, indent=2), encoding="utf-8")
    print(json.dumps({"analysis": "complete", "output": str(OUTPUT), "workload": workers}, ensure_ascii=False))


if __name__ == "__main__":
    main()
