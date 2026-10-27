from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


MARKS = {'main.tex': [('The evaluation combines', 3, None),
              ('Three experts prepare', 3, None),
              ('Nine study-plan traces', 1, None),
              ('Complete drafts preserve', 2, None),
              ('Selected-local mean cost gains over global calibration', 1, None)],
 'sections/02_Problem_Formulation.tex': [('The fixed validation layer applies', 1, '1-1'),
                                         ('The numerical layer reads', 2, None),
                                         ('\\citet{Lim2021TemporalFusion} develop', 2, None),
                                         ('\\citet{Nikseresht2025Hydrogen} study', 3, None),
                                         ('\\citet{Elmachtoub2022Smart} define', 1, '3-9'),
                                         ('\\citet{Bertsimas2020Prescriptive} formulate', 2, None),
                                         ('\\citet{Taylor2003WeatherEnsemble} study', 2, None),
                                         ('We denote the common empirical coverage requirement', 1, None),
                                         ('Cost is the primary criterion after', 1, '1-2'),
                                         ('Each candidate receives a nonnegative residual offset', 2, None),
                                         ('The residual-state procedure adds a controlled sensitivity diagnostic', 2, '3-12'),
                                         ('The input categories of \\citet{Lim2021TemporalFusion}', 1, '2-6'),
                                         ('The decision-error objective of', 3, None),
                                         ('The sensitivity procedure perturbs', 1, None),
                                         ('The work has two focused contributions', 5, None),
                                         ('In the public quarter-hourly comparison', 6, None),
                                         ('Within each numerical protocol', 6, None),
                                         ('For the public-data selection screen', 1, None),
                                         ('The archived regional comparison set contains', 1, None),
                                         ('The public-data comparison evaluates eight policies', 4, None),
                                         ('The archived regional study defines four diagnostic regimes', 5, None),
                                         ('The LLM prepares the study settings', 2, None),
                                         ('The historical replay tests a simulated Boolean approval gate', 1, None),
                                         ('Figure~\\ref{fig:method_flow} traces', 3, None)],
 'sections/03_Data_and_Experimental_Design.tex': [('The German weather diagnostic combines', 2, None),
                                                  ('The historical and repeated evaluations retain', 1, '3-2'),
                                                  ('The repeated protocol uses five independent calls', 2, '3-3'),
                                                  ('Confidence intervals resample exact request-text clusters', 2, None),
                                                  ('The independent annotation study samples', 3, '2-2'),
                                                  ('A coordinator adjudicates', 1, None),
                                                  ('The independent-request comparison adds', 3, None),
                                                  ('The independent-request evaluation separately measures', 2, None),
                                                  ('In the paired dialogue, each saved initial response', 2, None),
                                                  ('A separate written approval study records', 1, None),
                                                  ('A separate online experiment prepares complete drafts', 4, None),
                                                  ('The main reserve evaluation uses public quarter-hourly national load', 5, None),
                                                  ('The public evaluation uses chronological', 5, None),
                                                  ('For the later-window comparison, each country receives', 5, None),
                                                  ('The archived anonymized study uses', 3, None),
                                                  ('Figure~\\ref{fig:state_density} relates', 4, None),
                                                  ('Target magnitudes vary across load--ramp states', 4, None)],
 'sections/04_R1_Results.tex': [('The independent annotation study contains', 2, None),
                                ('On the independently authored requests, 45 of 48', 2, None),
                                ('Nine labels in the 120-request sample', 2, None),
                                ('The independently authored set contains', 2, None),
                                ('Its wording includes operational shorthand', 1, None),
                                ('The five-run historical comparison yields', 3, '2-3'),
                                ('The Supplementary Material reports class-specific confusion matrices', 1, '3-4'),
                                ('Hunyuan decision accuracy is 0.663', 2, '2-1'),
                                ('Its finite-state workflow records', 2, None),
                                ('The paired parser comparison evaluates', 4, None),
                                ('The three experts, identified as EXP-1', 2, '3-5'),
                                ('In the same replay, final dispositions after validation', 3, None),
                                ('We quantify the field corrections identified', 4, None),
                                ('For request $i$, let $E_i$', 4, None),
                                ('The resource comparison also expresses', 3, None),
                                ('The matched input comparison counts', 4, None),
                                ('The 24 requests contain 21 distinct texts', 3, None),
                                ('Six recorded maintenance changes', 4, None),
                                ('The experiment on complete drafts preserves supplied fields', 3, None),
                                ('These reusable proportions are', 2, None),
                                ('Measured median service time includes', 3, None),
                                ('The complete time analysis adds review', 4, None),
                                ('The check returns 41 ambiguous requests', 1, '3-6'),
                                ('The remaining 14 stop at the request stage', 2, None),
                                ('Each initial response receives one prespecified analyst confirmation', 3, None),
                                ('The confirmation burden is one reply', 1, '3-7'),
                                ('Explicit mention of every required field occurs', 2, None),
                                ('The question-driven follow-up audit retains', 4, '2-4'),
                                ('The reviewer uses the request, extracted study settings', 1, None),
                                ('Four decisions authorize execution', 2, '3-15'),
                                ('Figure~\\ref{fig:r1_service_interfaces} separates', 2, None),
                                ('Figure~\\ref{fig:r1_draft_preparation} compares', 2, None),
                                ('Figure~\\ref{fig:r1_clarification} separates', 2, None)],
 'sections/05_R1_Application.tex': [('The public validation uses quarter-hourly national load', 2, None),
                                    ('We evaluate twelve successive 30-day test windows', 2, None),
                                    ('All eight policies use the same chronological data blocks', 2, None),
                                    ('Target end times are purged', 1, None),
                                    ('The cost index divides', 1, None),
                                    ('In the 2019 selection-screened benchmark, selected-local mean test coverage', 3, None),
                                    ('For each country, we estimated a nonnegative reliability margin', 3, '3-11'),
                                    ('Under the frozen-margin protocol, selected-local mean cost gains', 4, None),
                                    ('An auxiliary weather diagnostic uses', 3, '2-9'),
                                    ('Table~\\ref{tab:r1_physical} expresses reserve', 3, '3-13'),
                                    ('The block comparison uses the maximum calibration residual', 2, '2-8'),
                                    ('The Supplementary Material reports these correlations', 2, None),
                                    ('Conditional results in the 2019 selection-screened benchmark reveal', 1, '3-14'),
                                    ('The bandwidth study keeps', 3, None),
                                    ('A separate block-length check on the twelve-window 2019 benchmark', 1, None),
                                    ('The calculation replay transfers region, horizon, and shortfall weight', 3, '3-8'),
                                    ('Nine checked public-data study plans vary', 1, None),
                                    ('A change in region changes the load series', 4, None),
                                    ('Changing the reliability requirement changes', 2, None),
                                    ('Under a common German reference target', 2, '2-7'),
                                    ('Reducing the predictor variables', 3, None),
                                    ("Across the four-service replay's 440 trials, 266 pass validation", 2, None),
                                    ('Completed validated plans reproduce the reference reserve series and have zero paired cost '
                                     'difference',
                                     2,
                                     None),
                                    ('The six-field extension connects actual service responses', 4, None),
                                    ('Each of the nine complete specifications produces', 3, None),
                                    ('We also inject one field deviation', 4, None),
                                    ('The original anonymized load-weather study provides', 2, None),
                                    ('The first 20 of the 30 calibration days supply residuals', 3, None),
                                    ('Among all eight policies, the lowest mean cost', 4, None),
                                    ('Incomplete or conflicting plans remain', 1, None),
                                    ('Figure~\\ref{fig:r1_frozen_policies} compares', 3, None),
                                    ('Figure~\\ref{fig:r1_frozen_gains} shows', 3, None),
                                    ('Figure~\\ref{fig:r1_conditional_bandwidth} places', 3, None),
                                    ('The time profile in Figure~\\ref{fig:r1_public_trajectory} uses', 3, None),
                                    ('Figure~\\ref{fig:r1_field_consequences} connects', 3, None)],
 'sections/06_R1_Discussion.tex': [('Every interface then requires the same check', 4, '2-5'),
                                   ('Function calling can produce an exact schema', 2, None),
                                   ('Returning an incomplete request protects', 1, None),
                                   ('Similar decision-time states supply residual observations', 2, None),
                                   ('All methods use the same selection requirement', 2, None),
                                   ('Request validation establishes the calculation boundary', 2, None),
                                   ('The frozen-margin extension gives a second reliability comparison', 4, None),
                                   ('The matched comparison identifies the work carried', 4, None),
                                   ('The variable-input count gives', 4, None),
                                   ('The experiment on complete drafts evaluates', 3, None),
                                   ('The distributed-weather diagnostic combines', 3, None),
                                   ('The actual-response extension broadens', 4, None),
                                   ('The parser preserves 52 of 53 variable inputs', 1, None),
                                   ('Request interpretation and validation determine', 1, None)],
 'sections/07_R1_Conditions.tex': [('The independently authored requests and scripted confirmations represent', 1, '3-1'),
                                   ('Coverage is the empirical fraction of realized targets covered', 2, '3-10'),
                                   ('The later-window comparison holds', 4, None)],
 'sections/08_R1_Conclusions.tex': [('The independent study includes 168 requests', 2, None),
                                    ('Public quarter-hourly load from four countries', 3, None),
                                    ('The checked-field experiment connects changes', 2, '3-16'),
                                    ('The frozen-margin extension provides', 3, None),
                                    ('The separately frozen protocol for complete drafts includes', 4, None),
                                    ('Across 265 variable entries per service in the original expert-matched replay', 1, None)],
 'sections/01_Introduction.tex': [('A natural-language request allows', 2, None),
                                  ('The study plan records the permitted load history', 3, None),
                                  ('A large language model (LLM) can interpret', 3, None),
                                  ('The contribution is a traceable preparation', 3, None)]}

DELETIONS = [('main.tex', 'The evaluation combines', 'main.tex', 'Joint success ranges from 0.705 to 0.885', 1, '2-3'),
 ('sections/03_Data_and_Experimental_Design.tex',
  'The independent annotation study samples',
  'sections/04_Primary_Results.tex',
  'The independent blind set was created after',
  1,
  '2-2'),
 ('sections/04_R1_Results.tex',
  'The five-run historical comparison yields',
  'sections/04_Primary_Results.tex',
  'Hunyuan has the highest semantic accuracy',
  2,
  '2-3'),
 ('sections/05_R1_Application.tex',
  'All eight policies use the same chronological data blocks',
  'sections/04_Primary_Results.tex',
  'Its mean cost is 87.53 below robust optimization',
  1,
  '3-11'),
 ('sections/06_R1_Discussion.tex',
  'Similar decision-time states supply residual observations',
  'sections/06_Discussion.tex',
  'State-dependent conformal calibration lowers mean cost',
  3,
  '1-2'),
 ('sections/02_Problem_Formulation.tex',
  'The residual-state procedure adds a controlled sensitivity diagnostic',
  'sections/06_Discussion.tex',
  'The counterfactual analysis identifies the source',
  1,
  '3-12'),
 ('sections/08_R1_Conclusions.tex',
  'The checked-field experiment connects changes',
  'sections/08_Conclusions.tex',
  'The contribution joins a decision-time validation layer',
  1,
  '3-16'),
 ('sections/02_Problem_Formulation.tex',
  'Cost is the primary criterion after',
  'sections/02_Problem_Formulation.tex',
  'Cost is the primary criterion because',
  2,
  '1-2'),
 ('sections/02_Problem_Formulation.tex',
  'The sensitivity procedure perturbs',
  'sections/02_Problem_Formulation.tex',
  'This test distinguishes information used by the base forecast',
  1,
  '3-12'),
 ('sections/03_Data_and_Experimental_Design.tex',
  'The historical and repeated evaluations retain',
  'sections/03_Data_and_Experimental_Design.tex',
  'The Supplementary Material records the requested and returned model identifiers so',
  1,
  '3-2'),
 ('sections/03_Data_and_Experimental_Design.tex',
  'The repeated protocol uses five independent calls',
  'sections/03_Data_and_Experimental_Design.tex',
  'All services receive the same request-validation instruction',
  1,
  '3-3'),
 ('sections/03_Data_and_Experimental_Design.tex',
  'The independent-request comparison adds',
  'sections/03_Data_and_Experimental_Design.tex',
  'The third identifies regions, horizons, costs',
  1,
  '2-1'),
 ('sections/03_Data_and_Experimental_Design.tex',
  'The independent-request evaluation separately measures',
  'sections/03_Data_and_Experimental_Design.tex',
  'The added check identifies requests that use terms',
  2,
  '2-4'),
 ('sections/03_Data_and_Experimental_Design.tex',
  'A separate written approval study records',
  'sections/04_Primary_Results.tex',
  'The approval status is recorded as a Boolean value before calculation',
  2,
  '3-15'),
 ('sections/04_R1_Results.tex',
  'The independent annotation study contains',
  'sections/04_Primary_Results.tex',
  'The designed validation set contains 180 cases',
  2,
  '2-2'),
 ('sections/04_R1_Results.tex',
  'The independently authored set contains',
  'sections/03_Data_and_Experimental_Design.tex',
  'The blind set contains 200 cases created after',
  2,
  '3-1'),
 ('sections/04_R1_Results.tex',
  'The Supplementary Material reports class-specific confusion matrices',
  'sections/04_Primary_Results.tex',
  'All four services record zero numerical outputs before calculation and zero parsing errors',
  2,
  '3-4'),
 ('sections/04_R1_Results.tex',
  'Hunyuan decision accuracy is 0.663',
  'sections/04_Primary_Results.tex',
  'The rule-based parser completes 58 of 80 valid requests',
  1,
  '2-1'),
 ('sections/04_R1_Results.tex',
  'The remaining 14 stop at the request stage',
  'sections/04_Primary_Results.tex',
  'The paired blind replay gives the same direction',
  1,
  '2-4'),
 ('sections/05_R1_Application.tex',
  'In the 2019 selection-screened benchmark, selected-local mean test coverage',
  'sections/04_Primary_Results.tex',
  'Its mean cost is 83.32 below robust optimization',
  2,
  '3-11'),
 ('sections/05_R1_Application.tex',
  'The public validation uses quarter-hourly national load',
  'sections/05_Deployment_and_Generalization.tex',
  'External validity is evaluated on the harmonized hourly five-region panel',
  3,
  '2-9'),
 ('sections/05_R1_Application.tex',
  'The original anonymized load-weather study provides',
  'sections/05_Deployment_and_Generalization.tex',
  'The adaptive method has a lower mean resource-allocation cost',
  3,
  '2-10'),
 ('sections/05_R1_Application.tex',
  'Conditional results in the 2019 selection-screened benchmark reveal',
  'sections/05_Deployment_and_Generalization.tex',
  'Local coverage ranges from 0.940 in spring',
  2,
  '3-14'),
 ('sections/06_R1_Discussion.tex',
  'Returning an incomplete request protects',
  'sections/06_Discussion.tex',
  'The unresolved-default check also returns ambiguous requests',
  1,
  '3-7'),
 ('sections/06_R1_Discussion.tex',
  'All methods use the same selection requirement',
  'sections/06_Discussion.tex',
  'The five-region analysis supports transfer through local re-estimation',
  2,
  '2-10'),
 ('sections/06_R1_Discussion.tex',
  'Request validation establishes the calculation boundary',
  'sections/06_Discussion.tex',
  'Within the reported setting, the evidence supports a complete energy-informatics sequence',
  1,
  '3-8'),
 ('sections/07_R1_Conditions.tex',
  'The independently authored requests and scripted confirmations represent',
  'sections/07_Scope_Conditions.tex',
  'The reported request-check results apply to the saved request sets',
  3,
  '3-1'),
 ('sections/07_R1_Conditions.tex',
  'Coverage is the empirical fraction of realized targets covered',
  'sections/07_Scope_Conditions.tex',
  'The empirical coverage requirement is evaluated on these rolling results',
  2,
  '3-10'),
 ('sections/08_R1_Conclusions.tex',
  'The independent study includes 168 requests',
  'sections/08_Conclusions.tex',
  'Joint success ranges from 0.705 to 0.885 across',
  1,
  '2-3'),
 ('sections/08_R1_Conclusions.tex',
  'Public quarter-hourly load from four countries',
  'sections/08_Conclusions.tex',
  'Across 86 rolling windows, the configuration selected for lowest cost',
  4,
  '3-11')]

HISTORICAL_REFERENCES = {"eq:decision_cost": "2", "fig:cross_region": "10", "subsec:data": "3.1"}


def sentence_span(source: str, prefix: str, count: int) -> tuple[int, int]:
    if source.count(prefix) != 1:
        raise ValueError(f"Sentence anchor must be unique: {prefix}")
    start = source.index(prefix)
    endings = list(re.finditer(r"\.(?=\s|$)", source[start:]))
    if len(endings) < count:
        raise ValueError(f"Sentence count exceeds anchor: {prefix}")
    end = start + endings[count - 1].end()
    if "\n\n" in source[start:end]:
        raise ValueError(f"Highlight crosses a paragraph: {prefix}")
    return start, end


def unwrap(source: str, command: str, discard: bool = False) -> str:
    needle = "\\" + command + "{"
    while needle in source:
        start = source.index(needle)
        position = start + len(needle)
        depth = 1
        content_start = position
        while depth:
            if position >= len(source):
                raise ValueError(f"Unclosed markup command: {command}")
            if source[position] in "{}" and (position == 0 or source[position - 1] != "\\"):
                depth += 1 if source[position] == "{" else -1
            position += 1
        content = "" if discard else source[content_start:position - 1]
        source = source[:start] + content + source[position:]
    return source


def accepted_text(source: str) -> str:
    source = re.sub(r"% AEI selective preamble begin.*?% AEI selective preamble end\n", "", source, flags=re.S)
    source = source.replace(r"\clearpage", "")
    source = unwrap(unwrap(source, "DIFdel", True), "DIFadd")
    source = unwrap(source, "Rlabel", True)
    return re.sub(r"\s+", " ", source).strip()


def mark_captions(source: str) -> str:
    for match in reversed(list(re.finditer(r"\\caption\{", source))):
        content_start = match.end()
        position = content_start
        depth = 1
        while depth:
            if source[position] in "{}" and source[position - 1] != "\\":
                depth += 1 if source[position] == "{" else -1
            position += 1
        content = source[content_start:position - 1]
        if r"\DIFadd{" not in content:
            source = source[:content_start] + r"\DIFadd{" + content + "}" + source[position - 1:]
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()
    deletions = {}
    original_spans = {}
    for target, anchor, original_file, original_anchor, count, reviewer in DELETIONS:
        original = (args.baseline / original_file).read_text(encoding="utf-8-sig")
        start, end = sentence_span(original, original_anchor, count)
        deleted = original[start:end]
        if deleted in (args.source / target).read_text(encoding="utf-8-sig"):
            raise ValueError(f"Deleted text is retained in the current manuscript: {original_anchor}")
        if (target, anchor) in deletions:
            raise ValueError(f"Duplicate deletion destination: {target}: {anchor}")
        previous_spans = original_spans.setdefault(original_file, [])
        if any(start < previous_end and end > previous_start for previous_start, previous_end in previous_spans):
            raise ValueError(f"Repeated original deletion: {original_file}: {original_anchor}")
        previous_spans.append((start, end))
        def historical_reference(match):
            key = match[2]
            if key not in HISTORICAL_REFERENCES:
                raise ValueError(f"Missing original AEI reference number: {key}")
            value = HISTORICAL_REFERENCES[key]
            return "(" + value + ")" if match[1] == "eqref" else value
        displayed = re.sub(r"\\(eqref|ref)\{([^}]+)\}", historical_reference, deleted)
        deletions[(target, anchor)] = {"text": displayed, "original_text": deleted, "original_file": original_file,
                                     "original_anchor": original_anchor, "sentences": count,
                                     "reviewer": reviewer}
    report = {"mode": "reviewer-related selective marking", "files": [], "marks": []}
    reviewers = Counter()
    for relative, marks in MARKS.items():
        clean = (args.source / relative).read_text(encoding="utf-8-sig")
        spans = []
        for prefix, count, reviewer in marks:
            start, end = sentence_span(clean, prefix, count)
            added = clean[start:end]
            deletion = deletions.get((relative, prefix))
            deleted = deletion["text"] if deletion else None
            replacement = ("\\DIFdel{" + deleted + "} " if deleted else "") + "\\DIFadd{" + added + "}"
            if reviewer:
                replacement += "\\Rlabel{R\\#" + reviewer + "}"
                reviewers[reviewer] += 1
            spans.append((start, end, replacement))
            report["marks"].append({"file": relative, "anchor": prefix, "sentences": count,
                                    "reviewer": reviewer, "added": added, "deleted": deleted,
                                    "deletion_source": deletion})
        spans.sort()
        if any(current[1] > following[0] for current, following in zip(spans, spans[1:])):
            raise ValueError(f"Overlapping selective highlights: {relative}")
        marked = clean
        for start, end, replacement in reversed(spans):
            marked = marked[:start] + replacement + marked[end:]
        if relative == "sections/02_Problem_Formulation.tex":
            caption = "Request checks and the verified reserve calculation."
            marked = marked.replace("\\caption{" + caption + "}", "\\caption{\\DIFadd{" + caption + "}\\Rlabel{R\\#2-10}}", 1)
            reviewers["2-10"] += 1
        if relative == "main.tex":
            preamble = (Path(__file__).parent / "r1_latexdiff_preamble.tex").read_text(encoding="utf-8-sig")
            marked = marked.replace("\\begin{document}", "% AEI selective preamble begin\n" + preamble + "\n% AEI selective preamble end\n\\begin{document}", 1)
        if relative == "sections/03_Data_and_Experimental_Design.tex":
            def mark_design_table(match):
                table = re.sub(r"\\caption\{([^{}]+)\}", r"\\caption{\\DIFadd{\1}}", match[0])
                lines = []
                for line in table.splitlines():
                    if "&" in line and line.rstrip().endswith(r"\\") and not line.lstrip().startswith(("Study &", "Item &")):
                        cells = line[:-2].rstrip().split("&")
                        cells = [" \\DIFadd{" + cell.strip() + "} " for cell in cells]
                        line = "&".join(cells).rstrip() + r" \\"
                    lines.append(line)
                return "\n".join(lines)
            marked = re.sub(r"\\begin\{table\}.*?\\end\{table\}", mark_design_table, marked, flags=re.S)
        if relative == "sections/06_R1_Discussion.tex":
            marked = marked.replace(r"\section{Discussion}", "\\clearpage\n" + r"\section{Discussion}", 1)
        marked = mark_captions(marked)
        if accepted_text(marked) != accepted_text(clean):
            raise ValueError(f"Selective marking changes accepted content: {relative}")
        (args.root / relative).write_text(marked, encoding="utf-8")
        report["files"].append({"file": relative, "accepted_content_matches_clean": True,
                                "source_sha256": hashlib.sha256(clean.encode()).hexdigest()})
    table_counts = {}
    manuscript = (args.source / "main.tex").read_text(encoding="utf-8-sig")
    main_sections = re.findall(r"\\input\{([^}]+)\}", manuscript)
    main_tables = set()
    for relative in main_sections:
        section = (args.source / relative).read_text(encoding="utf-8-sig")
        main_tables.update(re.findall(r"\\input\{sections/r1_tables/([^}]+)\.tex\}", section))
    for source in (args.source / "sections" / "r1_tables").glob("*.tex"):
        if source.stem not in main_tables:
            continue
        clean = source.read_text(encoding="utf-8-sig")
        marked = re.sub(r"\\caption\{([^{}]+)\}", r"\\caption{\\DIFadd{\1}}", clean)
        cell_count = 0
        lines = []
        for line in marked.splitlines():
            if "&" in line and line.rstrip().endswith(r"\\") and re.search(r"(?<![A-Za-z])\d", line):
                cells = line[:-2].rstrip().split("&")
                for index, cell in enumerate(cells):
                    value = cell.strip()
                    if index and re.search(r"\d", value):
                        cells[index] = " \\DIFadd{" + value + "} "
                        cell_count += 1
                line = "&".join(cells).rstrip() + r" \\"
            lines.append(line)
        marked = "\n".join(lines) + "\n"
        if accepted_text(marked) != accepted_text(clean):
            raise ValueError(f"Marked table changes accepted content: {source.name}")
        (args.root / "sections" / "r1_tables" / source.name).write_text(marked, encoding="utf-8")
        table_counts[source.stem] = cell_count
    supplementary = (args.source / "Supplementary_Material.tex").read_text(encoding="utf-8-sig")
    transparent = "% AEI selective preamble begin\n\\providecommand{\\DIFadd}[1]{#1}\n\\providecommand{\\Rlabel}[1]{}\n% AEI selective preamble end\n"
    supplementary = supplementary.replace("\\begin{document}", transparent + "\\begin{document}", 1)
    (args.root / "Supplementary_Material.tex").write_text(supplementary, encoding="utf-8")
    expected = {"1-" + str(number) for number in range(1, 3)}
    expected.update("2-" + str(number) for number in range(1, 11))
    expected.update("3-" + str(number) for number in range(1, 17))
    if set(reviewers) != expected or any(count != 1 for count in reviewers.values()):
        raise ValueError(f"Each reviewer comment needs one separate anchor: {dict(reviewers)}")
    marked_anchors = {(entry["file"], entry["anchor"]) for entry in report["marks"]}
    if set(deletions) - marked_anchors:
        raise ValueError(f"Unapplied deletion anchors: {set(deletions) - marked_anchors}")
    report.update({"reviewer_tags": dict(reviewers), "table_numeric_cells": table_counts,
                   "substantive_text_spans": len(report["marks"]), "deletion_spans": len(deletions),
                   "deleted_sentences": sum(entry["sentences"] for entry in deletions.values()),
                   "deletion_reviewer_comments": sorted({entry["reviewer"] for entry in deletions.values()}),
                   "accepted_content_verified": True, "grouped_reviewer_tags": 0})
    output = args.root.parent / "results" / "selective_marking"
    output.mkdir(parents=True, exist_ok=True)
    (output / "marking_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("substantive_text_spans", "deletion_spans", "grouped_reviewer_tags", "accepted_content_verified")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
