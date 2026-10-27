from __future__ import annotations

import csv

from workspace_paths import PROJECT


RESULTS = PROJECT / "results" / "substantive_resolution_20261011"
TABLES = PROJECT / "elsarticle_unmark" / "sections" / "r1_tables"
NAMES = {"deepseek": "DeepSeek", "qwen": "Qwen", "ernie": "ERNIE", "hunyuan": "Hunyuan"}


def rows(filename: str) -> list[dict]:
    with (RESULTS / filename).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def table(name: str, caption: str, columns: str, headings: list[str], body: list[list[str]], note: str) -> None:
    lines = [r"\begin{table}[!htbp]", r"\centering", r"\footnotesize", r"\caption{" + caption + "}",
             r"\label{tab:r1_" + name + "}", r"\begin{tabular}{" + columns + "}", r"\toprule",
             " & ".join(headings) + r" \\", r"\midrule"]
    lines += [" & ".join(record) + r" \\" for record in body]
    lines += [r"\bottomrule", r"\end{tabular}", r"\par\vspace{0.2em}\footnotesize\emph{Note}: " + note, r"\end{table}"]
    (TABLES / (name + ".tex")).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    costs = rows("provider_cost_summary.csv")
    table("provider_costs", "Provider-specific list-price estimates on independent requests.", "llrr",
          ["Service", "Currency", "Mean per trial", "Total for 240 trials"],
          [[NAMES[row["service"]], row["currency"], f"{float(row['mean_list_price_cost']):.6f}", f"{float(row['list_price_cost']):.6f}"] for row in costs],
          "USD denotes United States dollars and CNY Chinese yuan. Estimates use returned model, recorded cache use and online tariffs. Each currency retains its own unit.")
    workload = rows("input_workload_summary.csv")
    body = []
    for row in workload:
        replacements = row["required_replacements"]
        reduction = f"{float(row['input_reduction'])*100:.1f}"
        if row["service"] == "deepseek":
            replacements, reduction = [r"\textbf{" + value + "}" for value in (replacements, reduction)]
        body.append([NAMES[row["service"]], row["manual_entries"], replacements, row["retained_entries"], reduction])
    table("input_workload", "Reference input operations in matched plan preparation.", "lrrrr",
          ["Service", "Entries", "Replacements", "Retained", r"Reduction (\%)"], body,
          "Each service has 120 trials on 24 requests. Entries comprise disposition and specified variable fields; reserve weight is fixed. Replacements are minimum reference-label edits. Every entry remains subject to review. Bold identifies fewer replacements and greater input reduction.")
    table("maintenance_changes", "Recorded declaration changes and regression checks.", "lrrrr",
          ["Changed category", "Declarations", "Added lines", "Removed lines", "Regression"],
          [[name, row["policy_values_added"], row["added_diff_lines"], row["removed_diff_lines"], row["regression_passed"] + "/" + row["regression_requests"]]
           for name, row in zip(["Region", "Horizon", "Variables", "Shortfall weight", "Reliability", "Reporting"], rows("maintenance_changes.csv"))],
          "Each change edits one shared declaration and generates form choices, parser vocabulary and a generation schema. Three interfaces each receive 30 new-value checks. Regression preserves the 15 specified request outcomes.")
    summary_path = RESULTS / "six_field_summary.csv"
    if not summary_path.is_file():
        return
    summaries = rows("six_field_summary.csv")
    body = []
    for service in NAMES:
        selected = {row["plan_class"]: row for row in summaries if row["service"] == service}
        body.append([NAMES[service], selected["accept"]["initial_executed"] + "/45",
                     selected["clarify"]["terminal_executed"] + "/15",
                     f"{float(selected['reject']['validated_accuracy'])*15:.0f}/15"])
    maximum = max(int(next(row["initial_executed"] for row in summaries if row["service"] == service and row["plan_class"] == "accept")) for service in NAMES)
    for record in body:
        if int(record[1].split("/")[0]) == maximum:
            record[1] = r"\textbf{" + record[1] + "}"
    table("six_field_execution", "Execution from service responses across six study-field categories.", "lrrr",
          ["Service", "Complete request", "After clarification", "Boundary rejection"], body,
          "Nine complete specifications, three omissions and three boundary requests each have five trials per service. All executed outputs reproduce their reference. Higher completion is favorable; bold identifies the largest complete-request count.")
    names = ["Region", "Horizon", "Variables", "Shortfall weight", "Reliability", "Reporting"]
    fault_rows = rows("field_fault_summary.csv")
    table("field_faults", "Validation of single-field deviations in actual accepted responses.", "lrrr",
          ["Changed category", "Returned", "Potential cost change", "Potential coverage"],
          [[label, row["blocked"] + "/" + row["injections"], f"{float(row['potential_cost_difference']):+.6f}", f"{float(row['potential_coverage']):.3f}"] for label, row in zip(names, fault_rows)],
          "The 95 deviations are controlled fault injections. Potential cost uses the unchanged requested target and objective. Returned plans await field confirmation. Reporting deviation removes the requested tail result and preserves reserve quantities.")
    outcome_names = {"Correct accepted plan": "Accepted", "Incomplete returned plan": "Incomplete",
                     "Incorrect returned plan": "Incorrect", "Clarification": "Clarified", "Boundary rejection": "Rejected"}
    outcomes = rows("six_field_outcome_resources.csv")
    for name, services in (("six_field_resources_dq", ("deepseek", "qwen")), ("six_field_resources_eh", ("ernie", "hunyuan"))):
        body = []
        for row in outcomes:
            if row["service"] in services:
                body.append([NAMES[row["service"]], outcome_names[row["outcome"]], row["trials"],
                             f"{float(row['median_service_seconds']):.2f}",
                             f"{float(row['mean_field_replacements']):.2f}" if row["mean_field_replacements"] else "--",
                             f"{float(row['mean_list_price_cost']):.6f}"])
        table(name, "Service resources by plan outcome in the six-field study.", "llrrrr",
              ["Service", "Outcome", "Trials", "Seconds", "Corrections", "Mean fee"], body,
              "Seconds is median total service time; clarified plans include one reply. Fees use USD for DeepSeek and CNY for the other services. Corrections count discrepancies in supplied fields; rejected requests have no field-entry task. Computations replay checked specifications offline.")
    print("Substantive evidence tables generated.")


if __name__ == "__main__":
    main()
