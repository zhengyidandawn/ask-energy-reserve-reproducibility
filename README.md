# ASK energy-reserve reproducibility package

This is the minimal public code-and-results package for the paper
“A decision-time validation framework for LLM-assisted energy studies:
One-hour upward-reserve sizing”. It supports the claims that require an
independent reader to inspect or rerun the public workflow:

1. fixed request checks and the four-service, 200-request blind summary;
2. one-hour upward-reserve evaluation with the paper's 730/30/30 rolling
   design on four public U.S. balancing areas (`ERCO`, `CISO`, `ISNE`, `MISO`);
3. state-dependent conformal calibration and the selected-state scrambling
   counterfactual.

The frozen CSV results under `results/` are copied from the article-stage
experiments and are filtered to the public four-region scope. No Chinese
province raw data, hourly records, private testbed input, or private-region
result rows are included. The public workflow downloads only official EIA
balancing-authority demand and NOAA hourly weather data.

## Quick verification

From PowerShell:

```powershell
python .\scripts\check_frozen_claims.py
python .\scripts\verify_public_scope.py
```

The first command checks the frozen blind-test and public-region summaries.
The second command scans the distributed data/results paths for private-region
material.

## Re-run the public four-region calculation

Install the small dependency set:

```powershell
python -m pip install -r .\requirements.txt
```

Download the public inputs and build the hourly feature files:

```powershell
python .\scripts\download_public_data.py
python .\scripts\prepare_public_data.py
```

Then run the minimal rolling validation. A one-window smoke test is:

```powershell
python .\scripts\run_public_validation.py --max-windows 1
```

The full run is:

```powershell
python .\scripts\run_public_validation.py
```

The full run writes generated tables under `results/generated/`; it does not
overwrite the frozen article-stage tables. The implementation keeps the
paper's decision-time boundary, one-hour target, asymmetric cost
(`c_R=1`, `c_S=20`), 0.95 service level, and 730/30/30 rolling split. It
omits private-region reruns and optional neural/resource-allocation branches.

## Re-run the deterministic request checker

The blind labels are included in `data/llm/case_labels_blind.csv`. Provider
responses are intentionally not bundled: they require the original provider
access and can contain prompt/output material beyond the minimum claim set.
If a saved JSONL response file is available, run:

```powershell
python .\scripts\run_checker.py --service deepseek --outputs C:\path\to\model_outputs.jsonl
```

The checker never calls an API and writes case-level results beside the input
file.

## Frozen claim artifacts

- `results/llm/blind_summary.csv`: four LLM services, 200 blind requests.
- `results/holdout/mode_summary.csv`: 200-request paired governance replay.
- `results/holdout/paired_governance_tests.csv`: the exact McNemar comparison.
- `results/public_four_region/region_summary.csv`: four-region method ranking.
- `results/public_four_region/validation_results.csv`: aggregate metrics.
- `results/public_four_region/rolling_window_metrics.csv`: window-level metrics.
- `results/public_four_region/counterfactual_results.csv`: selected-state
  scrambling output.

## Public data provenance

- EIA balancing-authority demand bulk data: `https://www.eia.gov/opendata/bulk/EBA.zip`
- NOAA Global Hourly station data: `https://www.ncei.noaa.gov/data/global-hourly/`

The station-to-region mapping and time span are recorded in
`src/public_config.py`. Raw downloads are ignored by Git and remain local.

## License and citation

See `LICENSE`. Cite the associated paper and this repository when reusing the
code or frozen result artifacts.
