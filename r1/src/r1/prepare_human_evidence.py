from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT.parents[1]
SOURCE = PROJECT.parent / "人工记录"
DESTINATION = PROJECT / "data" / "human_r1"
RESULTS = PROJECT / "results" / "human_r1"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def cohen(first: list[str], second: list[str]) -> float:
    count = len(first)
    observed = sum(left == right for left, right in zip(first, second)) / count
    first_counts, second_counts = Counter(first), Counter(second)
    expected = sum(first_counts[label] * second_counts[label] for label in set(first + second)) / count**2
    return (observed - expected) / (1 - expected)


def fleiss(triples: list[list[str]]) -> float:
    observed = np.mean([sum(count * (count - 1) for count in Counter(triple).values()) / 6 for triple in triples])
    totals = Counter(label for triple in triples for label in triple)
    expected = sum((count / (3 * len(triples))) ** 2 for count in totals.values())
    return float((observed - expected) / (1 - expected))


def main() -> None:
    manifest = []
    for source in sorted(SOURCE.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(SOURCE)
        destination = DESTINATION / "source_snapshot" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest.append({"relative_path": relative.as_posix(), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    final = read_csv(SOURCE / "05_裁决与一致性" / "final_labels.csv")
    adjudication = {row["case_id"]: row for row in read_csv(SOURCE / "05_裁决与一致性" / "adjudication_log.csv")}
    independent = read_csv(SOURCE / "05_裁决与一致性" / "independent_annotation_records.csv")
    authored = {row["case_id"]: row for row in read_csv(SOURCE / "01_独立请求编写" / "independently_authored_requests.csv")}
    packets = {}
    for filename in ("frozen_annotation_packet.csv", "frozen_external_packet.csv"):
        packets.update({row["case_id"]: row for row in read_csv(SOURCE / "00_协议与冻结包" / filename)})
    annotations = {}
    for annotator in ("ANN-A", "ANN-B", "ANN-C"):
        for filename in ("labels.csv", "ext/labels_ext.csv"):
            for row in read_csv(SOURCE / "02_独立标注" / annotator / filename):
                key = (row["case_id"], annotator)
                if key in annotations:
                    raise ValueError("Duplicate annotation key")
                annotations[key] = row
    if len(annotations) != 504 or len(final) != 168:
        raise ValueError("Unexpected annotation count")
    for row in independent:
        original = annotations[(row["request_id"], row["annotator_id"])]
        for field in ("label", "annotation_timestamp", "confidence", "notes"):
            if original[field] != row[field]:
                raise ValueError("Annotation aggregation differs from its source")
    evaluation = []
    for row in final:
        identifier = row["case_id"]
        text = packets[identifier]["user_request"]
        record = {
            "case_id": identifier, "packet": row["packet"], "user_request": text,
            "text_cluster": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "source_class": row["source_class"], "expected_decision": row["final_label"],
            "request_type": authored.get(identifier, {}).get("request_type", packets[identifier].get("case_group", "")),
            "language": packets[identifier]["language"],
            "rule_derived_label": adjudication[identifier]["rule_derived_label"],
            "gold_region_id": "", "gold_horizon_minutes": "", "gold_cost_reserve": "", "gold_cost_shortfall": "",
            "gold_field_disagreements": "", "adjudicator_id": row["adjudicator_id"],
        }
        differences = []
        for field in ("region_id", "horizon_minutes", "cost_reserve", "cost_shortfall"):
            values = [annotations[(identifier, annotator)][field] for annotator in ("ANN-A", "ANN-B", "ANN-C")]
            counts = Counter(values)
            value, count = counts.most_common(1)[0]
            record["gold_" + field] = value if count >= 2 else ""
            if len(counts) > 1:
                differences.append(field)
        record["gold_field_disagreements"] = ";".join(differences)
        evaluation.append(record)
    write_csv(DESTINATION / "evaluation_labels.csv", evaluation)
    repairs = []
    experts = []
    for expert in ("EXP-1", "EXP-2", "EXP-3"):
        path = SOURCE / "03_专家对照" / expert / "timed_plans.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            for index, values in enumerate(reader, start=2):
                if len(values) != len(header):
                    if expert != "EXP-3" or index not in (2, 3, 4, 5) or len(values) != 14 or not values[8].startswith("calendar;"):
                        raise ValueError("Unexpected expert CSV damage")
                    values.insert(8, "")
                    repairs.append({"source": path.relative_to(SOURCE).as_posix(), "csv_line": index,
                        "case_id": values[0], "action": "insert empty cost_shortfall field before shifted variable list",
                        "evidence": "15-column header; 14-cell row; variable list occupied cost_shortfall; expert narrative specifies no execution"})
                record = dict(zip(header, values))
                if record["would_execute"] not in ("yes", "no"):
                    raise ValueError("Invalid expert execution value after repair")
                experts.append(record)
    write_csv(DESTINATION / "expert_plans_normalized.csv", experts)
    approvals = read_csv(SOURCE / "04_审批门" / "approval_decisions.csv")
    write_csv(DESTINATION / "approval_decisions.csv", approvals)
    summary = {"source_status": "author_supplied_human_evaluation_records", "independent_source_files_modified": False,
        "prepared_at": datetime.now(timezone.utc).isoformat(), "annotation_records": len(annotations),
        "unique_requests": len(final), "expert_plans": len(experts), "approval_records": len(approvals),
        "expert_timing_measure": "participant_estimated_minutes_as_specified_by_source_protocol",
        "expert_field_repairs": repairs, "packets": {}, "approval_counts": dict(Counter(row["approval_decision"] for row in approvals)),
        "expert_summary": []}
    for packet in ("blind_stratified_120", "independently_authored_48", "pooled_168"):
        subset = [row for row in final if packet == "pooled_168" or row["packet"] == packet]
        triples = [[row["annotator_" + suffix] for suffix in ("A", "B", "C")] for row in subset]
        summary["packets"][packet] = {"n": len(subset), "unique_texts": len({packets[row["case_id"]]["user_request"] for row in subset}),
            "unanimous": sum(len(set(triple)) == 1 for triple in triples), "fleiss_kappa": fleiss(triples),
            "cohen_AB": cohen([triple[0] for triple in triples], [triple[1] for triple in triples]),
            "cohen_AC": cohen([triple[0] for triple in triples], [triple[2] for triple in triples]),
            "cohen_BC": cohen([triple[1] for triple in triples], [triple[2] for triple in triples]),
            "final_counts": dict(Counter(row["final_label"] for row in subset))}
    for expert in ("EXP-1", "EXP-2", "EXP-3"):
        rows = [row for row in experts if row["expert_id"] == expert]
        summary["expert_summary"].append({"expert_id": expert, "n": len(rows),
            "estimated_total_minutes": sum(float(row["elapsed_minutes"]) for row in rows),
            "label_counts": dict(Counter(row["label"] for row in rows)),
            "would_execute_yes": sum(row["would_execute"] == "yes" for row in rows)})
    summary["rule_label_differences"] = [row["case_id"] for row in evaluation if row["rule_derived_label"] and row["rule_derived_label"] != row["expected_decision"]]
    write_json(RESULTS / "audit_summary.json", summary)
    write_json(DESTINATION / "source_manifest.json", {"prepared_at": summary["prepared_at"], "files": manifest,
        "repairs_applied_only_to_derived_expert_table": repairs,
        "provenance_note": "File integrity and arithmetic are checked. Source personnel and completion timestamps are supplied by the authors."})
    print(json.dumps({key: summary[key] for key in ("annotation_records", "unique_requests", "expert_plans", "approval_counts", "rule_label_differences")}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
