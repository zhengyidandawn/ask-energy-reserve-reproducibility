[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectName = Split-Path -Leaf $projectRoot
$parentRoot = Split-Path -Parent $projectRoot
$submissionRoot = if (Test-Path -LiteralPath (Join-Path $projectRoot 'Source_unmark')) {
    $projectRoot
} else {
    Get-ChildItem -LiteralPath $parentRoot -Directory |
        Where-Object { $_.Name.EndsWith('_AEI_R1') -and $_.Name -ne $projectName -and (Test-Path (Join-Path $_.FullName 'Source_unmark')) } |
        Select-Object -First 1 -ExpandProperty FullName
}
$submissionRoot = [string]$submissionRoot
$sourceUnmark = Join-Path $submissionRoot 'Source_unmark'
$sourceMark = Join-Path $submissionRoot 'Source_mark'
$unmarkZip = Join-Path $submissionRoot 'LaTeX_Source_unmark_AEI_R1.zip'
$markZip = Join-Path $submissionRoot 'LaTeX_Source_mark_AEI_R1.zip'

if (-not $submissionRoot) { throw 'Submission directory was not found.' }
Compress-Archive -LiteralPath $sourceUnmark -DestinationPath $unmarkZip -Force
Compress-Archive -LiteralPath $sourceMark -DestinationPath $markZip -Force
Write-Output "Created $unmarkZip"
Write-Output "Created $markZip"
