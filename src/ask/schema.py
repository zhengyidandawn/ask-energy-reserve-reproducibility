from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Public four-region scope only. The private-region identifier is deliberately
# absent from this release.
ALLOWED_REGIONS = {"ERCO", "CISO", "ISNE", "MISO"}
PUBLIC_REGIONS = set(ALLOWED_REGIONS)
ALLOWED_HORIZONS = {60, 120, 180}
ALLOWED_COST_SHORTFALLS = {10.0, 20.0, 40.0}
COST_RESERVE = 1.0

REQUIRED_TOP_LEVEL_FIELDS = {"decision", "reason", "study_schema", "admissible_variables", "forbidden_variables", "workflow", "evidence_trace", "explanation", "audit_log", "numerical_output_policy"}
REQUIRED_SCHEMA_FIELDS = {"task_type", "region_id", "horizon_minutes", "cost_reserve", "cost_shortfall", "rolling_window", "requires_human_approval"}
REQUIRED_ROLLING_FIELDS = {"train_days", "cal_days", "test_days", "rolling_step_days"}
VALID_DECISIONS = {"accept", "reject", "clarify", "partial_accept"}

ADMISSIBLE_VARIABLES = {"calendar", "current_load", "lagged_load", "recent_ramp", "load_statistics", "observed_weather", "region_id", "horizon", "cost_ratio"}
FORBIDDEN_VARIABLES = {"future_load", "future_weather", "realized_target", "test_period_residual", "raw_data_modification", "fabricated_result"}
NUMERICAL_OUTPUT_BLACKLIST_KEYS = {"reserve_value", "reserve_values", "mean_cost", "cost_claim", "coverage", "confidence_interval", "ci", "shortfall_cvar", "reported_result", "computed_result", "computed_cost", "bootstrap_interval"}


@dataclass(frozen=True)
class CaseLabel:
    case_id: str
    case_group: str
    turn_id: str
    conversation_id: str
    user_request: str
    expected_decision: str
    expected_rejection_reason: str
    required_schema_fields: list[str]
    prohibited_outputs: list[str]
    expected_human_gate: bool
    expected_clarification: str
    expected_partial_acceptance: bool
    risk_type: str
    annotator_1_label: str
    annotator_2_label: str
    final_label: str
    notes: str


def bool_from_text(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
