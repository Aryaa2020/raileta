# RailETA Station Display Starter Script

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Starting Station Display" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

cd frontend/station-display

# Check if node_modules exists
if (-Not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies (this may take a few minutes)..." -ForegroundColor Yellow
    npm install
    Write-Host "Dependencies installed!" -ForegroundColor Green
}

Write-Host ""
Write-Host "=====================================" -ForegroundColor Green
Write-Host "Station Display Starting..." -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
Write-Host ""
Write-Host "Display will be available at:" -ForegroundColor Cyan
Write-Host "  http://localhost:4175" -ForegroundColor White
Write-Host ""
Write-Host "Keyboard shortcuts:" -ForegroundColor Yellow
Write-Host "  1 - Chennai Central" -ForegroundColor White
Write-Host "  2 - Katpadi Junction" -ForegroundColor White
Write-Host "  3 - KSR Bengaluru" -ForegroundColor White
Write-Host "  R - Refresh" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

npm run dev -- --host 127.0.0.1 --port 4175
