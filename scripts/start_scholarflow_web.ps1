# Start ScholarFlow Phase-1 Vite web on 127.0.0.1:5173
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Web = Join-Path $Repo "apps\scholarflow-web"
Set-Location $Web
if (-not (Test-Path "node_modules")) {
  Write-Host "npm install..." -ForegroundColor Cyan
  npm install
}
npm run dev
