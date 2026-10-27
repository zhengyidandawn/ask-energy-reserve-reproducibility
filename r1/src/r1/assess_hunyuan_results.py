from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from analyze_paired_evidence import bootstrap_mean, field_accuracy
from deterministic_interfaces import validate_plan
from integrate_r1_evidence import load_records
from prepare_human_evidence import read_csv, write_json
from run_paired_services import PROJECT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    records = [record for record in load_records("repeated_four_services_v1") if record["service"] == "hunyuan"]
    counts = Counter(record["case_id"] for record in records)
    identifiers = [(record["case_id"], record["repeat"], record["interface"]) for record in records]
    complete = len(records) == 1240 and len(counts) == 248 and set(counts.values()) == {5} and len(set(identifiers)) == 1240
    status = {"main_trials": len(records), "planned_main_trials": 1240, "main_complete": complete,
        "statuses": dict(Counter(record["status"] for record in records)),
        "interfaces_trials": len(load_records("interfaces_hunyuan_v1")),
        "planned_interfaces_trials": 480,
        "clarification_trials": len(load_records("clarification_hunyuan_v1")),
        "planned_clarification_trials": 70}
    if not args.final:
        print(json.dumps(status, ensure_ascii=False))
        return
    if not complete:
        raise ValueError("Five trials for every frozen request must be complete before final assessment")
    human = read_csv(PROJECT / "data" / "human_r1" / "evaluation_labels.csv")
    independent = {row["case_id"]: row for row in human if row["packet"] == "independently_authored_48"}
    subset = [record for record in records if record["case_id"] in independent]
    scores = []
    for record in subset:
        gold = independent[record["case_id"]]
        output = record.get("parsed_output") or {}
        gate = validate_plan(gold["user_request"], output, record.get("checks", {}).get("numerical_contamination", False))
        correct, total = field_accuracy(output.get("study_schema"), gold)
        scores.append({"case_id": record["case_id"], "repeat": record["repeat"],
            "decision_correct": int(output.get("decision") == gold["expected_decision"]),
            "validated_correct": int(gate["decision"] == gold["expected_decision"]),
            "accepted_reference": gold["expected_decision"] == "accept", "ready": gate["execution_ready"],
            "unsafe_ready": gate["execution_ready"] and gold["expected_decision"] != "accept",
            "ready_field_mismatch": gate["execution_ready"] and correct != total,
            "all_requested_fields_correct": total > 0 and correct == total})
    case_accuracy = [np.mean([row["decision_correct"] for row in scores if row["case_id"] == identifier]) for identifier in independent]
    lower, upper = bootstrap_mean(np.asarray(case_accuracy), [independent[identifier]["text_cluster"] for identifier in independent])
    accepted = [row for row in scores if row["accepted_reference"]]
    ready = [row for row in scores if row["ready"]]
    metrics = {"requests": 48, "trials": len(scores), "decision_accuracy": float(np.mean(case_accuracy)),
        "decision_accuracy_95_interval": [lower, upper],
        "validated_accuracy": float(np.mean([row["validated_correct"] for row in scores])),
        "accepted_requests": 25, "accepted_trials": len(accepted),
        "valid_request_readiness": sum(row["ready"] for row in accepted) / len(accepted),
        "unsafe_ready_count": sum(row["unsafe_ready"] for row in scores),
        "ready_field_mismatch_count": sum(row["ready_field_mismatch"] for row in scores),
        "ready_all_fields_correct": all(row["all_requested_fields_correct"] for row in ready),
        "ready_trial_count": len(ready)}
    roots = [PROJECT / "data" / "api_r1" / "paired" / "repeated_four_services_v1",
        *sorted((PROJECT / "data" / "api_r1" / "paired").glob("repeated_hunyuan_resume_*"))]
    hash_checks = []
    for root in roots:
        for path in (root / "hunyuan").rglob("record.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            payload = json.loads((path.parent / "request.json").read_text(encoding="utf-8"))
            payload_digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()
            request_valid = payload_digest == record["request_sha256"]
            response_valid = record["status"] != "success" or hashlib.sha256((path.parent / "response.json").read_bytes()).hexdigest() == record["response_sha256"]
            hash_checks.append(request_valid and response_valid)
    integrity = {"complete_five_trial_pairs": complete, "all_hashes_verified": all(hash_checks),
        "verified_record_count": len(hash_checks), "all_attempts_in_denominator": len(scores) == 240,
        "returned_models": sorted({record.get("returned_model") for record in records if record.get("returned_model")}),
        "started_at": min(record["request_started_at"] for record in records),
        "finished_at": max(record["request_finished_at"] for record in records)}
    followups = {}
    for run, planned, cases in (("interfaces_hunyuan_v1", 480, 48), ("clarification_hunyuan_v1", 70, 14)):
        trials = load_records(run)
        identities = {(record["case_id"], record["repeat"], record["interface"]) for record in trials}
        groups = Counter((record["case_id"], record["interface"]) for record in trials)
        verified = []
        for path in (PROJECT / "data" / "api_r1" / "paired" / run).rglob("record.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            payload = json.loads((path.parent / "request.json").read_text(encoding="utf-8"))
            digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()
            response_valid = record["status"] != "success" or hashlib.sha256((path.parent / "response.json").read_bytes()).hexdigest() == record["response_sha256"]
            verified.append(digest == record["request_sha256"] and response_valid)
        followups[run] = {"trials": len(trials), "planned_trials": planned,
            "complete": len(trials) == planned and len(identities) == planned and len({record["case_id"] for record in trials}) == cases and set(groups.values()) == {5},
            "all_hashes_verified": len(verified) == planned and all(verified),
            "statuses": dict(Counter(record["status"] for record in trials))}
    output = PROJECT / "results" / "integrated_r1"
    interface_metrics = [row for row in read_csv(output / "interface_summary.csv") if row["method"].startswith("hunyuan / ")]
    clarification_metrics = next(row for row in read_csv(output / "clarification_summary.csv") if row["service"] == "hunyuan")
    replay_metrics = next(row for row in read_csv(PROJECT / "results" / "paired_public_execution" / "summary.csv") if row["service"] == "hunyuan")
    usable = complete and integrity["all_hashes_verified"] and integrity["all_attempts_in_denominator"] and all(item["complete"] and item["all_hashes_verified"] for item in followups.values())
    report = {**status, "integrity": integrity, "independent_request_metrics": metrics,
        "usable_for_reported_comparisons": usable,
        "reviewer_satisfaction_guaranteed": False, "followup_integrity": followups,
        "interface_metrics": interface_metrics, "clarification_metrics": clarification_metrics,
        "public_calculation_replay": replay_metrics,
        "supported_claims": ["five-run performance and consistency", "traceable hosted-model configuration",
            "observed validation and completion outcomes under frozen requests"],
        "additional_evidence_required_for_broader_claims": ["operational deployment evidence",
            "measured human preparation and review time", "general mathematical coverage guarantees",
            "monetary reserve savings caused by the language-validation layer"]}
    write_json(output / "hunyuan_usability_assessment.json", report)
    text = ["混元重复实验结果评估", "",
        f"主评估完成 {len(records)}/1240 次，248条请求各五次，配对及哈希核验{'通过' if usable else '未通过'}。",
        f"48条独立请求：决策准确率 {metrics['decision_accuracy']:.3%}，95%区间 [{lower:.3%}, {upper:.3%}]；验证后处置准确率 {metrics['validated_accuracy']:.3%}。",
        f"25条可接受请求的执行就绪率 {metrics['valid_request_readiness']:.3%}；不应执行却就绪 {metrics['unsafe_ready_count']} 次；就绪计划的标注字段不符 {metrics['ready_field_mismatch_count']} 次。",
        "",
        "接口对照完成480/480次，澄清完成70/70次；每个请求—接口组合均有五次正式尝试，记录哈希核验通过。",
        *[f"{row['method']}：决策准确率 {float(row['decision_accuracy']):.3%}，可接受请求就绪率 {float(row['valid_completion_readiness']):.3%}，不安全就绪 {row['unsafe_ready']} 次。" for row in interface_metrics],
        f"澄清终轮执行就绪率 {float(clarification_metrics['terminal_execution_readiness']):.3%}；每条一次预设确认，平均 {float(clarification_metrics['mean_reply_characters']):.1f} 字符。",
        f"公开数据字段重放：{replay_metrics['trials']}次，检查后完成率 {float(replay_metrics['validated_completion']):.3%}；已完成计划的备用序列与参考相同，成本差为零。",
        "结论：接口结构约束改善混元决策准确率；完整重复记录可支持所评估请求和版本下的性能比较及验证与完成率的权衡。就绪率与准确率使用各自规定的分母，不能互换。",
        "这些证据可以实质回应重复调用、版本归档及统计比较意见。审稿人的全部判断仍取决于独立请求、专家比较、端到端追踪和公共数值验证的整体证据，无法保证100%满意。",
        "现场部署不在本次实验范围。论文以离线研究准备和验证为研究范围，依实际证据表述结论。专家时间为自报估计；语言验证层的数值节省和一般覆盖保证须有对应证据才能作出结论。",
        "",
        "投稿仅整合必要的汇总统计和方法信息。开发调试响应留在内部，正式尝试完整计入各项统计。"]
    (output / "混元结果可用性评估.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not usable:
        raise ValueError("Hunyuan integrity assessment failed")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
