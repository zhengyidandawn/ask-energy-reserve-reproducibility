[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$submissionLayout = Test-Path -LiteralPath (Join-Path $projectRoot 'Source_unmark')
if ($submissionLayout) {
    $baselineRoot = Join-Path $projectRoot 'Source_baseline'
    $revisedRoot = Join-Path $projectRoot 'Source_unmark'
    $markedRoot = Join-Path $projectRoot 'Source_mark'
}
else {
    $baselineRoot = Join-Path $projectRoot 'baseline'
    $revisedRoot = Join-Path $projectRoot 'elsarticle_unmark'
    $markedRoot = Join-Path $projectRoot 'elsarticle_mark'
}
if (-not (Test-Path -LiteralPath $baselineRoot)) { throw "Baseline source directory was not found: $baselineRoot" }
Get-ChildItem -LiteralPath $revisedRoot -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($revisedRoot.Length).TrimStart('\')
    $marked = Join-Path $markedRoot $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $marked) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $marked -Force
}
$python = if ($env:AEI_PYTHON) { $env:AEI_PYTHON } else { (Get-Command python -ErrorAction Stop).Source }
& $python (Join-Path $PSScriptRoot 'add_reviewer_labels.py') $markedRoot --source $revisedRoot --baseline $baselineRoot
if ($LASTEXITCODE -ne 0) { throw 'Selective reviewer-related marking failed.' }
@'
# AEI R1 selective manuscript marking

The manuscript retains all accepted text from the AEI clean source.
Blue marks identify substantive revisions described in the response letters.
Red deletions retain selected original statements directly related to reviewer concerns.
Each of the 28 specific comments has one separate label on its corresponding sentence or figure caption.
New result tables mark their captions and numerical cells; table structure, headings, and notes remain black.
Routine language edits and broad paragraph restructuring are omitted from the visible comparison.
The supplementary material is retained as an unmarked document.
Run mark_aei_r1.ps1 and compile main.tex after updating the clean source or the marking anchors.
'@ | Set-Content -LiteralPath (Join-Path $markedRoot 'MARKING_STATUS.md') -Encoding UTF8
Write-Output "Selective marked source refreshed at $markedRoot"
