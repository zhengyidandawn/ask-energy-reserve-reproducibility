[CmdletBinding()]
param(
    [switch]$ReferenceOnly,
    [string[]]$DocumentNames = @('Response_to_Reviewers_AEI_R1_CN.docx', 'Response_to_Reviewers_AEI_R1_EN.docx', 'CoverLetter.docx', 'Highlights.docx', 'Manuscript_unmark.docx')
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$submissionRoot = Join-Path (Split-Path -Parent $projectRoot) '提交_AEI_R1'
$outputRoot = Join-Path $projectRoot 'results\word_render_r1'
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
$documents = if ($ReferenceOnly) {
    @('E:\论文\工作内论文\Information Processing & Management\修改R1\Response_to_reviewers.docx')
} else {
    $DocumentNames | ForEach-Object { Join-Path $submissionRoot $_ }
}
$taskWord = New-Object -ComObject Word.Application
$taskWord.Visible = $false
$taskWord.DisplayAlerts = 0
try {
    foreach ($sourcePath in $documents) {
        if (-not (Test-Path -LiteralPath $sourcePath)) { continue }
        $name = [IO.Path]::GetFileNameWithoutExtension($sourcePath)
        if ($ReferenceOnly) { $name = 'IPM_reference' }
        $renderRoot = Join-Path $outputRoot $name
        New-Item -ItemType Directory -Force -Path $renderRoot | Out-Null
        $pdfPath = Join-Path $renderRoot ($name + '.pdf')
        $taskDocument = $taskWord.Documents.Open($sourcePath, $false, $true)
        try {
            $taskDocument.Repaginate()
            $taskDocument.ExportAsFixedFormat($pdfPath, 17)
        }
        finally {
            $taskDocument.Close(0)
        }
        Get-ChildItem -LiteralPath $renderRoot -File -Filter 'page-*.png' | ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force
        }
        & pdftoppm -png -r 110 $pdfPath (Join-Path $renderRoot 'page')
        if ($LASTEXITCODE -ne 0) { throw "Word PDF rasterization failed: $name" }
        Write-Output "Rendered $name"
    }
}
finally {
    $taskWord.Quit()
}
