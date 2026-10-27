[CmdletBinding()]
param(
    [ValidateSet('unmark', 'mark', 'supplementary')]
    [string]$Target = 'unmark',
    [switch]$CopyToSubmission
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$resultsRoot = Join-Path $projectRoot 'results'
$projectName = Split-Path -Leaf $projectRoot
$parentRoot = Split-Path -Parent $projectRoot
$submissionLayout = Test-Path -LiteralPath (Join-Path $projectRoot 'Source_unmark')
if ($submissionLayout) {
    $submissionRoot = $projectRoot
    $unmarkSourceRoot = Join-Path $projectRoot 'Source_unmark'
    $markSourceRoot = Join-Path $projectRoot 'Source_mark'
}
else {
    $submissionRoot = Get-ChildItem -LiteralPath $parentRoot -Directory |
        Where-Object { $_.Name.EndsWith('_AEI_R1') -and $_.Name -ne $projectName -and (Test-Path (Join-Path $_.FullName 'Source_unmark')) } |
        Select-Object -First 1 -ExpandProperty FullName
    $submissionRoot = [string]$submissionRoot
    $unmarkSourceRoot = Join-Path $projectRoot 'elsarticle_unmark'
    $markSourceRoot = Join-Path $projectRoot 'elsarticle_mark'
}
$latexmk = if ($env:LATEXMK) { $env:LATEXMK } else { (Get-Command latexmk -ErrorAction Stop).Source }

switch ($Target) {
    'unmark' {
        $sourceRoot = $unmarkSourceRoot
        $entry = 'main.tex'
        $buildRoot = Join-Path $resultsRoot 'manuscript_unmark_build'
        $pdfName = 'Manuscript_unmark.pdf'
    }
    'mark' {
        $sourceRoot = $markSourceRoot
        $entry = 'main.tex'
        $buildRoot = Join-Path $resultsRoot 'manuscript_mark_build'
        $pdfName = 'Manuscript_mark.pdf'
    }
    'supplementary' {
        $sourceRoot = $unmarkSourceRoot
        $entry = 'Supplementary_Material.tex'
        $buildRoot = Join-Path $resultsRoot 'supplementary_build'
        $pdfName = 'Supplementary_Material.pdf'
    }
}

New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
Push-Location $sourceRoot
try {
    & $latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error "-outdir=$buildRoot" "-auxdir=$buildRoot" $entry
    if ($LASTEXITCODE -ne 0) {
        throw "LaTeX compilation failed for $entry with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$compiled = Join-Path $buildRoot ([IO.Path]::GetFileNameWithoutExtension($entry) + '.pdf')
if (-not (Test-Path -LiteralPath $compiled)) {
    throw "Expected PDF was not produced: $compiled"
}

$resultPdf = Join-Path $resultsRoot $pdfName
Copy-Item -LiteralPath $compiled -Destination $resultPdf -Force
if ($CopyToSubmission) {
    if (-not $submissionRoot) { throw 'Submission directory was not found.' }
    $submissionPdfName = if ($Target -eq 'supplementary') { '补充材料.pdf' } else { $pdfName }
    Copy-Item -LiteralPath $resultPdf -Destination (Join-Path $submissionRoot $submissionPdfName) -Force
}
Write-Output "Created $resultPdf"
