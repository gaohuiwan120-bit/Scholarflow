# Health check for ScholarFlow local stack (API :8100, optional Vite :5173).
# For demo-day PASS/WARN/FAIL preflight (secrets presence, scholar_mcp path, optional MCP):
#   .\scripts\preflight_scholarflow.ps1
#   .\scripts\preflight_scholarflow.ps1 -IncludeMcpProbe
$ErrorActionPreference = "Continue"
$Api = "http://127.0.0.1:8100"
$Web = "http://127.0.0.1:5173"

Write-Host "=== ScholarFlow health ===" -ForegroundColor Cyan
try {
  $h = Invoke-RestMethod -Uri "$Api/health" -TimeoutSec 5
  Write-Host "API /health: OK" -ForegroundColor Green
  Write-Host ($h | ConvertTo-Json -Compress)
  if (-not $h.langgraph_available) {
    Write-Host "WARN: langgraph_available=false" -ForegroundColor Yellow
  }
  if (-not $h.artifacts_dir_exists) {
    Write-Host "WARN: artifacts_dir_exists=false" -ForegroundColor Yellow
  }
} catch {
  Write-Host "API /health: FAIL $_" -ForegroundColor Red
  exit 1
}

try {
  $r = Invoke-WebRequest -Uri $Web -TimeoutSec 5 -UseBasicParsing
  Write-Host "Vite $Web : HTTP $($r.StatusCode)" -ForegroundColor Green
} catch {
  Write-Host "Vite $Web : not reachable (start scripts/start_scholarflow_web.ps1 if needed)" -ForegroundColor Yellow
}

Write-Host "OK" -ForegroundColor Green
