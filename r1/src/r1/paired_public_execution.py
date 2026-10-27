from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import lightgbm as lgb

from deterministic_interfaces import validate_plan
from integrate_r1_evidence import load_records
from prepare_human_evidence import read_csv, write_csv, write_json
from public_reserve_validation import metrics
from run_paired_services import PROJECT

DATA = PROJECT / "data" / "paired_public_execution"
RESULTS = PROJECT / "results" / "paired_public_execution"


def prepare_source() -> pd.DataFrame:
    sources, rows = [], []
    for path in sorted((PROJECT / "data" / "public_validation_r1" / "eia").glob("page_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        page = payload["response"]["data"]
        if any(row["value-units"] != "megawatthours" or row["type"] != "D" for row in page):
            raise ValueError("Unexpected official EIA field or unit")
        rows.extend(page)
        sources.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": len(page)})
    source = pd.DataFrame(rows)
    source["ts"] = pd.to_datetime(source["period"], utc=True)
    source["load"] = pd.to_numeric(source["value"], errors="coerce")
    source.loc[source["load"] <= 0, "load"] = np.nan
    source = source.sort_values(["respondent", "ts"]).drop_duplicates(["respondent", "ts"], keep="last")
    DATA.mkdir(parents=True, exist_ok=True)
    source[["ts", "respondent", "load"]].to_csv(DATA / "official_hourly_load.csv", index=False)
    write_json(DATA / "source_manifest.json", {"source": "EIA v2 electricity/rto/region-data/data", "type": "actual demand",
        "source_units": "MWh in one-hour intervals", "derived_units": "hourly average MW",
        "start": str(source["ts"].min()), "end": str(source["ts"].max()), "n_rows": len(source), "pages": sources})
    return source


def evaluate(source: pd.DataFrame, region: str, horizon: int, penalty: int,
             feature_mode: str = "full", required: float = 0.95) -> tuple[dict, dict]:
    frame = source[source["respondent"] == region][["ts", "load"]].set_index("ts")
    grid = pd.date_range(frame.index.min(), frame.index.max(), freq="1h", tz="UTC")
    frame = frame.reindex(grid).rename_axis("ts").reset_index()
    features = ["load", "lag1", "lag24", "recent_mean", "recent_std", "ramp", "hour_sin", "hour_cos"]
    frame["lag1"], frame["lag24"] = frame["load"].shift(1), frame["load"].shift(24)
    frame["recent_mean"] = frame["load"].rolling(6, min_periods=6).mean()
    frame["recent_std"] = frame["load"].rolling(6, min_periods=6).std()
    frame["ramp"] = frame["load"].diff().clip(lower=0)
    frame["hour_sin"] = np.sin(2*np.pi*frame["ts"].dt.hour/24)
    frame["hour_cos"] = np.cos(2*np.pi*frame["ts"].dt.hour/24)
    if feature_mode == "history_calendar":
        features = ["load", "lag1", "lag24", "hour_sin", "hour_cos"]
    elif feature_mode != "full":
        raise ValueError("Unknown supported feature set")
    steps = horizon // 60
    increments = pd.concat([frame["load"].diff().shift(-offset) for offset in range(1,steps+1)], axis=1)
    frame["target"] = increments.clip(lower=0).max(axis=1)
    frame.loc[increments.isna().any(axis=1),"target"] = np.nan
    frame["target_end"] = frame["ts"] + pd.Timedelta(hours=steps)
    end = frame["ts"].max().floor("D") - pd.Timedelta(days=1)
    test_start, selection_start, cal_start = end-pd.Timedelta(days=30), end-pd.Timedelta(days=40), end-pd.Timedelta(days=60)
    frame = frame.dropna(subset=features+["target"])
    train = frame[(frame["ts"] >= cal_start-pd.Timedelta(days=180)) & (frame["target_end"] < cal_start)]
    calibration = frame[(frame["ts"] >= cal_start) & (frame["target_end"] < selection_start)]
    selection = frame[(frame["ts"] >= selection_start) & (frame["target_end"] < test_start)]
    test = frame[(frame["ts"] >= test_start) & (frame["target_end"] < end)]
    if min(len(train),len(calibration),len(selection),len(test)) < 100:
        raise ValueError("Incomplete official-data temporal block")
    assert train["target_end"].max() < calibration["ts"].min()
    assert calibration["target_end"].max() < selection["ts"].min()
    assert selection["target_end"].max() < test["ts"].min()
    probability = 1-1/penalty
    model=lgb.LGBMRegressor(objective="quantile",alpha=probability,n_estimators=120,num_leaves=31,
        learning_rate=0.04,min_child_samples=40,random_state=20261010,n_jobs=2,verbosity=-1)
    model.fit(train[features],train["target"])
    offset=np.quantile(calibration["target"]-model.predict(calibration[features]),probability,method="higher")
    selection_reserve=model.predict(selection[features])+offset
    correction=max(0,float(np.quantile(selection["target"]-selection_reserve,required,method="higher")))
    reserve=np.maximum(model.predict(test[features])+offset+correction,0)
    target=test["target"].to_numpy()
    scale=float(calibration["load"].mean())
    result={"region":region,"horizon_minutes":horizon,"cost_shortfall":penalty,
        "feature_mode":feature_mode,"required_coverage":required,
        "test_start":str(test["ts"].min()),"test_end":str(test["ts"].max()),
        "selection_coverage":float(np.mean(selection["target"] <= np.maximum(selection_reserve+correction,0))),
        **metrics(target,reserve,scale,penalty),
        "target_sha256":hashlib.sha256(target.tobytes()).hexdigest(),"reserve_sha256":hashlib.sha256(reserve.tobytes()).hexdigest()}
    return result,{"target":target,"reserve":reserve,"load_scale":scale,"timestamps":test["ts"].to_numpy(dtype="datetime64[ns]")}


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--services",nargs="+",default=["deepseek","qwen","ernie"])
    args=parser.parse_args()
    source=prepare_source()
    protocol=DATA/"execution_protocol.json"
    if not protocol.exists():
        write_json(protocol,{"frozen_at":datetime.now(timezone.utc).isoformat(),"training_days":180,"calibration_days":20,
            "selection_days":10,"test_days":30,"common_selection_coverage":0.95,
            "target":"maximum future positive hourly increment","comparison":"paired actual service plans and independently labelled reference plans",
            "wrong_plan_cost":"same-timestamp difference in reserve/shortfall loss under reference objective","all_scheduled_service_trials_retained":True})
    if args.smoke:
        row,_=evaluate(source,"ERCO",60,20)
        assert row["selection_coverage"] >= .95 and np.isfinite(row["normalized_cost"])
        write_json(RESULTS/"smoke.json",{"passed":True,"purging_passed":True,"physical_unit":"MW","result":row})
        print(json.dumps({"smoke_passed":True,"coverage":row["coverage"],"n":row["n"]}))
        return
    if not (RESULTS/"smoke.json").exists():
        raise ValueError("Execution experiment requires a successful smoke")
    labels={row["case_id"]:row for row in read_csv(PROJECT/"data"/"human_r1"/"evaluation_labels.csv") if row["packet"]=="independently_authored_48"}
    cache={}
    def lookup(region,horizon,penalty):
        key=(region,horizon,penalty)
        if key not in cache:
            cache[key]=evaluate(source,*key)
        return cache[key]
    records=[row for row in load_records("repeated_four_services_v1") if row["service"] in args.services and row["case_id"] in labels]
    paired=[]
    for record in records:
        gold=labels[record["case_id"]]
        gate=validate_plan(gold["user_request"],record.get("parsed_output"),record.get("checks",{}).get("numerical_contamination",False))
        if gold["expected_decision"] != "accept" or gold["gold_region_id"] not in set(source["respondent"]):
            continue
        region=gold["gold_region_id"]
        horizon=int(float(gold["gold_horizon_minutes"]))
        penalty=int(float(gold["gold_cost_shortfall"]))
        reference,reference_arrays=lookup(region,horizon,penalty)
        row={"service":record["service"],"case_id":record["case_id"],"repeat":record["repeat"],"region":region,
            "execution_ready":int(gate["execution_ready"]),"blocked_before_computation":int(not gate["execution_ready"]),
            "reference_cost":reference["normalized_cost"],"validated_cost":"","validated_cost_difference":"",
            "paired_reserve_equal":False,"direct_plan_computed":False,"direct_cost_regret":"","direct_coverage":"",
            "validated_coverage":""}
        output=record.get("parsed_output") or {}
        schema=output.get("study_schema") or {}
        try:
            candidate=(schema["region_id"],int(schema["horizon_minutes"]),int(schema["cost_shortfall"]))
            if output.get("decision") in ("accept","partial_accept") and candidate[0] in set(source["respondent"]) and candidate[1] in (60,120,180) and candidate[2] in (10,20,40):
                direct,direct_arrays=lookup(*candidate)
                common,reference_indices,direct_indices=np.intersect1d(reference_arrays["timestamps"],direct_arrays["timestamps"],return_indices=True)
                target=reference_arrays["target"][reference_indices]
                direct_reserve=direct_arrays["reserve"][direct_indices]
                correct_reserve=reference_arrays["reserve"][reference_indices]
                direct_loss=np.mean(direct_reserve+penalty*np.maximum(target-direct_reserve,0))
                correct_loss=np.mean(correct_reserve+penalty*np.maximum(target-correct_reserve,0))
                row.update({"direct_plan_computed":True,"direct_cost_regret":float((direct_loss-correct_loss)/reference_arrays["load_scale"]),
                    "direct_coverage":float(np.mean(target <= direct_reserve))})
                if gate["execution_ready"]:
                    row.update({"validated_cost":float(direct_loss/reference_arrays["load_scale"]),
                        "validated_cost_difference":float((direct_loss-correct_loss)/reference_arrays["load_scale"]),
                        "validated_coverage":float(np.mean(target <= direct_reserve)),
                        "paired_reserve_equal":bool(np.array_equal(direct_reserve,correct_reserve)
                            and len(common)==len(reference_arrays["timestamps"]))})
        except (KeyError,ValueError,TypeError):
            pass
        if gate["execution_ready"] and not row["direct_plan_computed"]:
            raise ValueError("An execution-ready plan has no valid numerical configuration")
        paired.append(row)
    write_csv(RESULTS/"paired_trials.csv",paired)
    write_csv(RESULTS/"computed_configurations.csv",[value[0] for value in cache.values()])
    summary=[]
    for service in args.services:
        subset=[row for row in paired if row["service"]==service]
        direct=[row for row in subset if row["direct_plan_computed"]]
        ready=[row for row in subset if row["execution_ready"]]
        if subset:
            summary.append({"service":service,"accepted_public_requests":len({row["case_id"] for row in subset}),"trials":len(subset),
                "validated_completion":np.mean([row["execution_ready"] for row in subset]),"blocked":sum(row["blocked_before_computation"] for row in subset),
                "direct_plan_computed":len(direct),"mean_direct_cost_regret":np.mean([row["direct_cost_regret"] for row in direct]) if direct else "",
                "verified_completed_plan_cost_difference":float(np.mean([row["validated_cost_difference"] for row in ready])) if ready else "",
                "verified_reserve_series_equal":all(row["paired_reserve_equal"] for row in ready)})
    write_csv(RESULTS/"summary.csv",summary)
    write_json(RESULTS/"usability.json",{"passed":True,"same_timestamp_loss":True,"blocked_trials_retained":True,"computed_configurations":len(cache)})
    print(json.dumps(summary))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
