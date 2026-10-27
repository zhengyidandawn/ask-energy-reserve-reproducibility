from __future__ import annotations

import csv

from build_substantive_tables import NAMES, table
from workspace_paths import PROJECT


RESULTS = PROJECT / "results" / "online_draft_audit_20261011"
REMAINING = PROJECT / "results" / "remaining_review_questions_20261011"
SERVICES = ("deepseek", "qwen", "ernie", "hunyuan")


def rows(directory, filename):
    with (directory / filename).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def bold_fraction(numerator, denominator):
    value = f"{numerator}/{denominator}"
    return r"\textbf{" + value + "}" if int(numerator) == int(denominator) else value


def main() -> None:
    stages = rows(RESULTS, "stage_summary.csv")
    terminal = {row["service"]: row for row in stages if row["stage"] == "terminal"}
    table("online_draft_quality", "Complete drafts on the matched expert requests.", "lrrrrr",
          ["Service", "Disposition", "Fields", "Valid ready", "Reusable inputs", "Seconds"],
          [[NAMES[service], bold_fraction(terminal[service]["validated_correct"], 120),
            bold_fraction(terminal[service]["field_correct"], 200),
            bold_fraction(terminal[service]["valid_ready"], 20),
            bold_fraction(terminal[service]["retained_entries"], 265),
            f"{float(terminal[service]['median_service_seconds']):.2f}"] for service in SERVICES],
          "Each service has five trials on 24 requests; four are valid accept requests. Counts follow at most one automatic feedback call. Input reuse uses candidate dispositions and supplied fields. Seconds is median total online time. Human approval is required before execution. Higher correct and reusable counts are favorable; bold marks complete observed agreement.")
    table("online_draft_stages", "Initial and final outcomes under automatic feedback.", "llrrrr",
          ["Service", "Stage", "Disposition", "Fields", "Replacements", "Calls"],
          [[NAMES[row["service"]], "Initial" if row["stage"] == "initial" else "Final",
            row["validated_correct"] + "/120", row["field_correct"] + "/200",
            row["required_replacements"], row["online_calls"]] for row in stages],
          "Feedback uses frozen request-parser and validation diagnostics. Independent reference labels enter scoring after the calls. All scheduled trials contribute to both stages; replacements are minimum edits across 265 variable entries.")
    comparisons = rows(RESULTS, "comparator_summary.csv")
    table("online_draft_comparators", "Expert and parser records for the same draft task.", "lrrr",
          ["Method", "Disposition", "Fields", "Reusable inputs"],
          [[row["method"].replace("field-preserving deterministic parser", "Parser"),
            bold_fraction(row["raw_correct"], row["requests"]), bold_fraction(row["field_correct"], row["field_total"]),
            bold_fraction(row["retained_entries"], row["manual_entries"])] for row in comparisons],
          "Experts contribute 24 plans each. The parser preserves supplied fields under all dispositions. Greater reference agreement is favorable; bold identifies complete observed agreement. Service repetition and human plans retain their respective units.")
    table("online_draft_resources", "Online resources including automatic feedback.", "llrrr",
          ["Service", "Currency", "Calls", "Mean fee", r"Input reuse (95\% interval)"],
          [[NAMES[row["service"]], row["currency"], row["online_calls"], f"{float(row['mean_fee_per_trial']):.6f}",
            f"{100*float(terminal[row['service']]['retained_fraction']):.1f} ({100*float(terminal[row['service']]['retained_ci_low']):.1f}--{100*float(terminal[row['service']]['retained_ci_high']):.1f})"]
           for row in rows(RESULTS, "provider_cost_summary.csv")],
          "Fees use recorded tokens and provider-specific tariffs for initial and feedback calls. Input reuse is a percentage; its interval resamples 21 exact request-text clusters. All 120 trials per service retain human verification.")
    table("online_expert_field_difference", "Paired field agreement against the expert average.", "lrrr",
          ["Service", "Difference (percentage points)", r"95\% interval", "Holm $p$"],
          [[NAMES[row["service"]], f"{100*float(row['field_accuracy_difference']):+.1f}",
            f"[{100*float(row['ci_low']):+.1f}, {100*float(row['ci_high']):+.1f}]", f"{float(row['p_holm']):.3f}"]
           for row in rows(RESULTS, "paired_expert_field_difference.csv")],
          "The expert reference averages the three recorded plans within each request. Service trials are averaged within the same request. Differences use correct fields divided by reference-specified fields; 95-percent intervals resample exact text clusters. Holm adjusts four sign-permutation comparisons. The endpoint evaluates draft fields.")
    for endpoint, suffix, title in (("decision_correct", "raw", "Original disposition"), ("validated_correct", "validated", "Validated disposition")):
        selected = [row for row in rows(REMAINING, "parser_paired_comparison.csv") if row["endpoint"] == endpoint]
        body = []
        for row in selected:
            method = row["method"].replace(" / JSON object", " object").replace(" / json_schema", " schema").replace(" / tool_call", " function")
            for service, name in NAMES.items():
                method = method.replace(service, name)
            body.append([method, f"{float(row['interface_accuracy']):.3f}",
                         f"{float(row['mean_paired_gain']):+.3f}",
                         f"[{float(row['ci_low']):+.3f}, {float(row['ci_high']):+.3f}]", f"{float(row['p_holm']):.3f}"])
        table("parser_paired_" + suffix, title + " compared with the parser.", "lrrrr",
              ["Interface", "Accuracy", "Difference", r"95\% interval", "Holm $p$"], body,
              "The same 48 independent requests are paired. Five service trials are averaged within each request. Parser accuracy is 0.771. Differences use interface minus parser; intervals use 20,000 paired resamples. Each endpoint has ten Holm-adjusted comparisons.")
    original_quality = rows(REMAINING, "matched_validation_quality.csv")
    table("matched_validated_quality", "Validated dispositions in the original expert-matched replay.", "lrrr",
          ["Service", "Original", "Validated", "Valid ready"],
          [[NAMES[row["service"]], row["raw_correct"] + "/120", bold_fraction(row["validated_correct"], 120),
            bold_fraction(row["valid_ready"], row["valid_trials"])] for row in original_quality],
          "The 24 requests contain 21 different texts and four valid accept requests. Each service has five trials per request. Every group has zero unsafe-ready trials. Bold identifies complete observed agreement or valid-request completion.")
    old_work = rows(REMAINING, "input_workload_by_class.csv")
    table("input_workload_interval", "Input reuse in the original matched replay.", "lrr",
          ["Service", r"Reusable (\%)", r"95\% interval"],
          [[NAMES[row["service"]], f"{100*float(row['retained_fraction']):.1f}",
            f"[{100*float(row['cluster_ci_low']):.1f}, {100*float(row['cluster_ci_high']):.1f}]"]
           for row in old_work if row["category"] == "all"],
          "Intervals resample 21 exact request-text clusters 5,000 times, retaining all five trials and repeated texts together. The 265 entries comprise dispositions and specified variable fields.")
    table("input_workload_classes", "Input reuse by reference disposition in the original replay.", "lrrrr",
          ["Service", "Accept", "Clarify", "Reject", "Partial accept"],
          [[NAMES[service]] + [f"{100*float(next(row['retained_fraction'] for row in old_work if row['service'] == service and row['category'] == category)):.1f}"
                              for category in ("accept", "clarify", "reject", "partial_accept")] for service in SERVICES],
          "Values are percentages. Class sizes are four, nine, nine and two requests, respectively. Higher reuse leaves more reference-correct draft content. Every input remains subject to verification.")
    sensitivity = rows(RESULTS, "conditional_time_sensitivity.csv")
    body = []
    for service in SERVICES:
        subset = [row for row in sensitivity if row["service"] == service]
        selected = next(row for row in subset if row["review_seconds_per_entry"] == "30" and row["correction_seconds_per_replacement"] == "15" and row["overhead_seconds"] == "30")
        body.append([NAMES[service], f"{float(selected['median_modeled_seconds']):.1f}",
                     f"{100*float(selected['fraction_below_expert_estimate']):.1f}",
                     f"{100*min(float(row['fraction_below_expert_estimate']) for row in subset):.1f}--{100*max(float(row['fraction_below_expert_estimate']) for row in subset):.1f}"])
    table("online_time_sensitivity", "Conditional total preparation time.", "lrrr",
          ["Service", "Example seconds", r"Below reference (\%)", r"Full-grid range (\%)"], body,
          "The example assumes 30 seconds per reviewed entry, 15 per replacement and 30 for other tasks. The grid varies these values over 5 by 3 by 3 settings per service. Online time is measured; expert reference time is self-estimated. Remaining task times are explicit assumptions.")
    print("Online draft and paired-comparison tables generated.")


if __name__ == "__main__":
    main()
