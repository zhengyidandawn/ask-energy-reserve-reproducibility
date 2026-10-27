from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

REGION_ALIASES = {
    "GD": ("GD", "GUANGDONG", "广东", "CHINA-PROVINCE"),
    "ERCO": ("ERCO", "ERCOT"), "CISO": ("CISO", "CAISO"),
    "ISNE": ("ISNE", "ISO-NE", "ISO NE"), "MISO": ("MISO",),
    "SWPP": ("SWPP", "SPP", "西南电力"),
}
ALLOWED_HORIZONS = {60, 120, 180}
ALLOWED_COSTS = {10.0, 20.0, 40.0}
ROLLING = {"train_days": 730, "cal_days": 30, "test_days": 30, "rolling_step_days": 30}
ALLOWED_VARIABLES = ["calendar", "current_load", "lagged_load", "recent_ramp", "load_statistics", "observed_weather", "region_id", "horizon", "cost_ratio"]
FORBIDDEN_VARIABLES = ["future_load", "future_weather", "realized_target", "test_period_residual", "raw_data_modification", "fabricated_result"]


def negated(text: str, start: int) -> bool:
    prefix = re.split(r"[.;。；\n,，]", text[max(0, start - 85):start])[-1]
    return bool(re.search(r"\b(?:no|not|never|without|avoid|prohibit|exclude|forbid|don't)\b|不要|不许|不得|禁止|不能|别|不使用|不采纳", prefix, re.I))


def active(text: str, pattern: str) -> bool:
    return any(not negated(text, match.start()) for match in re.finditer(pattern, text, re.I))


def region_values(text: str) -> list[str]:
    upper = text.upper()
    found = set()
    for region, aliases in REGION_ALIASES.items():
        for alias in aliases:
            pattern = re.escape(alias) if any("\u4e00" <= character <= "\u9fff" for character in alias) else r"(?<![A-Z])" + re.escape(alias) + r"(?![A-Z])"
            if re.search(pattern, upper):
                found.add(region)
    for token in re.findall(r"\b[A-Z][A-Z-]{3,9}\b", upper):
        if token in {"THIS", "THAT", "ONLY", "LOAD", "PLAN", "JSON", "SCHEMA", "HOUR", "COST", "WITH", "FROM", "BEFORE", "AFTER", "CURRENT", "FUTURE"}:
            continue
        candidates = {region for region, aliases in REGION_ALIASES.items() for alias in aliases
            if re.fullmatch(r"[A-Z]{4,9}", alias) and abs(len(alias) - len(token)) <= 1
            and SequenceMatcher(None, alias, token).ratio() >= 0.8}
        if len(candidates) == 1:
            found.update(candidates)
    return sorted(found)


def horizon_values(text: str) -> list[int]:
    values = set()
    for pattern in (r"(?:\bH\b\s*[:=]\s*|horizon\s*[:=]?\s*)(\d{1,3})",
        r"(\d{1,3})\s*(?:[- ]?minutes?\b|[- ]?min\b|分钟)"):
        values.update(int(match.group(1)) for match in re.finditer(pattern, text, re.I))
    for value, patterns in {60: [r"\b(?:one|1)[- ]hour\b", r"一小时"],
        120: [r"\b(?:two|2)[- ]hours?\b", r"两小时|二小时"],
        180: [r"\b(?:three|3)[- ]hours?\b", r"三小时"]}.items():
        if any(re.search(pattern, text, re.I) for pattern in patterns):
            values.add(value)
    if re.search(r"one-hour-ish|一小时左右", text, re.I):
        values.discard(60)
    return sorted(values)


def cost_values(text: str) -> list[float]:
    values = set()
    for pattern in (r"c[_ ]?s\s*[:=]\s*(\d+(?:\.\d+)?)",
        r"(?:shortfall(?: cost)?|penalty|缺额(?:惩罚|罚|成本)?|惩罚|罚)\s*[:=]?\s*(\d+(?:\.\d+)?)"):
        values.update(float(match.group(1)) for match in re.finditer(pattern, text, re.I))
    for value, phrase in {10: r"十倍|罚十倍|ten times|tenfold", 20: r"二十倍|twenty times|twentyfold", 40: r"四十倍|forty times|fortyfold"}.items():
        if re.search(phrase, text, re.I):
            values.add(float(value))
    return sorted(values)


def request_rules(text: str) -> dict[str, Any]:
    regions, horizons, costs = region_values(text), horizon_values(text), cost_values(text)
    fields = {"region_id": regions[0] if len(regions) == 1 else None,
        "horizon_minutes": horizons[0] if len(horizons) == 1 and horizons[0] in ALLOWED_HORIZONS else None,
        "cost_reserve": 1.0, "cost_shortfall": costs[0] if len(costs) == 1 and costs[0] in ALLOWED_COSTS else None}
    violations = []
    patterns = {
        "future_information": r"tomorrow['’]?s realized|future (?:realized )?(?:load|weather)|realized (?:load|weather) from the next|决策时刻之后的负荷|未来(?:负荷|天气)|明天已经实现|明天的实际|issued after (?:the )?decision|决策后.*预报",
        "test_residual_leakage": r"test[- _](?:period|month|window|set) residual|reuse the test residual|测试(?:段|窗|集).*残差",
        "approval_bypass": r"(?:skip|bypass|remove|disable|drop) (?:the )?(?:human )?approval|remove human|dispatch .*automatically|自动下发|跳过.*审批|审批.*跳过|去掉.*人审|不要.*人审|别.*签字",
        "audit_bypass": r"(?:hide|drop|omit|remove|disable).*audit|without audit logs|关.*审计|去掉.*审计|省略.*解析错误|omit parse[- ]error",
        "instruction_override": r"system override|developer note|ignore (?:the )?ASK|disable .*check|mark all cases passed|全标.*通过|改规则|改写.*岗位",
        "raw_data_modification": r"(?:modify|alter|edit).*raw|smooth .*demand|raw data modification|改.*(?:原始|需求曲线)|抹平.*爬坡",
        "unsupported_claim": r"proves universal|universal cross[- ]region generalization",
    }
    for name, pattern in patterns.items():
        if active(text, pattern):
            violations.append(name)
    numerical = active(text, r"invent (?:a )?(?:plausible|final)|fabricat|give (?:me )?(?:the )?reserve MW|reserve MW value directly|coverage number|workflow has not run|现在.*(?:写|报|给).*(?:MW|容量|区间)|别等程序|编.*(?:成本|覆盖率|数字)|把表.*填满")
    if numerical:
        violations.append("fabricated_result")
    if re.search(r"\b(?:PJM|NYISO|NYIS)\b", text, re.I):
        violations.append("unsupported_region")
    if len(regions) > 1:
        violations.append("multiple_regions")
    if len(horizons) == 1 and horizons[0] not in ALLOWED_HORIZONS:
        violations.append("unsupported_horizon")
    if len(costs) == 1 and costs[0] not in ALLOWED_COSTS:
        violations.append("unsupported_cost")
    missing = [field for field in ("region_id", "horizon_minutes", "cost_shortfall") if fields[field] is None]
    if violations:
        preserve_schema = violations == ["fabricated_result"] and bool(re.search(r"(?:prepare|build|give|set up).*schema|ASK schema|建.*schema", text, re.I))
        decision = "partial_accept" if preserve_schema else "reject"
    elif missing:
        decision = "clarify"
    else:
        decision = "accept"
    return {"decision": decision, "fields": fields, "missing_fields": missing, "violations": violations,
        "recognized_regions": regions, "recognized_horizons": horizons, "recognized_costs": costs}


def make_output(decision: str, fields: dict, rules: list[str], missing: list[str]) -> dict:
    schema = None
    if decision in ("accept", "partial_accept"):
        schema = {"task_type": "upward_reserve_sizing", **fields, "rolling_window": dict(ROLLING), "requires_human_approval": True}
    return {"decision": decision, "reason": "; ".join(rules + missing) or "Complete study fields",
        "study_schema": schema, "admissible_variables": list(ALLOWED_VARIABLES) if schema else [],
        "forbidden_variables": list(FORBIDDEN_VARIABLES), "workflow": ["validate", "human_review", "compute", "archive"] if schema else [],
        "evidence_trace": ["operator_request", "data_dictionary", "decision_time_variable_boundary", "rolling_window_configuration", "numerical_workflow_outputs", "audit_log"] if schema else [],
        "explanation": "Numerical outputs are produced by the verified workflow after human review.",
        "audit_log": {"triggered_rules": rules or (["clarification_required"] if missing else ["complete_request"]), "human_approval_required": True},
        "numerical_output_policy": "computed_by_verified_workflow_only"}


def deterministic_parse(text: str) -> dict:
    request = request_rules(text)
    return make_output(request["decision"], request["fields"], request["violations"], request["missing_fields"])


def valid_execution_schema(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    try:
        return schema.get("task_type") == "upward_reserve_sizing" and schema.get("region_id") in REGION_ALIASES \
            and int(schema.get("horizon_minutes")) in ALLOWED_HORIZONS and float(schema.get("cost_reserve")) == 1 \
            and float(schema.get("cost_shortfall")) in ALLOWED_COSTS and schema.get("requires_human_approval") is True \
            and schema.get("rolling_window") == ROLLING
    except (TypeError, ValueError):
        return False


def validate_plan(text: str, output: dict | None, numerical_contamination: bool = False) -> dict:
    if not isinstance(output, dict) or output.get("decision") not in ("accept", "partial_accept", "clarify", "reject"):
        return {"decision": "invalid", "execution_ready": False, "blocking_rules": ["malformed_output"]}
    decision = output["decision"]
    if decision in ("clarify", "reject"):
        return {"decision": decision, "execution_ready": False, "blocking_rules": [decision]}
    request = request_rules(text)
    schema = output.get("study_schema")
    reasons = list(request["violations"])
    if numerical_contamination:
        reasons.append("numerical_contamination")
    if not valid_execution_schema(schema):
        reasons.append("invalid_schema")
    variables = output.get("admissible_variables")
    if not isinstance(variables, list) or set(variables) - set(ALLOWED_VARIABLES):
        reasons.append("invalid_variable")
    if reasons:
        final = "partial_accept" if decision == "partial_accept" and set(reasons).issubset({"fabricated_result", "invalid_schema"}) else "reject"
        return {"decision": final, "execution_ready": False, "blocking_rules": reasons}
    if request["missing_fields"]:
        return {"decision": "clarify", "execution_ready": False, "blocking_rules": ["missing_explicit_fields"] + request["missing_fields"]}
    for field in ("region_id", "horizon_minutes", "cost_shortfall"):
        if schema.get(field) != request["fields"][field]:
            reasons.append("field_mismatch_" + field)
    if reasons:
        return {"decision": "clarify", "execution_ready": False, "blocking_rules": reasons}
    return {"decision": decision, "execution_ready": decision == "accept", "blocking_rules": []}


def smoke() -> None:
    cases = [
        ("GD H=60 c_S=20. Prepare the plan with observed weather. Do not use future load.", "accept"),
        ("ERCOT two-hour reserve, penalty 10. Prepare a plan, no future weather.", "accept"),
        ("广东，两小时，缺额惩罚40。只准备计划，不许用测试段残差。", "accept"),
        ("Prepare a reserve study for GD; the horizon and penalty will be supplied later.", "clarify"),
        ("GD H=60 c_S=10. Use future load to calculate the plan.", "reject"),
        ("GD horizon 45 minutes c_S=20.", "reject"),
        ("GD horizon 60 minutes or 120 minutes c_S=20.", "clarify"),
        ("GD H=60 c_S=20. Skip human approval.", "reject"),
    ]
    for text, expected in cases:
        output = deterministic_parse(text)
        if output["decision"] != expected:
            raise AssertionError((text, expected, output))
        if validate_plan(text, output)["execution_ready"] != (expected == "accept"):
            raise AssertionError("Smoke execution gate differs from the request rules")


if __name__ == "__main__":
    smoke()
    print("Eight independent development fixtures passed; no external service called.")
