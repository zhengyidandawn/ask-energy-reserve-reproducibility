from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
from statistics import mean, median
import sys
import zipfile

from lxml import etree
from pypdf import PdfReader

from build_final_response import NS, ORIGINAL, TEMPLATE
from workspace_paths import PROJECT

sys.path.insert(0, str(PROJECT / "src"))
from add_reviewer_labels import DELETIONS, accepted_text, sentence_span


SUBMISSION = PROJECT.parent / "提交_AEI_R1"
PACKAGE = SUBMISSION / "Reproducibility_package_AEI_R1"
OUTPUT = PROJECT / "results" / "delivery_validation"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def check_records() -> dict:
    manifest = rows(PACKAGE / "data" / "formal_api_records_manifest.csv")
    assert len(manifest) == 6680
    assert len({row["task_id"] for row in manifest}) == 6680
    counts = Counter()
    recovered = 0
    for row in manifest:
        run = row["source_run"].split("/")[-1]
        path = PACKAGE / "data" / "formal_api_records" / run / row["relative_record"]
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["status"] == "success"
        assert record["task_id"] == row["task_id"]
        assert digest(path) == row["sha256"]
        assert all((path.parent / name).is_file() for name in ("request.json", "response.json"))
        phase = "primary" if run.startswith("repeated_") else run.split("_", 1)[0]
        counts[phase] += 1
        recovered += "recovery" in row["completed_source"]
    assert counts == {"primary": 4960, "interfaces": 1440, "clarification": 280}
    assert recovered == 30
    return {"records": len(manifest), "phases": dict(counts), "recovered": recovered,
            "unique_tasks_and_hashes_verified": True}


def check_reconstructed_evidence() -> dict:
    comparisons = {}
    for name in ("controlled_calculations", "joint_summary", "joint_tests", "matched_24",
                 "block_length_sensitivity", "clarification_alignment_summary"):
        relative = Path("results") / "strengthening_20261011" / (name + ".csv")
        original = rows(PROJECT / relative)
        rebuilt = rows(PACKAGE / "results" / "reconstructed_evidence" / "strengthening_20261011" / (name + ".csv"))
        assert len(original) == len(rebuilt)
        for original_row, rebuilt_row in zip(original, rebuilt):
            assert original_row.keys() == rebuilt_row.keys()
            for column, value in original_row.items():
                if any(term in column.lower() for term in ("latency", "seconds", "path", "time_value")):
                    continue
                other = rebuilt_row[column]
                if value == other:
                    continue
                assert abs(float(value) - float(other)) <= 1e-12
        comparisons[name] = len(original)
    return comparisons


def check_positive_evidence() -> dict:
    root = Path("results") / "positive_revision_20261011"
    files = ("frozen_policy_summary.csv", "frozen_paired_intervals.csv", "review_workload_summary.csv",
             "review_workload_trials.csv", "execution_resource_accounting.csv", "api_budget_sensitivity.csv",
             "analysis_contract.json")
    for name in files:
        assert digest(PROJECT / root / name) == digest(PACKAGE / root / name)
    policy_rows = rows(PROJECT / root / "frozen_policy_summary.csv")
    assert len(policy_rows) == 32
    assert all(float(row["minimum_coverage"]) >= 0.95 for row in policy_rows)
    best = {}
    for country in ("DE", "AT", "BE", "NL"):
        candidates = [row for row in policy_rows if row["country"] == country]
        best[country] = min(candidates, key=lambda row: float(row["normalized_cost"]))["method"]
    assert best == {"DE": "Quantile predictor", "AT": "Scenario quantile",
                    "BE": "Scenario quantile", "NL": "Selected shrinkage"}
    workload = rows(PROJECT / root / "review_workload_summary.csv")
    assert [int(row["field_corrections"]) for row in workload] == [50, 91, 81, 122]
    assert sum(int(row["trials"]) for row in workload) == 480
    execution = rows(PROJECT / root / "execution_resource_accounting.csv")
    counts = {stage: sum(int(row["trials"]) for row in execution if row["stage"] == stage)
              for stage in ("Authorized calculation", "Returned preparation")}
    assert counts == {"Authorized calculation": 266, "Returned preparation": 174}
    return {"independently_rebuilt_files": len(files), "minimum_coverage_verified": True,
            "eight_policy_lowest_cost": best, "matched_workload_trials": 480,
            "execution_outcomes": counts, "review_time_basis": "derived from expert self-estimates and service latency"}


def paragraphs(path: Path) -> tuple[list, dict]:
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    document = etree.fromstring(parts["word/document.xml"])
    return document.findall("w:body/w:p", NS), parts


def check_substantive_evidence() -> dict:
    data = PACKAGE / "data" / "substantive_resolution_20261011"
    result = PACKAGE / "results" / "substantive_resolution_20261011"
    source_hashes = set()
    initial_records = {}
    phases = Counter()
    trials = Counter()
    for phase in ("initial", "confirmation"):
        for path in sorted((data / "six_fields" / phase).glob("*/*/record.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            assert record["status"] == "success"
            assert record["phase"] == phase
            assert digest(path.parent / "request.json") == record["request_sha256"]
            assert digest(path.parent / "response.json") == record["response_sha256"]
            source_hashes.add(record["response_sha256"])
            if phase == "initial":
                initial_records[record["service"], record["case_id"], str(record["repeat"])] = record
            phases[phase] += 1
            trials[record["service"], phase] += 1
    assert phases == {"initial": 300, "confirmation": 60}
    assert all(trials[service, "initial"] == 75 and trials[service, "confirmation"] == 15
               for service in ("deepseek", "qwen", "ernie", "hunyuan"))
    cases = {case["case_id"]: case for case in json.loads((data / "six_fields" / "cases.json").read_text(encoding="utf-8"))}
    scored_trials = rows(result / "six_field_trials.csv")
    assert len(scored_trials) == len(initial_records) == 300
    for row in scored_trials:
        record = initial_records[row["service"], row["case_id"], row["repeat"]]
        reference = cases[row["case_id"]]["gold"]
        if reference["decision"] == "reject":
            assert row["field_comparison_applicable"] == "False" and row["field_replacements"] == ""
            assert row["terminal_execution_ready"] == "False"
        else:
            study = (record.get("parsed_output") or {}).get("study") or {}
            required = sum(study.get(name) != value for name, value in reference["fields"].items() if value is not None)
            assert row["field_comparison_applicable"] == "True"
            assert int(row["field_replacements"]) == required
    output_paths = sorted((result / "executed_outputs").glob("*.json"))
    assert len(output_paths) == 196
    for path in output_paths:
        output = json.loads(path.read_text(encoding="utf-8"))
        assert output["source_response_sha256"] in source_hashes
        assert output["study"]["human_authorization_required"] is True
        assert output["result"]["reserve_equal"] is True
        assert output["result"]["reporting_correct"] is True
        assert output["result"]["paired_cost_difference"] == 0
    coverage = json.loads((result / "six_field_coverage.json").read_text(encoding="utf-8"))
    assert [row["executed"] for row in coverage] == [16, 17, 17, 18, 13, 17, 17, 19, 15]
    faults = rows(result / "field_fault_injections.csv")
    assert len(faults) == 95 and all(row["blocked"] == "True" for row in faults)
    assert all(row["source_response_sha256"] in source_hashes for row in faults)
    assert len({row["changed_field"] for row in faults}) == 6
    maintenance = rows(result / "maintenance_changes.csv")
    assert len(maintenance) == 6
    assert sum(int(row["new_value_checks"]) for row in maintenance) == 540
    assert sum(int(row["regression_passed"]) for row in maintenance) == 90
    for row in maintenance:
        root = data / "maintenance" / row["changed_field"]
        assert all((root / name).is_file() for name in (
            "before.json", "after.json", "change.diff", "generated_form_choices.json",
            "generated_parser_vocabulary.json", "generated_schema.json", "regression.json"))
        regression = json.loads((root / "regression.json").read_text(encoding="utf-8"))
        plans = regression["new_value_checks"]
        assert len(plans) == regression["distinct_new_value_plans"] == 30
        assert len({json.dumps(item["plan"], sort_keys=True) for item in plans}) == 30
        assert all(set(item["before"].values()) == {"rejected"} and
                   set(item["after"].values()) == {"accepted"} for item in plans)
    work = rows(result / "input_workload_summary.csv")
    assert [int(row["required_replacements"]) for row in work] == [70, 96, 116, 140]
    assert all(int(row["manual_entries"]) == 265 for row in work)
    for row in work:
        assert int(row["retained_entries"]) + int(row["required_replacements"]) == 265
        assert abs(float(row["input_reduction"]) - int(row["retained_entries"]) / 265) < 1e-12
    costs = rows(result / "provider_cost_trials.csv")
    assert len(costs) == 960
    totals = Counter()
    for row in costs:
        ordinary = int(row["input_tokens"]) - int(row["cached_tokens"])
        calculated = (ordinary * float(row["input_rate"]) + int(row["cached_tokens"]) *
                      float(row["cache_rate"]) + int(row["output_tokens"]) * float(row["output_rate"])) / 1e6
        assert abs(calculated - float(row["list_price_cost"])) < 1e-12
        totals[row["service"]] += calculated
    for row in rows(result / "provider_cost_summary.csv"):
        assert abs(totals[row["service"]] - float(row["list_price_cost"])) < 1e-12
    tariffs = json.loads((data / "pricing" / "tariffs.json").read_text(encoding="utf-8"))
    assert len(tariffs["source_hashes"]) == 4
    for name, expected in tariffs["source_hashes"].items():
        assert digest(data / "pricing" / name) == expected
    for name in ("provider_cost_trials.csv", "provider_cost_summary.csv", "input_workload_trials.csv",
                 "input_workload_summary.csv", "six_field_trials.csv", "six_field_summary.csv",
                 "six_field_outcome_resources.csv", "six_field_consequences.csv", "field_fault_injections.csv",
                 "field_fault_summary.csv", "six_field_coverage.json", "analysis_contract.json"):
        assert digest(result / name) == digest(PROJECT / "results" / "substantive_resolution_20261011" / name)
    return {"service_responses": dict(phases), "record_hashes_verified": True,
            "reference_matched_offline_outputs": len(output_paths), "controlled_deviations": len(faults),
            "maintenance_new_value_checks": 540, "maintenance_request_regressions": 90,
            "variable_input_entries_per_service": 265, "provider_price_snapshots": 4,
            "fee_calculations_verified": len(costs),
            "human_time_basis": "self-estimates and conditional review thresholds"}


def check_online_evidence() -> dict:
    from analyze_paired_evidence import normalize
    from deterministic_interfaces import validate_plan
    from run_online_draft_audit import adapted_output

    relative_data = Path("data") / "online_draft_audit_20261011"
    relative_result = Path("results") / "online_draft_audit_20261011"
    data = PACKAGE / relative_data
    result = PACKAGE / relative_result
    protocol = json.loads((data / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["checker_sha256"] == digest(PACKAGE / "src/r1/deterministic_interfaces.py")
    assert protocol["parameters"] == {"temperature": 0, "top_p": 1, "max_tokens": 4096}
    assert protocol["repeats"] == 5 and protocol["maximum_feedback_calls"] == 1
    assert protocol["label_source_sha256"] == digest(PACKAGE / "data/human_r1/evaluation_labels.csv")
    assert protocol["expert_source_sha256"] == digest(PACKAGE / "data/human_r1/expert_plans_normalized.csv")
    cases = {row["case_id"]: row["user_request"] for row in json.loads((data / "cases.json").read_text(encoding="utf-8"))}
    assert len(cases) == 24 and len(set(cases.values())) == 21
    labels = {row["case_id"]: row for row in rows(PACKAGE / "data/human_r1/evaluation_labels.csv")}
    records = {}
    phases = Counter()
    for phase in ("initial", "feedback"):
        for path in sorted((data / phase).glob("*/*/record.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            key = (record["service"], record["case_id"], str(record["repeat"]), phase)
            assert key not in records and record["status"] == "success"
            assert record["phase"] == phase and record["parameters"] == protocol["parameters"]
            assert digest(path.parent / "request.json") == record["request_sha256"]
            assert digest(path.parent / "response.json") == record["response_sha256"]
            request = json.loads((path.parent / "request.json").read_text(encoding="utf-8"))
            response = json.loads((path.parent / "response.json").read_text(encoding="utf-8"))
            assert request["messages"][0] == {"role": "system", "content": protocol["system_prompt"]}
            assert request["messages"][1] == {"role": "user", "content": cases[record["case_id"]]}
            assert len(request["messages"]) == (2 if phase == "initial" else 4)
            assert response["usage"] == record["usage"] and response["model"] == record["returned_model"]
            assert response["choices"][0]["message"].get("content", "") == record["content"]
            assert record["diagnostics"]["reference_labels_used"] is False
            assert record["started_at"] >= protocol["frozen_at"]
            if phase == "feedback":
                initial = records[key[:3] + ("initial",)]
                assert request["messages"][2] == {"role": "assistant", "content": initial["content"]}
                assert request["messages"][3]["content"] == (
                    "Frozen checker feedback: " + " ".join(initial["diagnostics"]["messages"])
                    + " Return the corrected complete draft.")
            records[key] = record
            phases[phase] += 1
    assert phases == {"initial": 480, "feedback": 54}
    trials = {}
    for path in sorted((data / "trials").glob("*/*.json")):
        trial = json.loads(path.read_text(encoding="utf-8"))
        key = (trial["service"], trial["case_id"], str(trial["repeat"]))
        assert key not in trials and trial["transport_complete"] is True
        initial = records[key + ("initial",)]
        terminal = records.get(key + ("feedback",), initial)
        assert trial["initial_record"] == initial and trial["terminal_record"] == terminal
        assert trial["online_calls"] == 1 + (key + ("feedback",) in records)
        expected_seconds = initial["latency_seconds"] + (terminal["latency_seconds"] if trial["online_calls"] == 2 else 0)
        assert abs(trial["total_service_seconds"] - expected_seconds) < 1e-10
        trials[key] = trial
    services = ("deepseek", "qwen", "ernie", "hunyuan")
    assert set(trials) == {(service, case, str(repeat)) for service in services for case in cases for repeat in range(5)}
    details = rows(result / "trial_scores.csv")
    assert len(details) == 960
    metrics = ("raw_correct", "validated_correct", "field_correct", "field_total", "manual_entries",
               "retained_entries", "required_replacements", "unsafe_ready", "valid_ready", "reference_accept")
    for row in details:
        trial = trials[row["service"], row["case_id"], row["repeat"]]
        record = trial[row["stage"] + "_record"]
        label = labels[row["case_id"]]
        candidate = record.get("parsed_output") or {}
        fields = candidate.get("fields") or {}
        reference = [(name, label["gold_" + name]) for name in
                     ("region_id", "horizon_minutes", "cost_reserve", "cost_shortfall")
                     if label["gold_" + name] not in (None, "")]
        correct = sum(normalize(name, fields.get(name)) == normalize(name, value) for name, value in reference)
        variable = [(name, value) for name, value in reference if name != "cost_reserve"]
        reused = int(candidate.get("decision") == label["expected_decision"]) + sum(
            normalize(name, fields.get(name)) == normalize(name, value) for name, value in variable)
        gate = validate_plan(label["user_request"], adapted_output(candidate))
        expected = {"raw_correct": int(candidate.get("decision") == label["expected_decision"]),
                    "validated_correct": int(gate["decision"] == label["expected_decision"]),
                    "field_correct": correct, "field_total": len(reference), "manual_entries": 1 + len(variable),
                    "retained_entries": reused, "required_replacements": 1 + len(variable) - reused,
                    "unsafe_ready": int(gate["execution_ready"] and label["expected_decision"] != "accept"),
                    "valid_ready": int(gate["execution_ready"] and label["expected_decision"] == "accept"),
                    "reference_accept": int(label["expected_decision"] == "accept")}
        assert all(int(row[name]) == value for name, value in expected.items())
        assert row["response_sha256"] == record["response_sha256"]
    terminal_summary = {}
    for summary in rows(result / "stage_summary.csv"):
        subset = [row for row in details if row["service"] == summary["service"] and row["stage"] == summary["stage"]]
        assert len(subset) == int(summary["trials"]) == 120
        assert all(int(summary[name]) == sum(int(row[name]) for row in subset) for name in metrics)
        assert int(summary["manual_entries"]) == 265 and int(summary["field_total"]) == 200
        assert int(summary["retained_entries"]) + int(summary["required_replacements"]) == 265
        assert abs(float(summary["retained_fraction"]) - int(summary["retained_entries"]) / 265) < 1e-12
        assert abs(float(summary["median_service_seconds"]) - median(float(row["service_seconds"]) for row in subset)) < 1e-10
        if summary["stage"] == "terminal":
            terminal_summary[summary["service"]] = {name: int(summary[name]) for name in metrics}
    prices = rows(result / "provider_cost_trials.csv")
    assert len(prices) == len(records) == 534
    totals = Counter()
    for row in prices:
        ordinary = int(row["input_tokens"]) - int(row["cached_tokens"])
        fee = (ordinary * float(row["input_rate"]) + int(row["cached_tokens"]) * float(row["cache_rate"])
               + int(row["output_tokens"]) * float(row["output_rate"])) / 1e6
        assert abs(fee - float(row["list_price_cost"])) < 1e-12
        totals[row["service"]] += fee
    for row in rows(result / "provider_cost_summary.csv"):
        assert abs(totals[row["service"]] - float(row["total_list_price_cost"])) < 1e-12
        assert abs(totals[row["service"]] / 120 - float(row["mean_fee_per_trial"])) < 1e-12
    experts = rows(PACKAGE / "data/human_r1/expert_plans_normalized.csv")
    sensitivity = rows(result / "conditional_time_sensitivity.csv")
    assert len(sensitivity) == 180
    assert len({(row["service"], row["review_seconds_per_entry"], row["correction_seconds_per_replacement"], row["overhead_seconds"]) for row in sensitivity}) == 180
    for row in sensitivity:
        subset = [detail for detail in details if detail["service"] == row["service"] and detail["stage"] == "terminal"]
        durations = [float(detail["service_seconds"]) + float(row["review_seconds_per_entry"]) * int(detail["manual_entries"])
                     + float(row["correction_seconds_per_replacement"]) * int(detail["required_replacements"])
                     + float(row["overhead_seconds"]) for detail in subset]
        references = [60 * mean(float(expert["elapsed_minutes"]) for expert in experts if expert["case_id"] == detail["case_id"]) for detail in subset]
        assert abs(median(durations) - float(row["median_modeled_seconds"])) < 1e-10
        assert abs(mean(duration < reference for duration, reference in zip(durations, references))
                   - float(row["fraction_below_expert_estimate"])) < 1e-12
    for relative in (relative_data, relative_result, Path("results/remaining_review_questions_20261011")):
        for path in (PACKAGE / relative).rglob("*"):
            if path.is_file():
                assert digest(path) == digest(PROJECT / path.relative_to(PACKAGE))
    manifest = json.loads((result / "analysis_manifest.json").read_text(encoding="utf-8"))
    assert manifest["protocol_sha256"] == digest(data / "protocol.json")
    assert manifest["human_measurements_added"] == 0
    return {"requests": 24, "distinct_request_texts": 21, "trials": len(trials), "calls": dict(phases),
            "request_response_and_source_hashes_verified": True, "terminal_quality": terminal_summary,
            "verified_fee_calculations": len(prices), "verified_conditional_time_scenarios": len(sensitivity),
            "human_time_basis": "existing expert self-estimates and explicit review/correction/overhead assumptions"}


def text_of(paragraph) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))


def check_letters() -> dict:
    _, reviewer_one, overall_two, reviewer_two, overall_three, reviewer_three = ORIGINAL.extract_comments()
    comments = reviewer_one + reviewer_two + reviewer_three
    assert len(comments) == 28
    template_paragraphs, template_parts = paragraphs(TEMPLATE)
    paragraph_properties = {
        etree.tostring(value) if value is not None else None
        for paragraph in template_paragraphs
        for value in [paragraph.find("w:pPr", NS)]
    }
    run_properties = {
        etree.tostring(value) if value is not None else None
        for paragraph in template_paragraphs for run in paragraph.findall("w:r", NS)
        for value in [run.find("w:rPr", NS)]
    }
    report = {}
    language_identifiers = []
    forbidden = re.compile(r"rather than|not only|instead of|不是|不仅|不宣称|internal normalized", re.I)
    third_person_self_reference = re.compile(
        r"author[- ](?:designed|created|generated|written)|the authors?\b|作者(?:设计|编写|构建|增加|补充|认为)|本文作者|研究团队", re.I)
    for language in ("CN", "EN"):
        path = SUBMISSION / ("Response_to_Reviewers_AEI_R1_" + language + ".docx")
        elements, parts = paragraphs(path)
        texts = [text_of(paragraph) for paragraph in elements]
        combined = "\n".join(texts)
        assert all(comment in combined for comment in comments + [overall_two, overall_three])
        identifiers = [text for text in texts if re.fullmatch(r"R[123]-\d+", text)]
        assert len(identifiers) == 28
        language_identifiers.append(identifiers)
        for paragraph in elements:
            value = paragraph.find("w:pPr", NS)
            assert (etree.tostring(value) if value is not None else None) in paragraph_properties
            for run in paragraph.findall("w:r", NS):
                value = run.find("w:rPr", NS)
                assert (etree.tostring(value) if value is not None else None) in run_properties
        preserved = [name for name in template_parts if name not in ("word/document.xml", "docProps/core.xml")]
        assert all(parts[name] == template_parts[name] for name in preserved)
        author_responses = [text for text in texts if text.startswith(("Response: ", "回复："))]
        assert all(forbidden.search(text) is None for text in author_responses)
        assert all(third_person_self_reference.search(text) is None for text in author_responses)
        specific_responses = []
        overall_responses = []
        current_identifier = None
        for text in texts:
            if re.fullmatch(r"R[123]-\d+", text):
                current_identifier = text
            elif text.startswith(("对审稿人", "Responses to Reviewer", "总体意见", "Overall assessment")):
                current_identifier = None
            elif text.startswith(("Response: ", "回复：")):
                if current_identifier is None:
                    overall_responses.append(text)
                else:
                    specific_responses.append((current_identifier, text))
                    current_identifier = None
        assert [identifier for identifier, response in specific_responses] == identifiers
        assert len(overall_responses) == 2
        assert len(set(overall_responses)) == 2
        assert all("感谢" in text or "Thank you" in text for text in overall_responses)
        assert all(any(character.isdigit() for character in response)
                   for identifier, response in specific_responses)
        viewpoint = ("我们认为，修改后的稿件仍然契合Advanced Engineering Informatics"
                     if language == "CN" else "We believe that the revised manuscript remains aligned")
        assert viewpoint in combined
        summary_properties = [dict(element.find("w:pPr/w:ind", NS).attrib)
                              for element in elements if re.match(r"^[（(]\d+[）)]", text_of(element))]
        assert len(summary_properties) == 5
        report[language] = {"original_comments": 28, "overall_assessments": 2,
                            "specific_responses_with_quantitative_evidence": len(specific_responses),
                            "distinct_overall_acknowledgments": len(overall_responses),
                            "author_qualified_vsi_statement": True,
                            "author_voice_checked_in_all_responses": len(author_responses),
                            "template_parts_preserved": len(preserved),
                            "paragraph_and_run_properties_preserved": True,
                            "summary_indentation": summary_properties}
    assert language_identifiers[0] == language_identifiers[1]
    return report


def check_sources() -> dict:
    counts = {}
    for original_name, submitted_name, archive_name in (
        ("elsarticle_unmark", "Source_unmark", "LaTeX_Source_unmark_AEI_R1.zip"),
        ("elsarticle_mark", "Source_mark", "LaTeX_Source_mark_AEI_R1.zip"),
    ):
        original_root = PROJECT / original_name
        submitted_root = SUBMISSION / submitted_name
        originals = {path.relative_to(original_root).as_posix(): path
                     for path in original_root.rglob("*") if path.is_file()}
        submitted = {path.relative_to(submitted_root).as_posix(): path
                     for path in submitted_root.rglob("*") if path.is_file()}
        assert originals.keys() == submitted.keys()
        assert all(digest(originals[name]) == digest(submitted[name]) for name in originals)
        with zipfile.ZipFile(SUBMISSION / archive_name) as archive:
            files = {name.split("/", 1)[1]: name for name in archive.namelist() if not name.endswith("/")}
            assert originals.keys() == files.keys()
            assert all(hashlib.sha256(archive.read(files[name])).hexdigest() == digest(originals[name])
                       for name in originals)
        counts[submitted_name] = len(originals)
    for name in ("compile_aei_r1.ps1", "mark_aei_r1.ps1", "build_word_manuscript.ps1",
                 "prepare_word_source.py", "normalize_word_tables.py", "package_aei_r1.ps1", "build_supplementary.ps1",
                 "add_reviewer_labels.py", "resolve_deleted_references.py", "r1_latexdiff_preamble.tex"):
        assert digest(PROJECT / "src" / name) == digest(SUBMISSION / "Compilation_scripts" / name)
    return counts


def check_manuscripts() -> dict:
    report = {}
    forbidden = re.compile(r"rather than|not only|instead of|不是|不仅|(?<![A-Za-z])[A-Z]:[\\/]|internal normalized metric", re.I)
    for filename in ("Manuscript_unmark.pdf", "Manuscript_mark.pdf", "补充材料.pdf"):
        reader = PdfReader(SUBMISSION / filename)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert "??" not in text
        if "mark.pdf" not in filename or "unmark.pdf" in filename:
            assert forbidden.search(text.split("References")[0]) is None
        report[filename] = {"pages": len(reader.pages), "characters": len(text)}
    source = (PROJECT / "elsarticle_unmark" / "main.tex").read_text(encoding="utf-8")
    title = re.search(r"\\title\s*\[.*?\]\{(.*?)\}", source)[1]
    title_file = (SUBMISSION / "题目摘要关键词.txt").read_text(encoding="utf-8")
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", source, re.S)[1].strip()
    assert title in title_file and abstract in title_file
    document_paragraphs, _ = paragraphs(SUBMISSION / "Manuscript_unmark.docx")
    word_text = "\n".join(text_of(paragraph) for paragraph in document_paragraphs)
    assert title in word_text
    assert digest(SUBMISSION / "Manuscript_unmark.docx") == digest(PROJECT / "results" / "Manuscript_unmark.docx")
    for evidence in ("265 variable entries", "196 numerical outputs", "95 controlled deviations",
                     "0.082259", "540 new-value checks", "480 initial responses and 54 automatic feedback responses",
                     "255/265", "193/200", "260/265"):
        assert evidence in word_text, evidence
    report["word_copy_and_substantive_results_synchronized"] = True
    report["title_and_abstract_synchronized"] = True
    for relative in ("manuscript_unmark_build/main.log", "manuscript_mark_build/main.log",
                     "supplementary_build/Supplementary_Material.log"):
        log = (PROJECT / "results" / relative).read_text(encoding="utf-8", errors="replace")
        assert re.search(r"undefined references|Citation .* undefined|Reference .* undefined", log) is None
    return report


def check_selective_marking() -> dict:
    clean_root = PROJECT / "elsarticle_unmark"
    marked_root = PROJECT / "elsarticle_mark"
    manifest = json.loads((PROJECT / "results" / "selective_marking" / "marking_manifest.json").read_text(encoding="utf-8"))
    tags = Counter()
    verified = 0
    for clean_path in clean_root.rglob("*.tex"):
        relative = clean_path.relative_to(clean_root)
        marked_path = marked_root / relative
        clean = clean_path.read_text(encoding="utf-8-sig")
        marked = marked_path.read_text(encoding="utf-8-sig")
        assert accepted_text(clean) == accepted_text(marked), str(relative)
        assert re.search(r"\\Rlabel\{[^}]+\}\s*(?:\\Rsep)?\s*\\Rlabel", marked) is None
        tags.update(re.findall(r"\\Rlabel\{R\\#([^}]+)\}", marked))
        verified += 1
    assert len(tags) == 28 and set(tags.values()) == {1}
    assert manifest["accepted_content_verified"]
    assert manifest["deletion_spans"] == len(DELETIONS)
    selected_deletions = [entry for entry in manifest["marks"] if entry["deleted"]]
    assert len(selected_deletions) == len(DELETIONS)
    for entry in selected_deletions:
        deletion = entry["deletion_source"]
        original = (PROJECT / "baseline" / deletion["original_file"]).read_text(encoding="utf-8-sig")
        start, end = sentence_span(original, deletion["original_anchor"], deletion["sentences"])
        assert original[start:end] == deletion["original_text"]
        assert deletion["text"] == entry["deleted"]
        assert deletion["reviewer"] in tags
    assert manifest["deleted_sentences"] == sum(entry["deletion_source"]["sentences"] for entry in selected_deletions)
    assert manifest["grouped_reviewer_tags"] == 0
    return {"tex_files_with_identical_accepted_content": verified,
            "separate_reviewer_tags": len(tags), "substantive_text_spans": manifest["substantive_text_spans"],
            "selected_deletion_spans": manifest["deletion_spans"],
            "deleted_original_sentences": manifest["deleted_sentences"],
            "original_deletion_provenance_verified": True, "grouped_reviewer_tags": 0}


def check_package_inventory() -> dict:
    manifest = rows(PACKAGE / "package_manifest.csv")
    expected = {row["path"].replace("\\", "/") for row in manifest}
    actual = {path.relative_to(PACKAGE).as_posix() for path in PACKAGE.rglob("*") if path.is_file()
              and path.name != "package_manifest.csv"}
    assert expected == actual
    for row in manifest:
        path = PACKAGE / row["path"]
        assert digest(path) == row["sha256"]
        assert path.stat().st_size == int(row["bytes"])
    with zipfile.ZipFile(SUBMISSION / "Reproducibility_package_AEI_R1.zip") as archive:
        names = {name.split("/", 1)[1]: name for name in archive.namelist() if not name.endswith("/")}
        assert set(names) == actual | {"package_manifest.csv"}
        for relative, name in names.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest(PACKAGE / relative)
    return {"files": len(actual) + 1, "manifest_and_archive_hashes_verified": True}


def check_literature() -> dict:
    from verify_cited_references import cited_entries
    from verify_added_literature import DOIS
    root = PROJECT / "data" / "literature" / "cited_reference_verification_20261011"
    references = json.loads((root / "cited_references.json").read_text(encoding="utf-8"))
    archive_checks = {row["key"]: row for row in json.loads((root / "archive_reference_checks.json").read_text(encoding="utf-8"))}
    assert {row["bibliography"]["key"] for row in references} == set(cited_entries())
    assert all(row["status"] == "verified_doi" or archive_checks[row["bibliography"]["key"]]["verified"]
               for row in references)
    additions = json.loads((PROJECT / "data" / "literature" / "strengthening_20261011" / "verified_additions.json").read_text(encoding="utf-8"))
    assert {row["key"] for row in additions} == set(DOIS)
    assert all(row["doi"].lower() == DOIS[row["key"]].lower() for row in additions)
    return {"cited_references": len(references), "verified_added_references": len(additions),
            "doi_metadata_checks": sum(row["status"] == "verified_doi" for row in references),
            "publisher_and_archive_checks": len(archive_checks)}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {"completed_records": check_records(), "cached_reconstruction": check_reconstructed_evidence(),
              "positive_evidence": check_positive_evidence(), "substantive_evidence": check_substantive_evidence(),
              "online_evidence": check_online_evidence(),
              "letters": check_letters(), "source_packages": check_sources(),
              "manuscripts": check_manuscripts(), "literature": check_literature(),
              "selective_marking": check_selective_marking(),
              "reproducibility_inventory": check_package_inventory()}
    report["passed"] = True
    (OUTPUT / "delivery_checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
