AEI R1 reproducibility package

This package contains the source code, public inputs, independently authored request labels,
formal successful service records, scoring outputs, numerical caches, literature metadata,
and result tables used for the revised manuscript.

Suggested checks from this directory:
0. Install the dependencies in requirements.txt in a Python environment.
1. Run: python src/r1/strengthen_r1_evidence.py --smoke
2. Run: python src/r1/strengthen_r1_evidence.py
3. Run: python src/r1/run_bandwidth_sensitivity.py --smoke
4. Run: python src/r1/run_bandwidth_sensitivity.py

Steps 1 and 2 rebuild statistical evidence from archived responses and numerical caches.
They make no hosted-model calls. Steps 3 and 4 refit the public-data bandwidth comparisons.
The dependencies are pinned to the versions used for package validation.
The results/reconstructed_evidence directory retains the independently rebuilt outputs.
The reported result directories preserve the original measured preparation times.
Run python src/r1/analyze_positive_revision.py --smoke before
python src/r1/analyze_positive_revision.py to rebuild the later-window paired
cost intervals, reference-field correction workload, derived review-time budgets,
execution-stage resource accounting, and token-based price sensitivity.
Run python src/r1/build_positive_tables.py to rebuild their manuscript tables.
These commands read archived records and caches and use no hosted-model calls.
The positive_revision_20261011 results preserve measurement and derivation labels.
Run python src/r1/analyze_substantive_resolution.py --smoke before
python src/r1/analyze_substantive_resolution.py to rebuild provider-specific fees,
reference-label input counts, six declaration changes with regression checks,
six-field numerical replays and controlled field-deviation consequences.
Run python src/r1/build_substantive_tables.py to regenerate the related tables.
These commands use archived responses and numerical caches. The separately recorded
six-field extension contains 300 initial and 60 confirmation responses, with all
scheduled content outcomes retained. Its requests are author-designed. The 196
offline numerical outputs preserve the requirement for human authorization.
The 95 injected deviations evaluate controlled validation behavior. Input counts
describe minimum reference corrections; full human workflow time requires its own
measurement. Maintenance counts describe shared declarations and generated artifacts.
The evidence_completion_20261011 directory contains the frozen-margin extension,
the six-station weather diagnostic, and 280 retained initial trials with 421
successful field-limited follow-up responses. These follow-up results are a
separate clarification audit with retained scientific content outcomes.
All 6,680 completed records are retained: 4,960 primary, 1,440 matched-interface,
and 280 terminal clarification records. The manifest links each planned task to its
completed response, including 30 successful recovery records. Content errors remain
in scoring. The request checker and original case-level inputs are included.

The public OPSD and EIA inputs are retained with retrieval manifests and hashes.
Formal response records are limited to successful records used in the reported analyses;
transient transport diagnostics are excluded. Monetary API billing and restricted source
data are outside the package. The manuscript reports token use, measured latency,
the four returned models' provider-specific list-price estimates, and common-tariff
budget sensitivity. Price snapshots, currencies, cache accounting and per-trial
calculations are retained with their hashes.
All result files retain the denominators and hashes used in the tables.

The online audit of complete drafts is a separate frozen protocol on the existing
24-request expert packet. Five repetitions per service retain supplied fields
under all dispositions. At most one feedback call uses frozen parser and checker
diagnostics. All initial and final content outcomes are included in its scores.
Run python src/r1/analyze_online_draft_audit.py to recompute this audit from its
archived responses, expert records and independent labels without online calls.
Run python src/r1/analyze_remaining_review_questions.py --smoke before the same
command without --smoke to rebuild matched parser comparisons, task-specific
input reuse and conditional time sensitivity. Estimated human times and assumed
review/correction times retain their separate measurement meanings.

Manuscript synchronization on 26 October 2026
The revised manuscript distinguishes the public 2019 benchmark, later frozen-margin
comparison, and archived regional study. Numerical results and archived model responses
are unchanged. Updated document builders and the retained reply template are included.
The clean and marked LaTeX sources are supplied separately in the submission directory.

Publication graphics
The scripts src/r1/plot_study_design.py, plot_request_evidence.py, and
plot_public_evidence.py read completed CSV records and prediction caches.
They write PDF, SVG, and PNG assets without fitting models, making service
calls, or resampling intervals. Figure data and source hashes are retained
in results/figure_revision_20261026. Matplotlib 3.10.7 renders the graphics.
