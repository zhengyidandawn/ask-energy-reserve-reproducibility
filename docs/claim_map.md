# Claim-to-artifact map

| Paper claim | Public artifact | Minimal code |
|---|---|---|
| Four-service blind joint success is 0.705–0.885 on 200 requests | `results/llm/blind_summary.csv` | `src/ask/checker.py`, `scripts/run_checker.py` |
| Unresolved-default checking reduces unsafe execution from 0.205 to 0.000 | `results/holdout/paired_governance_tests.csv` | frozen result check in `scripts/check_frozen_claims.py` |
| Four public U.S. regions support the cross-region reserve comparison | `results/public_four_region/*.csv` | `src/minimal_validation.py`, `scripts/run_public_validation.py` |
| Scrambling the selected residual state is a counterfactual stress test | `results/public_four_region/counterfactual_results.csv` | `src/minimal_validation.py` |

The paper's private-region primary 15-minute rerun, private raw data, and
optional neural/resource-allocation branches are intentionally out of scope.
