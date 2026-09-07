# RailETA Controller Dashboard Starter Script

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Starting Controller Dashboard" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

cd frontend/controller-dashboard

# Check if node_modules exists
if (-Not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies (this may take a few minutes)..." -ForegroundColor Yellow
    npm install
    Write-Host "Dependencies installed!" -ForegroundColor Green
}

Write-Host ""
Write-Host "=====================================" -ForegroundColor Green
Write-Host "Controller Dashboard Starting..." -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
Write-Host ""
Write-Host "Dashboard will be available at:" -ForegroundColor Cyan
Write-Host "  http://localhost:4174" -ForegroundColor White
Write-Host ""
Write-Host "Features:" -ForegroundColor Yellow
Write-Host "  - Visual corridor map with trains" -ForegroundColor White
Write-Host "  - Click trains for details" -ForegroundColor White
Write-Host "  - Event freshness and fallback badges" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

npm run dev -- --host 127.0.0.1 --port 4174
