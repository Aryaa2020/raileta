# Compatibility helper: run one or more structured adapter polls directly.
$pythonExe = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    Write-Error 'Create the virtual environment and install requirements first.'
    exit 1
}

Write-Host 'Starting RailETA MAS-SBC structured data collector...' -ForegroundColor Cyan
& $pythonExe manage.py collect_events
