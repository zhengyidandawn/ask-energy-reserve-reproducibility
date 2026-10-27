[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$submissionRoot = Join-Path (Split-Path -Parent $projectRoot) '提交_AEI_R1'
$auditRoot = Join-Path $projectRoot 'results\submission_revision_20261026'
$backupRoot = Join-Path $auditRoot 'before_submission'
$workspacePrefix = [IO.Path]::GetFullPath((Split-Path -Parent $projectRoot)).TrimEnd('\') + '\'

function Assert-InWorkspace([string]$path) {
    $resolved = [IO.Path]::GetFullPath($path)
    if(-not $resolved.StartsWith($workspacePrefix,[StringComparison]::OrdinalIgnoreCase)) {
        throw "Target escaped the intended revision workspace: $resolved"
    }
}

function Preserve-Directory([string]$path) {
    if(-not (Test-Path -LiteralPath $path)) { return }
    Assert-InWorkspace $path
    $name = Split-Path -Leaf $path
    $target = Join-Path $backupRoot $name
    $index = 1
    while(Test-Path -LiteralPath $target) {
        $target = Join-Path $backupRoot ($name + '_' + $index)
        $index++
    }
    Assert-InWorkspace $target
    Move-Item -LiteralPath $path -Destination $target
}

function Copy-SourceTree([string]$source,[string]$target) {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    foreach($file in Get-ChildItem -LiteralPath $source -Recurse -File) {
        $relative = $file.FullName.Substring($source.Length).TrimStart('\')
        if($relative -match '(^|\\)(output|__pycache__|\.git)(\\|$)' -or
           $file.Extension -in @('.pyc','.aux','.log','.fls','.fdb_latexmk','.synctex','.out','.toc','.blg','.bbl','.abs')) { continue }
        $destination = Join-Path $target $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    }
}

Assert-InWorkspace $submissionRoot
Assert-InWorkspace $backupRoot
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
foreach($file in Get-ChildItem -LiteralPath $submissionRoot -File) {
    $target = Join-Path $backupRoot $file.Name
    if(-not (Test-Path -LiteralPath $target)) { Copy-Item -LiteralPath $file.FullName -Destination $target }
}

$deliverables = @{
    'results\Manuscript_unmark.pdf'='Manuscript_unmark.pdf'
    'results\Manuscript_mark.pdf'='Manuscript_mark.pdf'
    'results\Manuscript_unmark.docx'='Manuscript_unmark.docx'
    'results\Supplementary_Material.pdf'='补充材料.pdf'
    'article\Response_to_Reviewers_AEI_R1_EN.docx'='Response_to_Reviewers_AEI_R1_EN.docx'
    'article\Response_to_Reviewers_AEI_R1_CN.docx'='Response_to_Reviewers_AEI_R1_CN.docx'
    'article\CoverLetter.docx'='CoverLetter.docx'
    'article\Highlights.docx'='Highlights.docx'
    'article\题目摘要关键词.txt'='题目摘要关键词.txt'
}
foreach($relative in $deliverables.Keys) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $relative) -Destination (Join-Path $submissionRoot $deliverables[$relative]) -Force
}

foreach($item in @(
    @{Source='elsarticle_unmark'; Target='Source_unmark'},
    @{Source='elsarticle_mark'; Target='Source_mark'},
    @{Source='baseline'; Target='Source_baseline'},
    @{Source='src'; Target='Compilation_scripts'}
)) {
    $target = Join-Path $submissionRoot $item.Target
    Preserve-Directory $target
    Copy-SourceTree (Join-Path $projectRoot $item.Source) $target
}
Preserve-Directory (Join-Path $submissionRoot 'results')

$packageRoot = Join-Path $submissionRoot 'Reproducibility_package_AEI_R1'
Assert-InWorkspace $packageRoot
Copy-SourceTree (Join-Path $projectRoot 'src') (Join-Path $packageRoot 'src')
Copy-SourceTree (Join-Path $projectRoot 'article\templates') (Join-Path $packageRoot 'article\templates')
$readme = Join-Path $packageRoot 'README.txt'
$note = @'

Manuscript synchronization on 26 October 2026
The revised manuscript distinguishes the public 2019 benchmark, later frozen-margin
comparison, and archived regional study. Numerical results and archived model responses
are unchanged. Updated document builders and the retained reply template are included.
The clean and marked LaTeX sources are supplied separately in the submission directory.
'@
if(-not ([IO.File]::ReadAllText($readme).Contains('Manuscript synchronization on 26 October 2026'))) {
    Add-Content -LiteralPath $readme -Value $note -Encoding UTF8
}

& (Join-Path $projectRoot 'src\package_aei_r1.ps1')
& (Join-Path $projectRoot 'src\r1\build_reproducibility_package.ps1') -FinalizeOnly

$aliasRoot = Join-Path $projectRoot 'elsarticle_unmark\output\pdf'
if(Test-Path -LiteralPath $aliasRoot) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'results\Supplementary_Material.pdf') -Destination (Join-Path $aliasRoot 'Supplementary_Material.pdf') -Force
}
Write-Output 'Submission documents, sources, scripts, and archives synchronized.'
