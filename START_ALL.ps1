# START ALL RAILETA SERVICES
# This will open Redis, Django, Celery worker/beat, and the three dashboards.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
# Complete schema setup before workers can consume queued jobs.
& "$PSScriptRoot\start_redis.ps1"
& "$PSScriptRoot\venv\Scripts\python.exe" manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed; no services started.' }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  STARTING RAILETA COMPLETE SYSTEM" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Start Backend
Write-Host "1. Starting Backend API..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-File", "start_backend.ps1"
Start-Sleep -Seconds 3

# Start Redis broker
Write-Host "2. Starting Redis broker..." -ForegroundColor Yellow
& "$PSScriptRoot\start_redis.ps1"

# Start Celery worker and beat as separate processes
Write-Host "3. Starting Celery worker..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-File", "$PSScriptRoot\start_celery_worker.ps1"
Start-Sleep -Seconds 2

Write-Host "4. Starting Celery beat..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-File", "$PSScriptRoot\start_celery_beat.ps1"
Start-Sleep -Seconds 2

# Start Passenger UI
Write-Host "5. Starting Passenger UI..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-File", "$PSScriptRoot\start_passenger_ui.ps1"
Start-Sleep -Seconds 2

# Start Station Display
Write-Host "6. Starting Station Display..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-File", "$PSScriptRoot\start_station_display.ps1"
Start-Sleep -Seconds 2

# Start Controller Dashboard
Write-Host "7. Starting Controller Dashboard..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-File", "$PSScriptRoot\start_controller_dashboard.ps1"
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ALL SERVICES STARTING!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Wait 10-20 seconds for everything to start, then open:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Backend API:" -ForegroundColor Yellow
Write-Host "    http://localhost:8000/api/v1/health" -ForegroundColor White
Write-Host ""
Write-Host "  Passenger UI:" -ForegroundColor Yellow
Write-Host "    http://localhost:4173" -ForegroundColor White
Write-Host ""
Write-Host "  Ingestion:" -ForegroundColor Yellow
Write-Host "    Simulated CRIS-style events via Celery beat every 30 seconds" -ForegroundColor White
Write-Host ""
Write-Host "  Station Display:" -ForegroundColor Yellow
Write-Host "    http://localhost:4175" -ForegroundColor White
Write-Host ""
Write-Host "  Controller Dashboard:" -ForegroundColor Yellow
Write-Host "    http://localhost:4174" -ForegroundColor White
Write-Host ""
Write-Host "Close each PowerShell window to stop that service." -ForegroundColor Gray
Write-Host ""
Write-Host "Press any key to exit this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
