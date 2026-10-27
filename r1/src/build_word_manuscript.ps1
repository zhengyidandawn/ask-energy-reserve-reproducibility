[CmdletBinding()]
param(
    [switch]$CopyToSubmission
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$submissionLayout = Test-Path -LiteralPath (Join-Path $projectRoot 'Source_unmark')
$sourceRoot = if ($submissionLayout) { Join-Path $projectRoot 'Source_unmark' } else { Join-Path $projectRoot 'elsarticle_unmark' }
$resultsRoot = Join-Path $projectRoot 'results'
$projectName = Split-Path -Leaf $projectRoot
$parentRoot = Split-Path -Parent $projectRoot
if ($submissionLayout) {
    $submissionRoot = $projectRoot
}
else {
    $submissionRoot = Get-ChildItem -LiteralPath $parentRoot -Directory |
        Where-Object { $_.Name.EndsWith('_AEI_R1') -and $_.Name -ne $projectName -and (Test-Path (Join-Path $_.FullName 'Source_unmark')) } |
        Select-Object -First 1 -ExpandProperty FullName
    $submissionRoot = [string]$submissionRoot
}
$latexpand = if ($env:LATEXPAND) { $env:LATEXPAND } else { (Get-Command latexpand -ErrorAction Stop).Source }
$pandoc = if ($env:PANDOC) { $env:PANDOC } else { (Get-Command pandoc -ErrorAction Stop).Source }
$pdftoppm = if ($env:PDFTOPPM) { $env:PDFTOPPM } else { (Get-Command pdftoppm -ErrorAction Stop).Source }
$flattened = Join-Path $resultsRoot 'Manuscript_unmark_flattened.tex'
$wordFlattened = Join-Path $resultsRoot 'Manuscript_unmark_word.tex'
$wordFigures = Join-Path $resultsRoot 'word_figures'
$wordFile = Join-Path $resultsRoot 'Manuscript_unmark.docx'
New-Item -ItemType Directory -Force -Path $resultsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $wordFigures | Out-Null

Push-Location $sourceRoot
try {
    & $latexpand --empty-comments main.tex | Set-Content -LiteralPath $flattened -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw 'latexpand failed.' }
}
finally {
    Pop-Location
}

$flattenedText = Get-Content -LiteralPath $flattened -Raw
$python = if ($env:AEI_PYTHON) { $env:AEI_PYTHON } else { (Get-Command python -ErrorAction Stop).Source }
$aux = Join-Path $resultsRoot 'manuscript_unmark_build\main.aux'
$bbl = Join-Path $resultsRoot 'manuscript_unmark_build\main.bbl'
if (-not (Test-Path -LiteralPath $aux) -or -not (Test-Path -LiteralPath $bbl)) {
    & (Join-Path $PSScriptRoot 'compile_aei_r1.ps1') -Target unmark
}
& $python (Join-Path $PSScriptRoot 'prepare_word_source.py') --input $flattened --aux $aux --bbl $bbl --output $wordFlattened
if ($LASTEXITCODE -ne 0) { throw 'Word source reference resolution failed.' }
$flattenedText = Get-Content -LiteralPath $wordFlattened -Raw
$imageMatches = [regex]::Matches($flattenedText, '\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}')
foreach ($imageMatch in $imageMatches) {
    $imageName = [IO.Path]::GetFileName($imageMatch.Groups[1].Value)
    $imageBaseName = [IO.Path]::GetFileNameWithoutExtension($imageName)
    $sourceImage = Join-Path $sourceRoot (Join-Path 'figures' $imageName)
    if (-not (Test-Path -LiteralPath $sourceImage)) {
        throw "Referenced figure was not found: $sourceImage"
    }
    if ([IO.Path]::GetExtension($imageName).ToLowerInvariant() -eq '.pdf') {
        $wordImage = Join-Path $wordFigures ($imageBaseName + '.png')
        $wordImageBase = Join-Path $wordFigures $imageBaseName
        & $pdftoppm -png -singlefile -r 220 $sourceImage $wordImageBase
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $wordImage)) {
            throw "Failed to rasterize figure for Word conversion: $sourceImage"
        }
        $flattenedText = $flattenedText.Replace("{$imageName}", "{$imageBaseName.png}")
    }
}
Set-Content -LiteralPath $wordFlattened -Value $flattenedText -Encoding UTF8

$resourcePath = "$sourceRoot;$wordFigures;$([IO.Path]::Combine($sourceRoot, 'figures'));$([IO.Path]::Combine($sourceRoot, 'sections'))"
& $pandoc $wordFlattened --from=latex --to=docx --standalone --number-sections --resource-path=$resourcePath --output=$wordFile
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $wordFile)) {
    throw 'Pandoc Word conversion failed.'
}
& $python (Join-Path $PSScriptRoot 'normalize_word_tables.py') $wordFile
if ($LASTEXITCODE -ne 0) { throw 'Word table pagination failed.' }
if ($CopyToSubmission) {
    if (-not $submissionRoot) { throw 'Submission directory was not found.' }
    $submissionWordFile = Join-Path $submissionRoot 'Manuscript_unmark.docx'
    if ([IO.Path]::GetFullPath($wordFile) -ne [IO.Path]::GetFullPath($submissionWordFile)) {
        Copy-Item -LiteralPath $wordFile -Destination $submissionWordFile -Force
    }
}
Write-Output "Created $wordFile"
