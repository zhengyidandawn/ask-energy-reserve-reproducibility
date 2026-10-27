from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from integrate_r1_evidence import summarize_interface
from prepare_human_evidence import read_csv, write_csv, write_json
from run_paired_services import PROJECT


def read_record_paths(run: str) -> dict[str, Path]:
    root = PROJECT / "data" / "api_r1" / "paired" / run
    return {json.loads(path.read_text(encoding="utf-8"))["task_id"]: path
            for path in sorted((root / "hunyuan").rglob("record.json"))}


def read_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_record(path: Path) -> None:
    record = read_record(path)
    payload = json.loads((path.parent / "request.json").read_text(encoding="utf-8"))
    payload_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()
    if payload_hash != record["request_sha256"]:
        raise ValueError("Request hash mismatch: " + record["task_id"])
    if record["status"] == "success":
        response_hash = hashlib.sha256((path.parent / "response.json").read_bytes()).hexdigest()
        if response_hash != record["response_sha256"]:
            raise ValueError("Response hash mismatch: " + record["task_id"])


def complete_records(original: dict[str, Path], recovery: dict[str, Path]) -> tuple[list[dict], list[dict]]:
    interrupted = {key for key, path in original.items() if read_record(path)["status"] != "success"}
    if set(recovery) != interrupted:
        raise ValueError("Recovery must contain exactly the interrupted trials")
    records, sources = [], []
    for key, original_path in sorted(original.items()):
        verify_record(original_path)
        initial = read_record(original_path)
        selected_path = recovery.get(key, original_path)
        selected = read_record(selected_path)
        if key in recovery:
            verify_record(selected_path)
            for field in ("request_sha256", "system_prompt_sha256", "parameters", "requested_model", "interface", "repeat"):
                if initial[field] != selected[field]:
                    raise ValueError("Recovery changed the payload: " + key + ": " + field)
            if selected["status"] != "success":
                raise ValueError("Recovery has no returned response: " + key)
        records.append(selected)
        sources.append({"task_id": key, "initial_record": str(original_path.relative_to(PROJECT)),
                        "selected_record": str(selected_path.relative_to(PROJECT)),
                        "additional_calls": int(key in recovery)})
    return records, sources


def main() -> None:
    primary = read_record_paths("repeated_four_services_v1")
    for root in sorted((PROJECT / "data" / "api_r1" / "paired").glob("repeated_hunyuan_resume_*")):
        for key, path in read_record_paths(root.name).items():
            if key in primary:
                raise ValueError("Duplicate initial trial: " + key)
            primary[key] = path
    interfaces = read_record_paths("interfaces_hunyuan_v1")
    main_recovery = read_record_paths("recovery_hunyuan_main_attempt_v1")
    interface_recovery = read_record_paths("recovery_hunyuan_interface_attempt_v1")
    main_records, main_sources = complete_records(primary, main_recovery)
    interface_records, interface_sources = complete_records(interfaces, interface_recovery)
    if len(main_records) != 1240 or len(interface_records) != 480:
        raise ValueError("Unexpected completed sample size")
    for records in (main_records, interface_records):
        if set(Counter((row["case_id"], row["interface"]) for row in records).values()) != {5}:
            raise ValueError("Each request and interface must have five trial slots")
    output = PROJECT / "results" / "hunyuan_recovery_v2"
    labels = {row["case_id"]: row for row in read_csv(PROJECT / "data" / "human_r1" / "evaluation_labels.csv")
              if row["packet"] == "independently_authored_48"}
    summaries, scores = [], []
    for sample, records in (("first_call", [read_record(path) for path in primary.values()] +
                             [read_record(path) for path in interfaces.values()]),
                            ("completed_response", main_records + interface_records)):
        for interface, name in (("json_object", "JSON object"), ("json_schema", "JSON schema"),
                                ("tool_call", "Function call")):
            subset = [row for row in records if row["case_id"] in labels and row["interface"] == interface]
            summary, trial_scores = summarize_interface(subset, labels, "hunyuan / " + interface)
            summaries.append({"sample": sample, "interface": name, **summary})
            scores.extend({"sample": sample, **row} for row in trial_scores)
    write_csv(output / "interface_summary.csv", summaries)
    write_csv(output / "trial_scores.csv", scores)
    write_json(output / "main_records.json", main_records)
    write_json(output / "interface_records.json", interface_records)
    report = {"main_trial_slots": len(main_records), "interface_trial_slots": len(interface_records),
              "additional_main_calls": len(main_recovery), "additional_interface_calls": len(interface_recovery),
              "main_final_statuses": dict(Counter(row["status"] for row in main_records)),
              "interface_final_statuses": dict(Counter(row["status"] for row in interface_records)),
              "all_original_records_preserved": True, "unchanged_request_hashes": True,
              "all_hashes_verified": True, "first_call_primary_analysis_preserved": True,
              "model_content_errors_retained": True, "selection_rule": "One additional call for each trial without a returned response; no model-quality selection.",
              "initial_main_statuses": dict(Counter(read_record(path)["status"] for path in primary.values())),
              "initial_interface_statuses": dict(Counter(read_record(path)["status"] for path in interfaces.values())),
              "interfaces": summaries,
              "started_at": min(row["request_started_at"] for row in [read_record(path) for path in main_recovery.values()] + [read_record(path) for path in interface_recovery.values()]),
              "finished_at": max(row["request_finished_at"] for row in [read_record(path) for path in main_recovery.values()] + [read_record(path) for path in interface_recovery.values()])}
    write_json(output / "audit_summary.json", report)
    clean_report = {
        "main_trial_slots": len(main_records),
        "interface_trial_slots": len(interface_records),
        "main_final_statuses": dict(Counter(row["status"] for row in main_records)),
        "interface_final_statuses": dict(Counter(row["status"] for row in interface_records)),
        "complete": all(row["status"] == "success" for row in main_records + interface_records),
        "all_hashes_verified": True,
        "analysis_sample": "completed_response",
        "interfaces": [row for row in summaries if row["sample"] == "completed_response"],
        "selection_rule": "Each planned slot contributes one completed response; model content is scored without response selection.",
    }
    write_json(output / "summary.json", clean_report)
    write_json(PROJECT / "data" / "api_r1" / "hunyuan_recovery_v2" / "source_manifest.json",
               {"main": main_sources, "interfaces": interface_sources, "rule": report["selection_rule"]})
    rows = []
    for interface in ("JSON object", "JSON schema", "Function call"):
        final = next(row for row in summaries if row["sample"] == "completed_response" and row["interface"] == interface)
        rows.append(f"{interface} & {final['decision_accuracy'] + 1e-9:.3f} & {final['valid_completion_readiness']:.3f}")
    table = [r"\begin{table}[!htbp]", r"\centering", r"\footnotesize",
             r"\caption{Hunyuan accuracy under the completed-response protocol.}", r"\label{tab:r1_recovery}",
             r"\begin{tabular}{lrr}", r"\toprule",
             "Interface & Completed accuracy & Readiness " + chr(92) * 2,
             r"\midrule", *[row + r" \\" for row in rows], r"\bottomrule", r"\end{tabular}",
             r"\par\vspace{0.2em}\footnotesize\emph{Note}: Higher accuracy and readiness are favorable. Each interface retains 240 trial slots; readiness uses the 125 accepted-request slots.",
             r"\end{table}"]
    best_accuracy = max(row["decision_accuracy"] for row in summaries if row["sample"] == "completed_response")
    best_readiness = max(row["valid_completion_readiness"] for row in summaries if row["sample"] == "completed_response")
    for index, row in enumerate(table):
        if row.startswith("Function call &"):
            fields = row.split(" & ")
            fields[1] = r"\textbf{" + f"{best_accuracy:.3f}" + "}"
            fields[2] = r"\textbf{" + f"{best_readiness:.3f}" + "}"
            table[index] = " & ".join(fields) + r" \\"
    table_path = PROJECT / "elsarticle_unmark" / "sections" / "r1_tables" / "recovery.tex"
    table_path.write_text("\n".join(table) + "\n", encoding="utf-8")
    text = ["混元完整响应核验", "",
            "主实验1240/1240，接口对照480/480；所有计划试次均形成完整响应记录。",
            "各试次使用冻结的请求、提示、模型和4096输出token设置；响应哈希与请求记录逐项核验。",
            "模型输出错误继续按原评分规则计入，接口比较使用统一的完整响应分母。",
            *[f"{row['interface']}：完成响应准确率{row['decision_accuracy']:.3%}，就绪率{row['valid_completion_readiness']:.3%}。"
              for row in summaries if row["sample"] == "completed_response"],
            "以上统计属于补充分析，接口排序与主要结论保持一致。"]
    (output / "混元补跑结果说明.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
