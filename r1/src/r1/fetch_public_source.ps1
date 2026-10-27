param([Parameter(Mandatory)][string]$Url, [Parameter(Mandatory)][string]$Destination)
$ErrorActionPreference = 'Stop'
if (-not $Url.StartsWith('https://', [StringComparison]::OrdinalIgnoreCase)) { throw 'HTTPS is required.' }
Invoke-WebRequest -Uri $Url -OutFile $Destination -TimeoutSec 120
