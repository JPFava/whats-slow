# Run from this folder:
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
# Double-click run.bat instead if you do not want to deal with PowerShell.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = "py" }
}
if (-not $py) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Host "Python was not found. Install it from https://www.python.org/downloads/"
        exit 1
    }
    $py = "python"
}

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Setting up a private Python environment in this folder..."
    if ($py -eq "py") { & py -3 -m venv .venv } else { & python -m venv .venv }
}
& $venvPy -m pip install --disable-pip-version-check -q -r requirements.txt
Write-Host ""
Write-Host "Watching the PC. A pause of several seconds is the measurement."
Write-Host ""
& $venvPy -m whats_slow --open @args
Write-Host ""
Write-Host "A copy is in the reports folder."
