$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' -and $_.CommandLine -match 'celery -A django_service worker' }) { Write-Host 'RailETA worker is already running.'; exit 0 }
$pythonExe = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) { throw 'Create the virtual environment and install requirements first.' }
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'logs') -Force | Out-Null
& $pythonExe -m celery -A django_service worker --loglevel=INFO --pool=solo
