"""Plot stored request-evaluation CSVs without fitting models or resampling.

Run from any directory with the project Python environment.  Figure CSVs retain
the plotted values, denominators, and hashes of their input files.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


def native(path: Path | str) -> str:
    """Use native extended paths for Windows package directories of any length."""
    value = os.path.abspath(os.fspath(path))
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        return "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return value


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "figure_revision_20261026"
FIGURES = ROOT / "elsarticle_unmark" / "figures"
ORIGINAL = ROOT / "data" / "original_study"
if not Path(native(ORIGINAL)).is_dir():
    ORIGINAL = ROOT.parents[1]

SERVICES = ("deepseek", "qwen", "ernie", "hunyuan")
NAMES = dict(zip(SERVICES, ("DeepSeek", "Qwen", "ERNIE", "Hunyuan")))
COLORS = dict(zip(SERVICES, ("#0072B2", "#E69F00", "#009E73", "#CC79A7")))
GRAY = "#555555"
SOURCES: dict[str, dict] = {}
DATA: dict[str, list[dict]] = {}


def configure() -> None:
    times = Path("C:/Windows/Fonts/times.ttf")
    if times.is_file():
        font_manager.fontManager.addfont(str(times))
    plt.rcParams.update({
        "font.family": ["Times New Roman", "DejaVu Serif"],
        "font.size": 12,
        "axes.titlesize": 13.5,
        "axes.labelsize": 12,
        "xtick.labelsize": 12.0,
        "ytick.labelsize": 12.0,
        "legend.fontsize": 12.0,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#777777",
        "axes.linewidth": 0.7,
        "savefig.facecolor": "white",
        "figure.facecolor": "white",
    })


def read(key: str, relative: str, *, original: bool = False) -> pd.DataFrame:
    path = (ORIGINAL if original else ROOT) / relative
    raw = Path(native(path)).read_bytes()
    source_name = ("original_study/" if original else "") + relative.replace("\\", "/")
    digest = hashlib.sha256(raw).hexdigest()
    archive = OUT / "source_csv" / f"{key}.csv"
    Path(native(archive.parent)).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(native(path), native(archive))
    SOURCES[key] = {"source": source_name, "sha256": digest,
                    "package_source_path": ("data/original_study/" if original else "") + relative.replace("\\", "/"),
                    "archived_csv": archive.relative_to(OUT).as_posix()}
    return pd.read_csv(native(path))


def record(figure: str, panel: str, method: str, endpoint: str, value: float,
           source: str, **extra: object) -> None:
    DATA.setdefault(figure, []).append({
        "panel": panel, "method": method, "endpoint": endpoint,
        "value": value, **extra, **SOURCES[source],
    })


def style(ax, title: str, xlabel: str, *, fraction: bool = True) -> None:
    ax.set_title(title, loc="left", pad=12, fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#E5E5E5", linewidth=0.7)
    ax.tick_params(axis="both", length=3, color="#777777")
    if fraction:
        ax.set_xlim(0, 1.035)
        ax.set_xticks([0, .25, .5, .75, 1])
        ax.set_xticklabels(["0", "0.25", "0.50", "0.75", "1.00"])


def rows(ax, labels: list[str]) -> None:
    ax.set_yticks(range(len(labels)), labels)
    ax.set_ylim(len(labels) - .55, -.55)


def interval(ax, value: float, low: float, high: float, y: float, color: str) -> None:
    ax.errorbar(value, y, xerr=[[value - low], [high - value]], fmt="o",
                markersize=6.2, color=color, ecolor=color, elinewidth=1.6,
                capsize=3, capthick=1.1, zorder=3)


def export(fig, stem: str) -> None:
    Path(native(OUT)).mkdir(parents=True, exist_ok=True)
    Path(native(FIGURES)).mkdir(parents=True, exist_ok=True)
    paths = {}
    for suffix in ("pdf", "svg", "png"):
        target = OUT / f"{stem}.{suffix}"
        kwargs = {"dpi": 300} if suffix == "png" else {}
        fig.savefig(native(target), format=suffix, bbox_inches="tight", pad_inches=.12, **kwargs)
        shutil.copyfile(native(target), native(FIGURES / target.name))
        paths[suffix] = {"path": target.relative_to(ROOT).as_posix(),
                         "sha256": hashlib.sha256(Path(native(target)).read_bytes()).hexdigest()}
    csv = OUT / f"{stem}_data.csv"
    pd.DataFrame(DATA[stem]).to_csv(native(csv), index=False, float_format="%.15g")
    metadata = {"figure": stem, "artifacts": paths,
                "data_csv": csv.relative_to(ROOT).as_posix(),
                "data_sha256": hashlib.sha256(Path(native(csv)).read_bytes()).hexdigest(),
                "source_files": {key: value for key, value in SOURCES.items()
                                 if value["source"] in {row["source"] for row in DATA[stem]}},
                "figure_width_inches": fig.get_figwidth(),
                "minimum_text_points": 12.0,
                "intended_print_width_inches": 6.3,
                "intervals": "Existing CSV endpoints only; no resampling."}
    Path(native(OUT / f"{stem}_provenance.json")).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plt.close(fig)


def service_interfaces() -> None:
    stem = "R1_F4_Service_Interfaces"
    joint = read("joint", "results/strengthening_20261011/joint_summary.csv").set_index("service")
    independent = read("services", "results/paired_evidence/service_summary.csv")
    independent = independent[independent.packet == "independently_authored_48"].set_index("service")
    paired = read("parser_pairs", "results/remaining_review_questions_20261011/parser_paired_comparison.csv")
    fig, axs = plt.subplots(2, 2, figsize=(9, 8.7),
                            gridspec_kw={"height_ratios": [1, 1.55]}, layout="constrained")
    ax = axs[0, 0]
    for y, service in enumerate(SERVICES):
        row = joint.loc[service]
        interval(ax, row.joint_success, row.ci_low, row.ci_high, y, COLORS[service])
        ax.text(.03, y, f"{row.joint_success:.3f}", va="center", fontsize=12.0)
        record(stem, "a", NAMES[service], "joint_success", row.joint_success, "joint",
               ci_low=row.ci_low, ci_high=row.ci_high, requests=200, trials=1000)
    rows(ax, list(NAMES.values()))
    style(ax, "(a) Historical labels: 200 requests", "Joint success (five responses/request)")
    ax = axs[0, 1]
    for y, service in enumerate(SERVICES):
        row = independent.loc[service]
        ax.plot(row.decision_accuracy, y - .12, "o", color=COLORS[service], markersize=6.2)
        ax.plot(row.validated_accuracy, y + .12, "s", color=COLORS[service],
                markerfacecolor="white", markersize=6.2, markeredgewidth=1.5)
        for endpoint in ("decision_accuracy", "validated_accuracy"):
            record(stem, "b", NAMES[service], endpoint, float(row[endpoint]), "services",
                   requests=48, trials=240)
    rows(ax, list(NAMES.values()))
    style(ax, "(b) Independent labels: 48 requests", "Disposition accuracy (point estimates)")
    ax.legend(handles=[Line2D([], [], marker="o", color=GRAY, linestyle="none", label="Original"),
                       Line2D([], [], marker="s", color=GRAY, markerfacecolor="white",
                              linestyle="none", label="Validated")], loc="lower left", frameon=False,
              borderpad=.1, handletextpad=.4)
    order = ["deepseek / JSON object", "deepseek / tool_call", "qwen / JSON object",
             "qwen / json_schema", "qwen / tool_call", "ernie / JSON object", "ernie / json_schema",
             "hunyuan / JSON object", "hunyuan / json_schema", "hunyuan / tool_call"]
    labels = [m.replace("deepseek", "DeepSeek").replace("qwen", "Qwen")
              .replace("ernie", "ERNIE").replace("hunyuan", "Hunyuan")
              .replace(" / JSON object", ": object").replace(" / json_schema", ": schema")
              .replace(" / tool_call", ": function") for m in order]
    for col, (endpoint, letter, title) in enumerate([
            ("decision_correct", "c", "Original disposition"),
            ("validated_correct", "d", "After deterministic validation")]):
        ax = axs[1, col]
        subset = paired[paired.endpoint == endpoint].set_index("method")
        for y, method in enumerate(order):
            row = subset.loc[method]
            service = method.split(" / ")[0]
            interval(ax, row.mean_paired_gain, row.ci_low, row.ci_high, y, COLORS[service])
            record(stem, letter, method, endpoint, row.mean_paired_gain, "parser_pairs",
                   ci_low=row.ci_low, ci_high=row.ci_high, p_holm=row.p_holm,
                   requests=48, trials=240, parser_requests=48)
        rows(ax, labels)
        style(ax, f"({letter}) {title}", "Accuracy difference: interface minus parser", fraction=False)
        ax.axvline(0, color=GRAY, linestyle="--", linewidth=1)
        ax.set_xlim(-.35, .35)
        ax.set_xticks([-.3, -.15, 0, .15, .3])
        ax.set_xticklabels(["−0.30", "−0.15", "0", "+0.15", "+0.30"])
    export(fig, stem)


def draft_preparation() -> None:
    stem = "R1_F5_Draft_Preparation"
    summary = read("draft_stages", "results/online_draft_audit_20261011/stage_summary.csv")
    terminal = summary[summary.stage == "terminal"].set_index("service")
    references = read("draft_references", "results/online_draft_audit_20261011/comparator_summary.csv").set_index("method")
    experts = read("expert_times", "results/paired_evidence/expert_matched_summary.csv")
    expert_plans = read("expert_plans", "data/human_r1/expert_plans_normalized.csv")
    labels = read("evaluation_labels", "data/human_r1/evaluation_labels.csv").set_index("case_id")
    exp3 = expert_plans[expert_plans.expert_id == "EXP-3"]
    fixed_weight_blanks = exp3[exp3.cost_reserve.isna() & exp3.case_id.map(labels.gold_cost_reserve.notna())]
    assert len(fixed_weight_blanks) == 7
    record(stem, "caption", "EXP-3", "blank_fixed_reserve_weight_entries", 7,
           "expert_plans", denominator=40)
    record(stem, "caption", "EXP-3", "reference_fixed_reserve_weight", 1,
           "evaluation_labels", affected_entries=7)
    participants = [(NAMES[s], s, terminal.loc[s], "draft_stages") for s in SERVICES]
    participants += [("Parser", "parser", references.loc["field-preserving deterministic parser"], "draft_references")]
    participants += [(e, "expert", references.loc[e], "draft_references") for e in ("EXP-1", "EXP-2", "EXP-3")]
    fig, axs = plt.subplots(2, 2, figsize=(9, 8.4), layout="constrained")
    measures = [("field_correct", "field_total", "(a) Correct supplied fields", "Field agreement"),
                ("retained_entries", "manual_entries", "(b) Reusable candidate inputs", "Input reuse"),
                ("valid_ready", "reference_accept", "(c) Ready among accepted requests", "Valid-request readiness")]
    for ax, (numerator, denominator, title, xlabel), panel in zip(
            (axs[0, 0], axs[0, 1], axs[1, 0]), measures, ("a", "b", "c")):
        for y, (label, service, row, source) in enumerate(participants):
            value = float(row[numerator]) / float(row[denominator])
            color = COLORS.get(service, GRAY)
            marker = "o" if service in SERVICES else ("D" if service == "parser" else "s")
            if panel == "b" and service in SERVICES:
                interval(ax, value, row.retained_ci_low, row.retained_ci_high, y, color)
            else:
                ax.plot(value, y, marker=marker, color=color, linestyle="none", markersize=6.2,
                        markerfacecolor=color if service in SERVICES else "white", markeredgewidth=1.4)
            count = f"{int(row[numerator])}/{int(row[denominator])}"
            ax.text(.025, y, count, va="center", fontsize=12.0)
            record(stem, panel, label, numerator, value, source, numerator=int(row[numerator]),
                   denominator=int(row[denominator]),
                   **({"ci_low": row.retained_ci_low, "ci_high": row.retained_ci_high}
                      if panel == "b" and service in SERVICES else {}))
        rows(ax, [p[0] for p in participants])
        style(ax, title, xlabel)
        ax.axhline(3.5, color="#BBBBBB", linewidth=.8)
    ax = axs[1, 1]
    for y, service in enumerate(SERVICES):
        row = terminal.loc[service]
        value = float(row.median_service_seconds)
        ax.barh(y, value, color=COLORS[service], alpha=.85, height=.52)
        ax.text(value + .35, y, f"{value:.2f} s", va="center", fontsize=12.0)
        record(stem, "d", NAMES[service], "median_online_seconds", value, "draft_stages",
               requests=24, trials=120, online_calls=int(row.online_calls))
    rows(ax, list(NAMES.values()))
    style(ax, "(d) Automatic draft preparation", "Median online time, including feedback (s)", fraction=False)
    ax.set_xlim(0, 21)
    ax.set_xticks([0, 5, 10, 15, 20])
    for _, row in experts[experts.method.str.startswith("EXP-")].iterrows():
        record(stem, "caption", row.method, "self_estimated_preparation_minutes",
               row.estimated_human_mean_minutes, "expert_times", requests=24)
    export(fig, stem)


def clarification() -> None:
    stem = "R1_F6_Clarification"
    legacy = read("legacy_modes", "supplementary_artifacts/blind_end_to_end_holdout/mode_summary.csv", original=True).set_index("mode")
    cases = read("legacy_cases", "supplementary_artifacts/blind_end_to_end_holdout/case_execution_results.csv", original=True)
    uniform = read("uniform_confirmation", "results/integrated_r1/clarification_summary.csv").set_index("service")
    dialogue = read("question_dialogue", "results/evidence_completion_20261011/question_driven_dialogue/main/dialogue_trials.csv")
    fig, axs = plt.subplots(2, 2, figsize=(9, 8), layout="constrained")
    ax = axs[0, 0]
    colors = ("#999999", "#333333")
    for group, (mode, label) in enumerate((("ask_v1_0", "Without default check"),
                                         ("ask_v1_1", "With default check"))):
        row = legacy.loc[mode]
        eligible = cases[(cases["mode"] == mode) & cases.expected_decision.isin(["accept", "partial_accept"])]
        denominator = len(eligible)
        assert denominator == 62
        record(stem, "a", label, "eligible_requests", float(denominator), "legacy_cases", denominator=200)
        violations = float(row.unsafe_execution_rate)
        completion = float(row.valid_release_rate)
        x = np.array([0, 1]) + (group - .5) * .3
        ax.bar(x, [violations, completion], width=.27, color=colors[group], label=label)
        for xx, value, count in zip(x, [violations, completion],
                                     [f"{round(violations * 200)}/200", f"{int(row.verified_result_count)}/62"]):
            ax.text(xx, value + .035, count, ha="center", fontsize=12.0)
        for endpoint, value, n in (("rule_violating_calculation", violations, 200),
                                   ("eligible_request_completion", completion, denominator)):
            record(stem, "a", label, endpoint, value, "legacy_modes", denominator=n)
    ax.set_title("(a) Archived paired replay", loc="left", pad=12, fontweight="bold")
    ax.set_ylabel("Request fraction")
    ax.set_xticks([0, 1], ["Rule-violating\ncalculation", "Eligible requests\nwith a result"])
    ax.set_ylim(0, 1.12)
    ax.set_yticks([0, .25, .5, .75, 1])
    ax.grid(axis="y", color="#E5E5E5", linewidth=.7)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left", borderpad=.1, handlelength=1.1)
    for y, service in enumerate(SERVICES):
        row = uniform.loc[service]
        axb = axs[0, 1]
        axb.plot(row.initial_clarification_rate, y - .11, "o", color=COLORS[service],
                 markerfacecolor="white", markersize=6.2, markeredgewidth=1.4)
        axb.plot(row.terminal_execution_readiness, y + .11, "s", color=COLORS[service], markersize=6.2)
        for endpoint in ("initial_clarification_rate", "terminal_execution_readiness"):
            record(stem, "b", NAMES[service], endpoint, float(row[endpoint]), "uniform_confirmation",
                   requests=14, trials=70, followups_per_trial=1)
    ax = axs[0, 1]
    rows(ax, list(NAMES.values()))
    style(ax, "(b) One scripted confirmation", "Fraction of 70 trials per service")
    ax.legend(handles=[Line2D([], [], marker="o", color=GRAY, markerfacecolor="white", linestyle="none", label="Initial clarify"),
                       Line2D([], [], marker="s", color=GRAY, linestyle="none", label="Final ready")],
              frameon=False, loc="upper left", borderpad=.1, handletextpad=.4)
    for y, service in enumerate(SERVICES):
        subset = dialogue[dialogue.service == service]
        n = len(subset)
        assert n == 70
        matched = float(subset.matching_completed_plan.sum()) / n
        accepted = float((subset.final_decision == "accept").sum()) / n
        median_seconds = float(subset.total_service_seconds.median())
        mean_replies = float(subset.additional_turns.mean())
        axc = axs[1, 0]
        axc.plot(accepted, y - .11, "s", color=COLORS[service], markerfacecolor="white", markersize=6.2, markeredgewidth=1.4)
        axc.plot(matched, y + .11, "o", color=COLORS[service], markersize=6.2)
        for endpoint, value in (("final_acceptance", accepted), ("matched_terminal_plan", matched),
                                 ("median_total_service_seconds", median_seconds), ("mean_additional_replies", mean_replies)):
            record(stem, "c" if endpoint in ("final_acceptance", "matched_terminal_plan") else "d",
                   NAMES[service], endpoint, value, "question_dialogue", requests=14, trials=n)
        axd = axs[1, 1]
        axd.barh(y, median_seconds, color=COLORS[service], height=.52, alpha=.85)
        axd.text(median_seconds + .8, y, f"{median_seconds:.2f} s", va="center", fontsize=12.0)
    ax = axs[1, 0]
    rows(ax, list(NAMES.values()))
    style(ax, "(c) Question-driven completion", "Fraction of 70 retained initial trials")
    ax.legend(handles=[Line2D([], [], marker="s", color=GRAY, markerfacecolor="white", linestyle="none", label="Final accept"),
                       Line2D([], [], marker="o", color=GRAY, linestyle="none", label="Matched fields")],
              frameon=False, loc="upper left", borderpad=.1, handletextpad=.4)
    ax = axs[1, 1]
    labels = [f"{NAMES[s]}\n{dialogue[dialogue.service == s].additional_turns.mean():.2f} replies"
              for s in SERVICES]
    rows(ax, labels)
    style(ax, "(d) Question-driven reply burden", "Median total service time (s)", fraction=False)
    ax.set_xlim(0, 66)
    ax.set_xticks([0, 20, 40, 60])
    export(fig, stem)


def main() -> None:
    configure()
    service_interfaces()
    draft_preparation()
    clarification()
    print(json.dumps({"figures": list(DATA), "output_directory": str(OUT),
                      "source_files": len(SOURCES), "new_resamples": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
