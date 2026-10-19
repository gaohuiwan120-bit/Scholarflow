# Stop ScholarFlow local API (8100) and Vite (5173) without touching ScholarFlow Docker.
$ErrorActionPreference = "Continue"
Write-Host "Stopping ScholarFlow listeners on 8100 / 5173 (host processes only)..." -ForegroundColor Cyan

function Stop-PortProcess([int]$Port) {
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if (-not $conns) {
    Write-Host ("  port {0}: not listening" -f $Port)
    return
  }
  $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($procId in $pids) {
    try {
      $p = Get-Process -Id $procId -ErrorAction Stop
      Write-Host ("  port {0}: stopping PID {1} ({2})" -f $Port, $procId, $p.ProcessName)
      Stop-Process -Id $procId -Force -ErrorAction Stop
    } catch {
      Write-Host ("  port {0}: skip PID {1} ({2})" -f $Port, $procId, $_) -ForegroundColor Yellow
    }
  }
}

Stop-PortProcess 8100
Stop-PortProcess 5173
Write-Host "Done. (Did not run docker compose / did not touch other containers.)" -ForegroundColor Green
