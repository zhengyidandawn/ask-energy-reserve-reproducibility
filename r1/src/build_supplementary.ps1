[CmdletBinding()]
param([switch]$CopyToSubmission)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'compile_aei_r1.ps1') -Target supplementary -CopyToSubmission:$CopyToSubmission
