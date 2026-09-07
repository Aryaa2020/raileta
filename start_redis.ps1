param(
  [int]$Port = 6379
)

$ErrorActionPreference = 'Stop'
$redisRoot = Join-Path $PSScriptRoot '.runtime\redis\Redis-8.10.1-Windows-x64-msys2'
$redisServer = Join-Path $redisRoot 'redis-server.exe'
$redisCli = Join-Path $redisRoot 'redis-cli.exe'
$installedCli = Join-Path ${env:ProgramFiles} 'Redis\redis-cli.exe'

# Winget's Redis.Redis package installs a persistent Windows service. Prefer it
# when present; the bundled runtime below is only a non-admin fallback.
if (Test-Path $installedCli) {
  $service = Get-Service -Name Redis -ErrorAction SilentlyContinue
  if ($service -and $service.Status -ne 'Running') { Start-Service -Name Redis }
  $pong = & $installedCli -p $Port ping
  if ($pong -ne 'PONG') { throw "Installed Redis service did not respond on port $Port." }
  Write-Host "Redis Windows service is running on localhost:$Port ($pong)" -ForegroundColor Green
  exit 0
}
$dataDir = Join-Path $PSScriptRoot 'data\redis'
$logDir = Join-Path $PSScriptRoot 'logs'

if (-not (Test-Path $redisServer)) {
  throw "Redis runtime not found at $redisServer. Install Docker Redis or place the approved Redis Windows runtime there."
}
New-Item -ItemType Directory -Path $dataDir,$logDir -Force | Out-Null
$alreadyRunning = $false
try { $alreadyRunning = (& $redisCli -p $Port ping 2>$null) -eq 'PONG' } catch { $alreadyRunning = $false }
if (-not $alreadyRunning) {
  Start-Process -FilePath $redisServer -WorkingDirectory $redisRoot -ArgumentList @('--bind', '127.0.0.1', '--port', $Port, '--dir', $dataDir, '--dbfilename', 'dump.rdb', '--appendonly', 'yes', '--logfile', (Join-Path $logDir 'redis.log')) -WindowStyle Hidden
  Start-Sleep -Seconds 2
}
$pong = & $redisCli -p $Port ping
if ($pong -ne 'PONG') { throw "Redis did not respond to ping on port $Port." }
Write-Host "Redis is running persistently on localhost:$Port ($pong)" -ForegroundColor Green
