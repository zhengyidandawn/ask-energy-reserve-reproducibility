from __future__ import annotations

import csv
from pathlib import Path

from workspace_paths import PROJECT


RESULTS = PROJECT / "results" / "positive_revision_20261011"
TABLES = PROJECT / "elsarticle_unmark" / "sections" / "r1_tables"
if not (PROJECT / "elsarticle_unmark").is_dir():
    TABLES = PROJECT / "results" / "positive_revision_20261011" / "article" / "tables"
NAMES = {"deepseek": "DeepSeek", "qwen": "Qwen", "ernie": "ERNIE", "hunyuan": "Hunyuan"}
METHODS = {"Block-score calibration": "Block maximum", "Global calibration": "Global",
    "Local calibration": "Local", "Quantile predictor": "Quantile predictor",
    "Scenario maximum": "Scenario maximum", "Scenario quantile": "Scenario quantile",
    "Selected shrinkage": "Selected local", "Static quantile": "Static quantile"}


def rows(name: str) -> list[dict]:
    with (RESULTS / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def table(name: str, caption: str, columns: str, headings: list[str], body: list[list[str]], note: str) -> None:
    lines = [r"\begin{table}[!htbp]", r"\centering", r"\footnotesize",
        r"\caption{" + caption + "}", r"\label{tab:r1_" + name + "}",
        r"\begin{tabular}{" + columns + "}", r"\toprule", " & ".join(headings) + r" \\", r"\midrule"]
    lines.extend(" & ".join(row) + r" \\" for row in body)
    lines.extend([r"\bottomrule", r"\end{tabular}",
        r"\par\vspace{0.2em}\footnotesize\emph{Note}: " + note, r"\end{table}"])
    (TABLES / (name + ".tex")).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    summary = rows("frozen_policy_summary.csv")
    body = []
    for country in ("DE", "AT", "BE", "NL"):
        pair = [row for row in summary if row["country"] == country and row["method"] in ("Global calibration", "Selected shrinkage")]
        minimum_cost = min(float(row["normalized_cost"]) for row in pair)
        for row in pair:
            cost = f"{float(row['normalized_cost']):.6f}"
            if float(row["normalized_cost"]) == minimum_cost:
                cost = r"\textbf{" + cost + "}"
            body.append([country, METHODS[row["method"]], f"{float(row['coverage']):.3f}", cost,
                         f"{float(row['shortfall_CVaR95_MW']):.2f}"])
    table("frozen_comparison", "Policy outcomes under frozen common reliability margins.", "llrrr",
        ["Region", "Policy", "Coverage", "Cost index", "Tail shortfall (MW)"], body,
        "Each policy reaches 0.95 in all eight later windows. Bold marks the lower cost within each displayed pair. Lower cost and tail shortfall are favorable; all eight policies appear in the Supplementary Material.")
    for name, countries in (("frozen_all_de_at", ("DE", "AT")), ("frozen_all_be_nl", ("BE", "NL"))):
        body = []
        for country in countries:
            subset = [row for row in summary if row["country"] == country]
            minimum_cost = min(float(row["normalized_cost"]) for row in subset)
            for row in subset:
                cost = f"{float(row['normalized_cost']):.6f}"
                if float(row["normalized_cost"]) == minimum_cost:
                    cost = r"\textbf{" + cost + "}"
                body.append([country, METHODS[row["method"]], f"{float(row['minimum_coverage']):.3f}",
                    f"{float(row['coverage']):.3f}", cost, f"{float(row['shortfall_CVaR95_MW']):.2f}"])
        table(name, "Eight-policy frozen-margin comparison: " + ", ".join(countries) + ".", "llrrrr",
            ["Region", "Policy", "Minimum coverage", "Mean coverage", "Cost index", "Tail (MW)"], body,
            "Eight windows per policy; each window reaches 0.95 coverage. Bold marks the lowest mean cost per region. Tail is the upper five-percent shortfall mean; lower cost and tail are favorable.")
    intervals = [row for row in rows("frozen_paired_intervals.csv") if row["comparator"] == "Global calibration"
                 and row["metric"] == "normalized_cost" and row["block_months"] == "3"]
    body = []
    for row in intervals:
        gain = f"{float(row['mean_gain']):+.6f}"
        if float(row["four_country_ci_low"]) > 0:
            gain = r"\textbf{" + gain + "}"
        body.append([row["country"], gain,
            f"[{float(row['four_country_ci_low']):+.6f}, {float(row['four_country_ci_high']):+.6f}]"])
    table("frozen_intervals", "Paired cost gains over global calibration under frozen margins.", "lrr",
        ["Region", "Mean gain", "Family-adjusted interval"], body,
        "Gain is global cost minus selected-local cost. Circular three-month blocks and 3,000 draws give 98.75-percent intervals, with Bonferroni adjustment for four countries. Bold marks positive lower endpoints. One- to four-month block results are archived.")
    body = []
    for row in rows("review_workload_summary.csv"):
        correct = row["correct_fields"] + "/" + row["reference_fields"]
        corrections = row["field_corrections"]
        disposition = row["disposition_corrections"]
        budget = f"{float(row['median_review_budget_seconds']):.1f}"
        if row["service"] == "deepseek":
            correct, corrections, disposition, budget = [r"\textbf{" + value + "}" for value in (correct, corrections, disposition, budget)]
        body.append([NAMES[row["service"]], correct, corrections, disposition, budget])
    table("review_workload", "Field corrections and derived review-time budgets on matched requests.", "lrrrr",
        ["Service", "Correct fields", "Field corrections", "Disposition corrections", "Budget (s)"], body,
        "Each service has 120 trials on 24 requests. Corrections are reference-label discrepancies. Budget is the median expert estimate minus request-matched service latency. Bold identifies more correct fields, fewer corrections, and the larger derived budget.")
    costs = [row for row in rows("api_budget_sensitivity.csv") if row["input_CNY_per_million"] == "2.4"]
    body = [[NAMES[row["service"]], f"{float(row['input_tokens']) / 240:.1f}",
        f"{float(row['output_tokens']) / 240:.1f}", f"{float(row['mean_budget_CNY']):.6f}",
        f"{float(row['total_budget_CNY']):.4f}"] for row in costs]
    table("api_budgets", "Recorded token use and common-tariff API budgets.", "lrrrr",
        ["Service", "Mean input", "Mean output", "CNY per trial", "CNY per 240 trials"], body,
        "API means application programming interface; CNY denotes Chinese yuan. The common budget uses 2.4/9.6 CNY per million input/output tokens, the published mainland qwen-max standard tariff. For Qwen it is a list-price estimate; other rows are common-rate sensitivity comparisons.")
    body = []
    for row in rows("execution_resource_accounting.csv"):
        budget = (float(row["mean_input_tokens"]) * 2.4 + float(row["mean_output_tokens"]) * 9.6) / 1e6
        body.append([NAMES[row["service"]], "Executed" if row["stage"] == "Authorized calculation" else "Returned",
            row["trials"], f"{float(row['median_service_seconds']):.2f}",
            f"{float(row['mean_field_corrections']):.2f}", f"{budget:.6f}"])
    table("execution_accounting", "Preparation resources by validated execution outcome.", "llrrrr",
        ["Service", "Outcome", "Trials", "Median seconds", "Mean corrections", "CNY budget"], body,
        "The 440 trials use 22 requests and five repetitions. Corrections count reference-field discrepancies. Budget uses the common tariff in Table~\\ref{tab:r1_api_budgets}; each executed record has zero paired reserve-cost difference.")
    table("maintenance_specification", "Shared configuration and interface maintenance artifacts.", "lr",
        ["Shared configuration", "Entries"], [["Supported regional identifiers", "6"], ["Supported horizons", "3"],
        ["Shortfall weights", "3"], ["Admissible variable categories", "9"], ["Prohibited source/action categories", "6"],
        ["Workflow states", "5"]],
        "Forms, parsers, and language interfaces share these definitions. Interface-specific maintenance covers form fields, parser expressions, generation schema, prompts, and provider settings.")
    print("Eight evidence tables generated from archived results.")


if __name__ == "__main__":
    main()
