$ErrorActionPreference = "Stop"

$repoRoot = Split-Path $PSScriptRoot -Parent
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error ".venv not found. Please run build.ps1 first."
    exit 1
}

$syncScript = Join-Path $PSScriptRoot "sync-origin-and-mirror.py"
& $venvPython -u $syncScript
exit $LASTEXITCODE
