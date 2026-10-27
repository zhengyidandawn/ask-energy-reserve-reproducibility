from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

from prepare_human_evidence import read_csv
from run_paired_services import PROJECT

OUTPUT = PROJECT / "elsarticle_unmark" / "sections" / "r1_tables"
NAMES = {"deepseek": "DeepSeek", "qwen": "Qwen", "ernie": "ERNIE", "hunyuan": "Hunyuan"}


def table(name: str, caption: str, columns: str, heading: str, rows: list[str], note: str = "") -> None:
    body = [r"\begin{table}[!htbp]", r"\centering", r"\footnotesize", r"\caption{" + caption + "}",
        r"\label{tab:r1_" + name + "}", r"\begin{tabular}{" + columns + "}", r"\toprule", heading + r" \\", r"\midrule"]
    body.extend(row + r" \\" for row in rows)
    body.extend([r"\bottomrule", r"\end{tabular}"])
    if note:
        body.append(r"\par\vspace{0.2em}\footnotesize\emph{Note}: " + note)
    body.append(r"\end{table}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / (name + ".tex")).write_text("\n".join(body) + "\n", encoding="utf-8")


def main() -> None:
    root = PROJECT / "results"
    summary = read_csv(root / "paired_evidence" / "service_summary.csv")
    for packet, suffix in (("blind_stratified_120", "repeat_120"), ("independently_authored_48", "repeat_48")):
        subset = [row for row in summary if row["packet"] == packet]
        best_raw = max(float(row["decision_accuracy"]) for row in subset)
        best_gate = max(float(row["validated_accuracy"]) for row in subset)
        rows = []
        for row in subset:
            raw = f"{float(row['decision_accuracy']) + 1e-9:.3f}"
            gate = f"{float(row['validated_accuracy']) + 1e-9:.3f}"
            if float(row["decision_accuracy"]) == best_raw:
                raw = r"\textbf{" + raw + "}"
            if float(row["validated_accuracy"]) == best_gate:
                gate = r"\textbf{" + gate + "}"
            rows.append(f"{NAMES[row['service']]} & {raw} & [{float(row['accuracy_ci_low']):.3f}, {float(row['accuracy_ci_high']):.3f}] & {gate} & {float(row['median_latency_seconds']):.2f}")
        table(suffix, ("Five-run results on 120 independently annotated requests." if suffix.endswith("120") else "Five-run results on 48 independently authored requests."),
            "lrrrr", "Service & Decision accuracy & 95\\% interval & Validated accuracy & Median seconds", rows,
            "Higher accuracy is favorable. Intervals resample identical request-text clusters after averaging five responses per case. Bold identifies the highest accuracy in each column.")
    interfaces = read_csv(root / "integrated_r1" / "interface_summary.csv")
    rows = []
    for row in interfaces:
        service, interface = row["method"].split(" / ")
        interface = {"JSON object": "JSON object", "tool_call": "Function call", "json_schema": "JSON schema"}[interface]
        service_rows = [item for item in interfaces if item["method"].startswith(service + " / ")]
        values = []
        for metric in ("decision_accuracy", "exact_schema_rate", "valid_completion_readiness"):
            value = float(row[metric])
            formatted = f"{value + 1e-9:.3f}"
            if value == max(float(item[metric]) for item in service_rows):
                formatted = r"\textbf{" + formatted + "}"
            values.append(formatted)
        rows.append(f"{NAMES[service]}, {interface} & " + " & ".join(values) + f" & {float(row['median_latency_seconds']):.2f}")
    table("interfaces", "Matched generation interfaces on the 48-request set.", "lrrrr", "Service and interface & Accuracy & Schema & Readiness & Seconds", rows,
        "Higher accuracy, schema validity, and readiness are favorable; bold marks the highest value within each service. Readiness uses the 25 accepted requests. Each interface uses five trials per request.")
    rows = []
    interface_rows = {row["method"]: row for row in interfaces}
    for method in ("hunyuan / JSON object", "hunyuan / json_schema", "hunyuan / tool_call"):
        row = interface_rows[method]
        interface_label = {"hunyuan / JSON object": "JSON object", "hunyuan / json_schema": "JSON schema", "hunyuan / tool_call": "Function calling"}[method]
        rows.append(f"Hunyuan, {interface_label} & {float(row['decision_accuracy']) + 1e-9:.3f} & {float(row['false_clarification_rate']):.3f} & {int(float(row['unsafe_ready']))} & {float(row['median_latency_seconds']):.2f} & {int(float(row['total_tokens']))}")
    parser_rows = read_csv(root / "integrated_r1" / "deterministic_external_scores.csv")
    parser_latency = np.median([float(row["latency_seconds"]) for row in parser_rows]) * 1000
    parser_false_clarification = sum(int(row["false_clarification"]) for row in parser_rows) / max(1, sum(row["expected"] == "accept" for row in parser_rows))
    rows.append(f"Deterministic parser & {np.mean([int(row['decision_correct']) for row in parser_rows]):.3f} & {parser_false_clarification:.3f} & {sum(int(row['unsafe_ready']) for row in parser_rows)} & {parser_latency:.2f} ms & 0")
    rows[1] = rows[1].replace(" & 0.120 &", r" & \textbf{0.120} &")
    rows[2] = rows[2].replace(" & 0.904 &", r" & \textbf{0.904} &")
    table("resource_comparison", "Accuracy and resource use of matched interfaces.", "lrrrrr", "Method & Accuracy & False clarification & Readiness errors & Median latency & Service tokens", rows,
        "Hunyuan uses 240 trials per interface; the parser uses 48 requests. Service latency is in seconds, and parser latency is in milliseconds. Higher accuracy and lower false clarification are favorable; bold identifies the best Hunyuan values.")
    parser = read_csv(root / "integrated_r1" / "deterministic_external_scores.csv")
    form = read_csv(root / "integrated_r1" / "expert_form_workflow.csv")
    experts = read_csv(root / "paired_evidence" / "expert_matched_summary.csv")
    rows = [f"Expert-entered form & 24 / 72 & {np.mean([int(row['decision_correct']) for row in form]):.3f} & {sum(int(row['unsafe_ready']) for row in form)} & Human preparation",
        f"Deterministic parser & 48 / 48 & {np.mean([int(row['decision_correct']) for row in parser]):.3f} & {sum(int(row['unsafe_ready']) for row in parser)} & {np.median([float(row['latency_seconds']) for row in parser])*1000:.2f} ms"]
    table("nonllm", "Structured and deterministic workflow references.", "lrrrl", "Method & Requests / trials & Accuracy & Readiness errors & Preparation", rows,
        "The finite-state workflow uses the same expert-entered forms and validates state transitions. Human preparation and automatic parsing have different input burdens.")
    rows = []
    for row in experts:
        latency = (f"{float(row['estimated_human_mean_minutes']):.2f} min (estimated)" if row["estimated_human_mean_minutes"] else f"{float(row['measured_API_median_seconds']):.2f} s (measured)")
        rows.append(f"{NAMES.get(row['method'],row['method'])} & {float(row['decision_accuracy']):.3f} & {float(row['field_accuracy']):.3f} & {float(row['unsafe_ready']):.0f} & {latency}")
    table("expert", "Experts and services on the same 24 requests.", "lrrrl", "Method & Accuracy & Field accuracy & Readiness errors & Preparation time", rows,
        "EXP-1, EXP-2, and EXP-3 identify the three experts, each preparing 24 plans. Service rates average five responses per request. Expert time is a participant estimate; service time is observed response latency.")
    public = read_csv(root / "public_validation_r1" / "main" / "summary.csv")
    rows, physical = [], []
    countries = ("DE", "AT", "BE", "NL")
    for country in countries:
        subset = [row for row in public if row["country"] == country]
        best = min(float(row["normalized_cost"]) for row in subset if float(row["coverage"]) >= .95)
        for method in ("Global calibration", "Selected shrinkage", "Block-score calibration", "Scenario maximum"):
            row = next(row for row in subset if row["method"] == method)
            label = {"Global calibration": "Global", "Selected shrinkage": "Selected local", "Block-score calibration": "Block maximum", "Scenario maximum": "Scenario maximum"}[method]
            coverage, cost = f"{float(row['coverage']):.3f}", f"{float(row['normalized_cost']):.5f}"
            if float(row["coverage"]) >= .95 and float(row["normalized_cost"]) == best:
                cost = r"\textbf{" + cost + "}"
            rows.append(f"{country} & {label} & {coverage} & {cost} & {row['windows_meeting_coverage']}/12")
            if method == "Selected shrinkage":
                physical.append(f"{row['country_name']} & {float(row['mean_reserve_MW']):.1f} & {float(row['mean_shortfall_MW']):.2f} & {float(row['shortfall_CVaR95_MW']):.1f} & {coverage}")
    table("public", "Public-data policies under a common selection constraint.", "llrrr", "Region & Policy & Test coverage & Cost index & Windows $\\geq .95$", rows,
        "DE, AT, BE, and NL denote Germany, Austria, Belgium, and the Netherlands. All policies use the same 0.95 selection constraint. Test coverage and lower cost are assessed together; bold marks the lowest qualifying cost across all eight policies for a region.")
    table("physical", "Physical-unit results for the selected local policy.", "lrrrr", "Region & Reserve (MW) & Shortfall (MW) & Tail shortfall (MW) & Coverage", physical,
        "MW denotes megawatts. Tail shortfall is the conditional value at risk in the worst five percent. Each region contains 34,560 held-out decisions.")
    regimes = read_csv(root / "integrated_r1" / "public_conditional_summary.csv")
    rows = []
    for country in countries:
        for regime in ("season_winter", "season_spring", "season_summer", "season_autumn", "high_observed_ramp"):
            row = next(row for row in regimes if row["country"] == country and row["method"] == "Selected shrinkage" and row["regime"] == regime)
            rows.append(f"{country} & {regime.replace('season_','').replace('high_observed_ramp','High ramp').title()} & {row['n']} & {float(row['coverage']):.3f} & {float(row['normalized_cost']):.5f}")
    table("conditional", "Seasonal and high-ramp performance on public data.", "llrrr", "Region & Regime & Decisions & Coverage & Cost index", rows,
        "High ramp uses the 80th percentile of the training-period recent-ramp statistic. Regime membership uses the recent observed ramp available at the decision time.")
    prediction = read_csv(root / "integrated_r1" / "conditional_prediction_summary.csv")
    rows = []
    for country in countries:
        for regime in ("season_winter", "season_spring", "season_summer", "season_autumn", "high_observed_ramp"):
            row = next(item for item in prediction if item["country"] == country and item["regime"] == regime)
            coverage = f"{float(row['calibrated_coverage']):.3f}"
            if float(row["calibrated_coverage"]) >= 0.95:
                coverage = r"\textbf{" + coverage + "}"
            rows.append(f"{country} & {regime.replace('season_', '').replace('high_observed_ramp', 'High ramp').title()} & {row['n']} & {float(row['predictor_pinball_MW']):.2f} & {coverage}")
    table("conditional_prediction", "Prediction loss and calibrated reliability by regime.", "llrrr", "Region & Regime & Decisions & Pinball (MW) & Coverage", rows,
        "Lower pinball loss is favorable for the common 0.95 quantile predictor. Coverage evaluates selected local calibration; bold identifies values at least 0.95. Groups match the seasonal and high-ramp reserve comparison.")
    confusion = read_csv(root / "paired_evidence" / "confusion_matrices.csv")
    rows = []
    for service in sorted({row["service"] for row in summary}):
        for expected in ("accept", "clarify", "reject"):
            counts = [next(int(row["count"]) for row in confusion if row["packet"] == "independently_authored_48" and row["service"] == service and row["expected"] == expected and row["predicted"] == predicted) for predicted in ("accept", "clarify", "reject", "partial_accept", "invalid")]
            rows.append(NAMES[service] + " & " + expected.title() + " & " + " & ".join(map(str, counts)))
    table("confusion", "Decision confusion counts on independently authored requests.", "llrrrrr", "Service & Reference & Accept & Clarify & Reject & Partial & Invalid", rows,
        "Counts include all five attempts. Reference class counts are 25 accepted, 14 clarification, and 9 rejected requests.")
    path = root / "integrated_r1" / "clarification_summary.csv"
    if path.exists():
        rows = []
        for row in read_csv(path):
            rows.append(f"{NAMES[row['service']]} & {float(row['initial_clarification_rate']):.3f} & {float(row['terminal_acceptance']):.3f} & {float(row['terminal_execution_readiness']):.3f} & {float(row['median_total_API_seconds']):.2f}")
        table("clarification", "One-confirmation clarification experiment.", "lrrrr", "Service & Initial clarify & Final accept & Final readiness & Total seconds", rows,
            "Each of 14 requests receives one prespecified confirmation and five paired trials. Timing covers both service calls. Confirmations are scripted analyst answers.")
    dialogue_path = root / "evidence_completion_20261011" / "question_driven_dialogue" / "main" / "dialogue_trials.csv"
    if dialogue_path.exists():
        dialogue = read_csv(dialogue_path)
        grouped = []
        for service in ("deepseek", "qwen", "ernie", "hunyuan"):
            subset = [row for row in dialogue if row["service"] == service]
            grouped.append({
                "service": service,
                "n": len(subset),
                "initial_clarify": np.mean([row["initial_decision"] == "clarify" for row in subset]),
                "matched": np.mean([int(row["matching_completed_plan"]) for row in subset]),
                "final_accept": np.mean([row["final_decision"] == "accept" for row in subset]),
                "median_seconds": np.median([float(row["total_service_seconds"]) for row in subset]),
                "mean_turns": np.mean([float(row["additional_turns"]) for row in subset]),
            })
        best_matched = max(row["matched"] for row in grouped)
        rows = []
        for row in grouped:
            matched = f"{row['matched']:.3f}"
            if row["matched"] == best_matched:
                matched = r"\textbf{" + matched + "}"
            rows.append(f"{NAMES[row['service']]} & {row['n']} & {row['initial_clarify']:.3f} & {matched} & {row['final_accept']:.3f} & {row['median_seconds']:.2f} & {row['mean_turns']:.2f}")
        table("question_dialogue", "Question-driven clarification with field-limited follow-up.", "lrrrrrr",
              "Service & Trials & Initial clarify & Matched terminal plan & Final accept & Median seconds & Mean turns", rows,
              "Each service contributes 70 retained initial trials. The analyst response supplies only fields explicitly requested by the preceding response, with at most three follow-up turns. Matching requires the accepted disposition, all three required fields, and retained human approval. Higher matching and final acceptance are favorable.")
    reliability_path = root / "evidence_completion_20261011" / "reliability" / "main" / "summary.csv"
    if reliability_path.exists():
        reliability = read_csv(reliability_path)
        rows = []
        for country in ("DE", "AT", "BE", "NL"):
            subset = [row for row in reliability if row["country"] == country and row["margin_applied"] == "True"]
            qualifying = sum(int(row["windows_meeting_coverage"]) for row in subset)
            minimum = min(float(row["minimum_window_coverage"]) for row in subset)
            mean_coverage = np.mean([float(row["coverage"]) for row in subset])
            rows.append(f"{country} & 8 & {qualifying}/64 & {minimum:.3f} & {mean_coverage:.3f}")
        table("common_reliability", "Frozen-margin reliability extension on public data.", "lrrrr",
              "Region & Policies & Windows at 0.95 & Minimum window coverage & Mean coverage", rows,
              "The common nonnegative margin is estimated from the 2019 benchmark windows and applied unchanged to eight 2020-onward windows for each of eight policies. Higher coverage is favorable. This is an empirical frozen-margin check under the recorded chronological protocol.")
    weather_path = root / "evidence_completion_20261011" / "weather" / "main" / "summary.csv"
    if weather_path.exists():
        weather = read_csv(weather_path)
        rows = []
        for variant in ("load_calendar", "distributed_weather"):
            row = next(item for item in weather if item["input_variant"] == variant and item["method"] == "Selected shrinkage")
            label = "Calendar inputs" if variant == "load_calendar" else "Six-station weather"
            rows.append(f"{label} & {row['windows']} & {row['decisions']} & {float(row['coverage']):.3f} & {float(row['minimum_window_coverage']):.3f} & {float(row['normalized_cost']):.5f} & {float(row['predictor_pinball_loss']):.2f}")
        table("weather_diagnostic", "Distributed-weather diagnostic on German public load.", "llrrrrr",
              "Input variant & Windows & Decisions & Coverage & Minimum window & Cost index & Pinball (MW)", rows,
              "The comparison uses equal-weight temperature and relative humidity from six official German Weather Service stations, with a one-hour availability lag. The diagnostic retains all eight windows and uses the same chronological split. Higher coverage and lower cost or pinball loss are favorable; window-level coverage remains the governing reliability check.")
    dependency = read_csv(root / "public_validation_r1" / "main" / "dependence_diagnostics.csv")
    rows = []
    for country in countries:
        subset = [row for row in dependency if row["country"] == country]
        rows.append(f"{country} & {np.mean([float(row['target_autocorrelation_lag1']) for row in subset]):.3f} & {np.mean([float(row['residual_autocorrelation_lag1']) for row in subset]):.3f} & {np.mean([float(row['effective_sample_mean']) for row in subset]):.1f}")
    table("dependence", "Dependence and neighborhood diagnostics.", "lrrr", "Region & Target lag-one correlation & Residual correlation & Effective sample size", rows)
    rows = []
    for row in summary:
        if row["packet"] == "independently_authored_48":
            rows.append(f"{NAMES[row['service']]} & {float(row['mean_prompt_tokens']):.0f} & {float(row['mean_completion_tokens']):.2f} & {float(row['p95_latency_seconds']):.2f}")
    table("usage", "Usage and latency on independent requests.", "lrrr", "Service & Mean input tokens & Mean output tokens & 95th-percentile seconds", rows,
        "All 240 scheduled responses per service are included. Usage is preserved as returned by each provider; provider billing records are required for a monetary charge.")
    rows = []
    for row in summary:
        if row["packet"] == "independently_authored_48":
            rows.append(f"{NAMES[row['service']]} & {row['always_correct_cases']} & {row['mixed_cases']} & {row['never_correct_cases']} & {row['same_decision_all_runs']}")
    table("consistency", "Five-response consistency for 48 independent requests.", "lrrrr", "Service & Always correct & Mixed & Never correct & Same decision", rows)
    comparisons = read_csv(root / "paired_evidence" / "paired_service_tests.csv")
    rows = []
    for row in comparisons:
        if row["packet"] == "independently_authored_48":
            label = "Decision" if row["metric"] == "decision_correct" else "Validated"
            probability = float(row['p_holm'])
            probability_text = "$<0.001$" if probability < 0.001 else f"{probability:.3f}"
            if probability < 0.05:
                probability_text = r"\textbf{" + probability_text + "}"
            rows.append(f"{NAMES[row['first_service']]}--{NAMES[row['second_service']]} & {label} & {float(row['mean_difference']):+.3f} & {probability_text}")
    table("paired_tests", "Paired service comparison on independent requests.", "llrr", "Service pair & Endpoint & First minus second & Adjusted $p$", rows,
        "Two-sided cluster sign permutations use 20,000 draws. Holm correction applies to all service pairs within each endpoint. Bold identifies adjusted probabilities below 0.05.")
    rows = []
    for row in read_csv(root / "integrated_r1" / "interface_paired_tests.csv"):
        interface = row["alternative"].split(" / ")[1]
        label = {"json_schema": "JSON schema", "tool_call": "Function call"}[interface]
        probability = float(row["p_holm"])
        value = r"\textbf{$<0.001$}" if probability < 0.001 else f"{probability:.3f}"
        rows.append(f"{NAMES[row['service']]} & {label} & {float(row['object_minus_alternative']):+.3f} & {value}")
    table("interface_tests", "Paired accuracy comparisons between generation interfaces.", "llrr", "Service & Alternative & Object minus alternative & Adjusted $p$", rows,
        "Negative differences favor the alternative. All 48 requests are paired. Holm adjustment applies within each service; bold identifies adjusted probabilities below 0.05.")
    rows = []
    for row in read_csv(root / "integrated_r1" / "public_paired_cost.csv"):
        if row["comparator"] != "Global calibration":
            continue
        interval = f"[{float(row['ci_low']):.5f}, {float(row['ci_high']):.5f}]"
        if float(row["ci_low"]) > 0:
            interval = r"\textbf{" + interval + "}"
        rows.append(f"{row['country']} & {float(row['normalized_cost_gain']):+.5f} & {interval}")
    table("public_cost_intervals", "Selected local cost gain relative to global calibration.", "lrr", r"Region & Mean cost-index gain & 95\% interval", rows,
        "Positive gain favors selected local calibration. Intervals use 3000 moving-block draws of three successive monthly windows. Bold intervals lie above zero.")
    sensitivity = read_csv(root / "public_validation_r1" / "sensitivity.csv")
    grouped = {}
    for row in sensitivity:
        if row["method"] == "Selected shrinkage":
            key = (row["calibration_days"],row["neighbors"],row["required_coverage"])
            grouped.setdefault(key, []).append(row)
    rows = []
    for key, subset in grouped.items():
        rows.append(" & ".join(key) + f" & {np.mean([float(row['coverage']) for row in subset]):.3f} & {np.mean([float(row['normalized_cost']) for row in subset]):.5f} & {np.mean([float(row['effective_sample_mean']) for row in subset]):.1f} & {min(float(row['effective_sample_min']) for row in subset):.1f}")
    table("sensitivity", "Calibration sensitivity in four German rolling windows.", "rrrrrrr", "Calibration days & Neighbors & Required coverage & Test coverage & Cost index & Mean ESS & Minimum ESS", rows,
        "The same four quarterly origins evaluate every setting. All settings are selected before their test period. ESS denotes effective sample size; higher ESS indicates a broader weighted residual neighborhood.")
    traces = read_csv(root / "integrated_r1" / "checked_request_to_calculation.csv")
    labels = ("Reference", "Region", "120-minute horizon", "180-minute horizon", "Variables", "Shortfall weight 10", "Shortfall weight 40", "Coverage 0.975", "Tail reporting")
    rows = []
    for label, row in zip(labels,traces):
        rows.append(f"{label} & {float(row['coverage']):.3f} & {float(row['mean_reserve_MW']):.1f} & {float(row['normalized_cost']):.5f}")
    table("field_trace", "Checked study fields and their computed outputs.", "lrrr", "Changed field & Coverage & Reserve (MW) & Cost index", rows,
        "The reference uses Germany, 60 minutes, observed load and calendar inputs, shortfall weight 20, and required coverage 0.95. Tail reporting returns an additional diagnostic with the same target and reserve.")
    executions = read_csv(root / "paired_public_execution" / "summary.csv")
    best_completion = max(float(row["validated_completion"]) for row in executions)
    rows = []
    for row in executions:
        completion = f"{float(row['validated_completion']):.3f}"
        if float(row["validated_completion"]) == best_completion:
            completion = r"\textbf{" + completion + "}"
        rows.append(f"{NAMES[row['service']]} & {row['trials']} & {completion} & {row['blocked']} & {row['direct_plan_computed']} & {float(row['verified_completed_plan_cost_difference']):.5f}")
    table("execution", "Actual service fields in matched public-data calculations.", "lrrrrr", "Service & Trials & Completion & Blocked & Direct calculations & Paired cost difference", rows,
        "Each service contributes five trials for each of 22 requests. Higher completion is favorable; bold identifies its highest value. Blocked plans retain a blank cost field. Checked completed plans reproduce the reference reserve series. Cost differences use identical timestamps and the reference objective.")
    print(json.dumps({"tables": len(list(OUTPUT.glob('*.tex'))), "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
