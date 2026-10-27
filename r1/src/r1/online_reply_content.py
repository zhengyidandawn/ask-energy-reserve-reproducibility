from __future__ import annotations

import csv
import json

from workspace_paths import PROJECT


def read_rows(filename):
    with (PROJECT / "results/online_draft_audit_20261011" / filename).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def revise_online_pairs(pairs):
    services = ("deepseek", "qwen", "ernie", "hunyuan")
    terminal = {row["service"]: row for row in read_rows("stage_summary.csv") if row["stage"] == "terminal"}
    calls = json.loads((PROJECT / "results/online_draft_audit_20261011/call_summary.json").read_text(encoding="utf-8"))
    feedback_count = calls["online_calls"] - 480
    fields_cn = "、".join(terminal[service]["field_correct"] + "/200" for service in services)
    fields_en = ", ".join(terminal[service]["field_correct"] + "/200" for service in services)
    decisions_cn = "、".join(terminal[service]["validated_correct"] + "/120" for service in services)
    decisions_en = ", ".join(terminal[service]["validated_correct"] + "/120" for service in services)
    reusable_cn = "、".join(terminal[service]["retained_entries"] + "/265" for service in services)
    reusable_en = ", ".join(terminal[service]["retained_entries"] + "/265" for service in services)
    seconds_cn = "、".join(f"{float(terminal[service]['median_service_seconds']):.2f}" for service in services)
    seconds_en = ", ".join(f"{float(terminal[service]['median_service_seconds']):.2f}" for service in services)
    replacements_cn = "、".join(terminal[service]["required_replacements"] for service in services)
    replacements_en = ", ".join(terminal[service]["required_replacements"] for service in services)
    intervals_cn = "；".join(f"{100*float(terminal[service]['retained_fraction']):.1f}%（95%区间{100*float(terminal[service]['retained_ci_low']):.1f}%—{100*float(terminal[service]['retained_ci_high']):.1f}%）" for service in services)
    intervals_en = "; ".join(f"{100*float(terminal[service]['retained_fraction']):.1f}% (95% interval {100*float(terminal[service]['retained_ci_low']):.1f}% to {100*float(terminal[service]['retained_ci_high']):.1f}%)" for service in services)
    chinese, english = pairs["R2-1"]
    pairs["R2-1"] = (
        chinese + "进一步对相同48条请求计算接口相对解析器的配对区间：混元函数调用的原始处置差值为+0.133，95%区间为[0.000,0.267]，Holm校正p值0.679；校验后差值+0.033，区间[-0.075,0.142]。补充材料完整报告十种接口的两个指标。对24条专家请求另采用保留全部已给定字段的共同草稿任务，四服务各五次，共480个初始试次及" + str(feedback_count) + "次固定检查反馈。终轮字段正确数依DeepSeek、千问、ERNIE、混元顺序为" + fields_cn + "，最少输入替换为" + replacements_cn + "项。解析器采用相同字段保留任务，专家、解析器和服务的共同对照表同时报告参考一致性和资源。这些结果把自然语言准备的具体内容、字段复用和固定验证分别纳入评价。",
        english + " We also compute paired intervals against the parser on the same 48 requests. Hunyuan function calling has an original-disposition difference of +0.133, with a 95% interval [0.000, 0.267] and Holm-adjusted p=0.679; its validated difference is +0.033, with an interval [-0.075, 0.142]. The supplement reports both endpoints for all ten interfaces. A separate common draft task preserves every supplied field on the 24 expert requests. Five trials per service give 480 initial trials and " + str(feedback_count) + " frozen-checker feedback calls. Final field counts are " + fields_en + " for DeepSeek, Qwen, ERNIE, and Hunyuan, with " + replacements_en + " minimum input replacements. The parser receives the same field-preserving task, and the common expert, parser, and service tables report reference agreement and resources. These results evaluate the content of natural-language preparation, field reuse, and fixed validation separately."
    )
    pairs["R3-5"] = (
        "我们讨论后采纳您的专家对照建议，并将同任务质量、可复用输入与完整准备时间条件共同纳入评价。三位专家为相同24条请求准备72份计划，处置正确数72/72；字段准确率分别为1.000、1.000和0.825，自估平均准备时间为2.93—3.25分钟。原服务响应在共同校验后的处置正确数依DeepSeek、千问、ERNIE、混元顺序为120/120、109/120、102/120和74/120；四条有效接受请求各贡献五次试次，有效就绪数为20/20、20/20、20/20和17/20。原草稿在265项可变输入中的复用比例为73.6%、63.8%、56.2%和47.2%，补充材料按21个不同文本给出聚类区间与四类任务分层。另设保留所有已给定字段的在线草稿协议，采用同24条请求和相同参考，四服务各五次；固定检查反馈至多一次，只读取原请求与冻结规则。480个初始试次及" + str(feedback_count) + "次反馈形成终轮字段正确数" + fields_cn + "、校验后处置正确数" + decisions_cn + "、可复用输入" + reusable_cn + "；最少替换为" + replacements_cn + "项，复用比例及区间为" + intervals_cn + "。包含反馈的实测服务时间中位数为" + seconds_cn + "秒。时间分析在每份计划中加入逐项核查、替换修正及阅读与审批等整体工作，按每项核查10—60秒、每项修正5—30秒和整体工作0—60秒形成180种条件，并报告全网格范围。专家自估时间、服务实测延迟和条件推算分别标明。Noy与Zhang的453人写作实验及Vaccaro等106项研究、370个效应量，为按任务评价协作提供方法依据。这些对照给出已有专家计划、实际在线草稿、输入替换和完整条件时间的具体证据，每份草稿均保留人工核查与授权要求。",
        "We discussed and adopted your recommendation for an expert benchmark, evaluating matched-task quality, reusable inputs, and the conditions for total preparation time together. Three experts prepare 72 plans for the same 24 requests, with 72/72 correct dispositions. Their field accuracies are 1.000, 1.000, and 0.825, and mean self-estimated preparation time is 2.93 to 3.25 minutes. In the original service replay, validated dispositions are correct in 120/120, 109/120, 102/120, and 74/120 trials for DeepSeek, Qwen, ERNIE, and Hunyuan. The four valid accept requests each contribute five trials per service, with readiness counts of 20/20, 20/20, 20/20, and 17/20. Original drafts reuse 73.6%, 63.8%, 56.2%, and 47.2% of 265 variable inputs; the supplement gives intervals clustered by 21 distinct texts and results for four task classes. A separate online draft protocol preserves every supplied field on the same 24 requests and reference, with five trials per service. At most one frozen-checker feedback call uses the original request and fixed rules. The 480 initial trials and " + str(feedback_count) + " feedback calls give final field counts of " + fields_en + ", validated dispositions of " + decisions_en + ", and reusable inputs of " + reusable_en + ". Minimum replacements are " + replacements_en + ", with reuse proportions and intervals of " + intervals_en + ". Measured median total service times, including feedback, are " + seconds_en + " seconds. Time analysis adds entry review, replacement correction, and other work such as reading and authorization. Review of 10 to 60 seconds per entry, correction of 5 to 30 seconds per replacement, and other work of 0 to 60 seconds give 180 conditions, with full-grid ranges reported. Expert self-estimates, measured service latency, and conditional calculations are identified separately. Noy and Zhang's 453-person writing experiment and Vaccaro et al.'s synthesis of 106 studies and 370 effects provide methodological support for task-specific collaboration evaluation. These comparisons supply concrete evidence from existing expert plans, actual online drafts, input replacements, and conditional total time. Every draft retains human verification and authorization."
    )
    for key in ("R2-3", "R3-2", "R3-3"):
        chinese, english = pairs[key]
        pairs[key] = (chinese + "完整字段草稿协议另有480条初始响应与" + str(feedback_count) + "条固定检查反馈响应，按单独协议归档其提示、参数、模型、日期、token、延迟、费用及初末结果。",
                      english + " The complete-draft protocol separately archives 480 initial responses and " + str(feedback_count) + " frozen-checker feedback responses, with prompts, parameters, models, dates, tokens, latency, fees, and initial and final outcomes.")
    chinese, english = pairs["R2-5"]
    pairs["R2-5"] = (chinese + "完整字段草稿对照进一步解释输入复用的机制：在澄清和拒绝时保留已给定字段，把需要确认的内容和已有内容共同交给人工核查；四服务终轮字段正确数为" + fields_cn + "，对应最少输入替换" + replacements_cn + "项。",
                      english + " The complete-draft comparison further explains input reuse: supplied fields remain available during clarification and rejection, so human review receives both known content and fields requiring confirmation. Final field counts are " + fields_en + ", corresponding to " + replacements_en + " minimum input replacements.")
    return pairs
