[CmdletBinding()]
param([switch]$FinalizeOnly)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$submissionRoot = Join-Path (Split-Path -Parent $projectRoot) '提交_AEI_R1'
$packageRoot = Join-Path $submissionRoot 'Reproducibility_package_AEI_R1'
$archive = Join-Path $submissionRoot 'Reproducibility_package_AEI_R1.zip'
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $projectRoot)
$python = if ($env:AEI_PYTHON) { $env:AEI_PYTHON } else { (Get-Command python -ErrorAction Stop).Source }

function Copy-Tree($relativePath) {
    $source = Join-Path $projectRoot $relativePath
    $destination = Join-Path $packageRoot $relativePath
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    Get-ChildItem -LiteralPath $source -Recurse -File |
        Where-Object {
            $_.Extension -notin @('.pyc', '.log', '.aux', '.fls', '.fdb_latexmk', '.synctex.gz') -and
            $_.Name -notin @('assessment_console.txt', '混元结果可用性评估.txt', 'hunyuan_usability_assessment.json') -and
            ($_.Extension -eq '.py' -or $_.Name -notmatch '(^|_)(smoke|failure|failed|rate_limit|quota|余额|限流)') -and
            $_.Name -ne 'final_analysis_console.txt' -and
            ($relativePath -ne 'data/online_draft_audit_20261011' -or $_.FullName -notmatch '\\smoke[^\\]*\\')
        } |
        ForEach-Object {
            $relative = $_.FullName.Substring($source.Length).TrimStart('\')
            $target = Join-Path $destination $relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
}

function Copy-File($relativePath, $targetRelativePath = $relativePath) {
    $source = Join-Path $projectRoot $relativePath
    $target = Join-Path $packageRoot $targetRelativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
}

if (-not $FinalizeOnly) {
if (Test-Path -LiteralPath $packageRoot) {
    $resolvedPackage = [IO.Path]::GetFullPath($packageRoot)
    $resolvedSubmission = [IO.Path]::GetFullPath($submissionRoot).TrimEnd('\') + '\'
    if (-not $resolvedPackage.StartsWith($resolvedSubmission, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($resolvedPackage) -ne 'Reproducibility_package_AEI_R1') {
        throw 'The package cleanup target is outside the intended submission directory.'
    }
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}
New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
Copy-Tree 'src'
Copy-Tree 'data/human_r1'
Copy-Tree 'data/public_validation_r1'
Copy-Tree 'data/paired_public_execution'
Copy-Tree 'data/api_r1/clarification_protocol_v1'
Copy-Tree 'data/api_r1/historical'
Copy-Tree 'data/literature/strengthening_20261011'
Copy-Tree 'data/literature/cited_reference_verification_20261011'
Copy-Tree 'data/literature/positive_revision'
Copy-Tree 'data/api_r1/provider_documentation'
Copy-Tree 'data/evidence_completion_20261011'
Copy-Tree 'data/substantive_resolution_20261011'
Copy-Tree 'data/online_draft_audit_20261011'
Copy-Tree 'data/literature/online_draft_audit_20261011'
Copy-Tree 'results/integrated_r1'
Copy-Tree 'results/paired_evidence'
Copy-Tree 'results/paired_public_execution'
Copy-Tree 'results/positive_revision_20261011'
Copy-Tree 'results/substantive_resolution_20261011'
Copy-Tree 'results/online_draft_audit_20261011'
Copy-Tree 'results/remaining_review_questions_20261011'
Copy-Tree 'results/public_validation_r1'
Copy-Tree 'results/strengthening_20261011'
Copy-Tree 'results/evidence_completion_20261011'
Copy-Tree 'results/reconstructed_evidence'
Copy-File 'results/hunyuan_recovery_v2/summary.json'

$checkerRoot = Join-Path $workspaceRoot 'src\ask'
Get-ChildItem -LiteralPath $checkerRoot -File -Filter '*.py' | ForEach-Object {
    $target = Join-Path $packageRoot (Join-Path 'src\ask' $_.Name)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $target -Force
}
$originalInputs = @(
    'supplementary_artifacts\blind_end_to_end_holdout\case_execution_results.csv',
    'supplementary_artifacts\llm_benchmark\case_labels_blind.csv',
    'supplementary_artifacts\llm_benchmark\prompts_blind.jsonl',
    'experiments\outputs\llm_benchmark\blind\deepseek\model_outputs.jsonl'
)
foreach ($relativePath in $originalInputs) {
    $source = Join-Path $workspaceRoot $relativePath
    $target = Join-Path $packageRoot (Join-Path 'data\original_study' $relativePath)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
}
& $python (Join-Path $projectRoot 'src\r1\export_completed_records.py') --package-root $packageRoot
if ($LASTEXITCODE -ne 0) { throw 'Completed-response export failed.' }
$manifest = @(Import-Csv -LiteralPath (Join-Path $packageRoot 'data\formal_api_records_manifest.csv'))
$requirements = & $python (Join-Path $projectRoot 'src\r1\capture_requirements.py')
if ($LASTEXITCODE -ne 0) { throw 'Dependency-version capture failed.' }
$requirements | Set-Content -LiteralPath (Join-Path $packageRoot 'requirements.txt') -Encoding UTF8

$readme = @'
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
'@
Set-Content -LiteralPath (Join-Path $packageRoot 'README.txt') -Value $readme -Encoding UTF8
}

$resolvedPackage = [IO.Path]::GetFullPath($packageRoot).TrimEnd('\') + '\'
Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Filter '*.pyc' | ForEach-Object {
    if (-not $_.FullName.StartsWith($resolvedPackage, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Generated bytecode cleanup escaped the package directory.'
    }
    Remove-Item -LiteralPath $_.FullName -Force
}
$allFiles = Get-ChildItem -LiteralPath $packageRoot -Recurse -File |
    Where-Object { $_.Name -ne 'package_manifest.csv' } | Sort-Object FullName
$inventory = foreach ($file in $allFiles) {
    [pscustomobject]@{
        path = $file.FullName.Substring($packageRoot.Length).TrimStart('\')
        bytes = $file.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    }
}
$inventory | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath (Join-Path $packageRoot 'package_manifest.csv')
$archive = Join-Path $submissionRoot 'Reproducibility_package_AEI_R1.zip'
Compress-Archive -LiteralPath $packageRoot -DestinationPath $archive -Force
Write-Output "Created $packageRoot"
Write-Output "Created $archive"
$recordCount = @(Import-Csv -LiteralPath (Join-Path $packageRoot 'data\formal_api_records_manifest.csv')).Count
Write-Output "Successful formal records: $recordCount"
