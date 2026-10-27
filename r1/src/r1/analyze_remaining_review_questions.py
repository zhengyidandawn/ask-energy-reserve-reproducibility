from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from workspace_paths import PROJECT


OUTPUT = PROJECT / "results" / "remaining_review_questions_20261011"
SOURCES = {
    "labels": "data/human_r1/evaluation_labels.csv",
    "experts": "data/human_r1/expert_plans_normalized.csv",
    "interfaces": "results/integrated_r1/interface_scores.csv",
    "parser": "results/integrated_r1/deterministic_external_scores.csv",
    "workload": "results/substantive_resolution_20261011/input_workload_trials.csv",
    "scores": "results/paired_evidence/trial_scores.csv",
}


def read_rows(relative: str) -> list[dict]:
    with (PROJECT / relative).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_rows(directory: Path, filename: str, rows: list[dict]) -> None:
    with (directory / filename).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def ratio_interval(rows: list[dict], numerator: str, denominator: str, draws: int) -> tuple[float, float]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["text_cluster"]].append(row)
    totals = np.array([sum(float(row[numerator]) for row in group) for group in grouped.values()])
    counts = np.array([sum(float(row[denominator]) for row in group) for group in grouped.values()])
    generator = np.random.default_rng(20261011)
    selected = generator.integers(0, len(grouped), size=(draws, len(grouped)))
    lower, upper = np.quantile(totals[selected].sum(axis=1) / counts[selected].sum(axis=1), [0.025, 0.975])
    return float(lower), float(upper)


def parser_comparison(draws: int) -> list[dict]:
    parser = {row["case_id"]: row for row in read_rows(SOURCES["parser"])}
    interfaces = read_rows(SOURCES["interfaces"])
    comparisons = []
    for method in sorted({row["method"] for row in interfaces}):
        trials = [row for row in interfaces if row["method"] == method]
        groups = defaultdict(list)
        for row in trials:
            groups[row["case_id"]].append(row)
        assert len(groups) == 48 and all(len(group) == 5 for group in groups.values())
        assert set(groups) == set(parser)
        for endpoint in ("decision_correct", "validated_correct"):
            interface_values = np.array([np.mean([int(row[endpoint]) for row in groups[identifier]])
                                         for identifier in sorted(groups)])
            parser_values = np.array([int(parser[identifier][endpoint]) for identifier in sorted(groups)])
            differences = interface_values - parser_values
            generator = np.random.default_rng(20261011)
            indices = generator.integers(0, 48, size=(draws, 48))
            lower, upper = np.quantile(differences[indices].mean(axis=1), [0.025, 0.975])
            permutations = generator.choice([-1, 1], size=(draws, 48)) @ differences
            probability = (1 + np.sum(np.abs(permutations) >= abs(differences.sum()) - 1e-12)) / (draws + 1)
            comparisons.append({"method": method, "endpoint": endpoint, "requests": 48,
                "service_trials": len(trials), "parser_requests": len(parser),
                "interface_accuracy": float(interface_values.mean()), "parser_accuracy": float(parser_values.mean()),
                "mean_paired_gain": float(differences.mean()), "ci_low": float(lower), "ci_high": float(upper),
                "p_value": float(probability), "p_holm": 0.0,
                "interface_unsafe_trials": sum(int(row["unsafe_ready"]) for row in trials),
                "parser_unsafe_requests": sum(int(row["unsafe_ready"]) for row in parser.values())})
    for endpoint in ("decision_correct", "validated_correct"):
        family = sorted([row for row in comparisons if row["endpoint"] == endpoint], key=lambda row: row["p_value"])
        running = 0.0
        for rank, row in enumerate(family):
            running = max(running, min(1.0, row["p_value"] * (len(family) - rank)))
            row["p_holm"] = running
    return comparisons


def human_comparison(draws: int) -> tuple[list[dict], list[dict], list[dict]]:
    labels = {row["case_id"]: row for row in read_rows(SOURCES["labels"])}
    inputs = read_rows(SOURCES["workload"])
    for row in inputs:
        row["text_cluster"] = labels[row["case_id"]]["text_cluster"]
        row["expected_decision"] = labels[row["case_id"]]["expected_decision"]
    identifiers = {row["case_id"] for row in inputs}
    assert len(identifiers) == 24
    experts = read_rows(SOURCES["experts"])
    assert len(experts) == 72 and {row["case_id"] for row in experts} == identifiers
    for expert in {row["expert_id"] for row in experts}:
        expert_subset = [row for row in experts if row["expert_id"] == expert]
        assert len(expert_subset) == 24 and {row["case_id"] for row in expert_subset} == identifiers
    expert_correct = sum(row["label"] == labels[row["case_id"]]["expected_decision"] for row in experts)
    scores = [row for row in read_rows(SOURCES["scores"])
              if row["case_id"] in identifiers and row["packet"] == "blind_stratified_120"]
    assert len(scores) == 480
    work, quality, sensitivity = [], [], []
    for service in sorted({row["service"] for row in inputs}):
        subset = [row for row in inputs if row["service"] == service]
        assert len(subset) == 120
        for category in ("all", "accept", "clarify", "reject", "partial_accept"):
            group = [row for row in subset if category == "all" or row["expected_decision"] == category]
            lower, upper = ratio_interval(group, "retained_entries", "manual_entries", draws)
            entries = sum(int(row["manual_entries"]) for row in group)
            retained = sum(int(row["retained_entries"]) for row in group)
            work.append({"service": service, "category": category,
                "requests": len({row["case_id"] for row in group}),
                "distinct_texts": len({row["text_cluster"] for row in group}), "trials": len(group),
                "entries": entries, "replacements": entries - retained, "retained": retained,
                "retained_fraction": retained / entries, "cluster_ci_low": lower, "cluster_ci_high": upper})
        observed = [row for row in scores if row["service"] == service]
        assert len(observed) == 120 and {row["case_id"] for row in observed} == identifiers
        for identifier in identifiers:
            assert sum(row["case_id"] == identifier for row in observed) == 5
        quality.append({"service": service, "requests": 24,
            "distinct_texts": len({row["text_cluster"] for row in subset}), "trials": len(observed),
            "raw_correct": sum(int(row["decision_correct"]) for row in observed),
            "validated_correct": sum(int(row["validated_decision_correct"]) for row in observed),
            "unsafe_ready": sum(int(row["unsafe_ready"]) for row in observed),
            "valid_requests": len({row["case_id"] for row in observed if row["expected_decision"] == "accept"}),
            "valid_trials": sum(row["expected_decision"] == "accept" for row in observed),
            "valid_ready": sum(int(row["valid_ready"]) for row in observed),
            "expert_plans": len(experts), "expert_correct": expert_correct,
            "expert_disposition_accuracy": expert_correct / len(experts),
            "measurement": "archived automated validation; human-assisted final outcomes require direct observation"})
        for review_seconds in (10, 20, 30, 40, 60):
            for correction_seconds in (5, 15, 30):
                for overhead_seconds in (0, 30, 60):
                    modeled = [float(row["service_seconds"]) + review_seconds * int(row["reviewed_entries"])
                               + correction_seconds * int(row["required_replacements"]) + overhead_seconds for row in subset]
                    margins = [float(row["expert_estimate_seconds"]) - duration for row, duration in zip(subset, modeled)]
                    sensitivity.append({"service": service, "review_seconds_per_entry": review_seconds,
                        "correction_seconds_per_replacement": correction_seconds, "overhead_seconds": overhead_seconds,
                        "trials": len(subset), "median_modeled_seconds": float(np.median(modeled)),
                        "median_margin_to_expert_estimate_seconds": float(np.median(margins)),
                        "fraction_below_expert_estimate": float(np.mean(np.array(margins) > 0)),
                        "basis": "assumption sensitivity; expert self-estimates; no measured assisted time"})
    return work, quality, sensitivity


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    arguments = parser.parse_args()
    directory = OUTPUT / "smoke" if arguments.smoke else OUTPUT
    directory.mkdir(parents=True, exist_ok=True)
    comparisons = parser_comparison(100 if arguments.smoke else 20000)
    work, quality, sensitivity = human_comparison(100 if arguments.smoke else 5000)
    write_rows(directory, "parser_paired_comparison.csv", comparisons)
    write_rows(directory, "input_workload_by_class.csv", work)
    write_rows(directory, "matched_validation_quality.csv", quality)
    write_rows(directory, "conditional_total_time_sensitivity.csv", sensitivity)
    manifest = {"source_sha256": {name: hashlib.sha256((PROJECT / relative).read_bytes()).hexdigest()
                for name, relative in SOURCES.items()}, "smoke": arguments.smoke, "hosted_calls": 0,
                "interface_requests": 48, "expert_requests": 24, "expert_distinct_texts": 21,
                "comparisons": len(comparisons), "workload_rows": len(work), "quality_rows": len(quality),
                "conditional_scenarios": len(sensitivity), "automated_quality_and_human_outcomes_distinct": True,
                "time_scenarios_are_assumptions": True}
    (directory / "analysis_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
