# Start ScholarFlow FastAPI on 127.0.0.1:8100
# Phase 8.0: safely inject allowed keys from repo-root .env into this process only.
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Repo "apps\scholarflow-api"
$Harness = Join-Path $Repo "backend\packages\harness"
$VenvPython = Join-Path $Repo "backend\.venv\Scripts\python.exe"
$EnvFile = Join-Path $Repo ".env"

# Keys allowed into the API process. Never inject VITE_* secrets / frontend build vars.
$AllowedKeys = @(
  "DEEPSEEK_API_KEY",
  "SCHOLARFLOW_LLM_MODEL",
  "SCHOLARFLOW_LLM_BASE_URL",
  "SCHOLARFLOW_LLM_TIMEOUT",
  "SCHOLARFLOW_LLM_MAX_RETRIES",
  "SCHOLARFLOW_LLM_TEMPERATURE",
  "SCHOLARFLOW_CHAT_MAX_TOOL_ITERS",
  "SCHOLARFLOW_ARTIFACTS_DIR",
  "SCHOLARFLOW_TASKS_DIR",
  "SCHOLARFLOW_CONVERSATIONS_DIR",
  "SCHOLARFLOW_TASK_TIMEOUT",
  "SCHOLARFLOW_API_PORT",
  "GITHUB_TOKEN",
  "SCHOLAR_MCP_DIR",
  "SCHOLAR_HARNESS_DIR"
)

function Import-ScholarFlowEnv {
  param([string]$Path)
  if (-not (Test-Path $Path)) {
    Write-Host "No .env at $Path (LLM may be unconfigured)" -ForegroundColor Yellow
    return @()
  }
  $loaded = @()
  Get-Content -Path $Path -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or ($line -notmatch "=")) { return }
    $name, $raw = $line -split "=", 2
    $name = $name.Trim()
    if ($AllowedKeys -notcontains $name) { return }
    if ($name -match '^VITE_') {
      Write-Host "Refusing to inject frontend build var: $name" -ForegroundColor Red
      return
    }
    $val = $raw.Trim()
    if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
      $val = $val.Substring(1, $val.Length - 2)
    }
    if ([string]::IsNullOrWhiteSpace($val)) { return }
    # Do not overwrite a non-empty value already present in the shell.
    $existing = [Environment]::GetEnvironmentVariable($name, "Process")
    if (-not [string]::IsNullOrWhiteSpace($existing)) {
      $loaded += $name
      return
    }
    Set-Item -Path "Env:$name" -Value $val
    $loaded += $name
  }
  return $loaded
}

$imported = Import-ScholarFlowEnv -Path $EnvFile
if ($imported.Count -gt 0) {
  Write-Host ("Loaded env keys (names only): " + (($imported | Select-Object -Unique) -join ", ")) -ForegroundColor Cyan
}
$hasKey = -not [string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)
Write-Host ("DEEPSEEK_API_KEY configured for API process: " + $hasKey) -ForegroundColor $(if ($hasKey) { "Green" } else { "Yellow" })

$ScholarMcp = Join-Path $Repo "extensions\scholar_mcp"
if (-not [string]::IsNullOrWhiteSpace($env:SCHOLAR_MCP_DIR) -and (Test-Path $env:SCHOLAR_MCP_DIR)) {
  $ScholarMcp = $env:SCHOLAR_MCP_DIR
}

Set-Location $Api
# Api + harness + scholar_mcp: in-process adapters import scholar_mcp.clients.github;
# MCP stdio child also needs the package root (client.py prepends it again for safety).
$env:PYTHONPATH = "$Api;$Harness;$ScholarMcp"
$env:PYTHONIOENCODING = "utf-8"
Write-Host "PYTHONPATH includes scholar_mcp: $ScholarMcp" -ForegroundColor Cyan

if (Test-Path $VenvPython) {
  Write-Host "Using backend venv: $VenvPython" -ForegroundColor Cyan
  & $VenvPython -c "import fastapi,uvicorn" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing fastapi/uvicorn into backend venv..." -ForegroundColor Yellow
    & $VenvPython -m pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2"
  }
  & $VenvPython -c "import langchain_deepseek" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "langchain_deepseek missing in venv — chat LLM will report unconfigured until installed" -ForegroundColor Yellow
  }
  & $VenvPython -m scholarflow_api
} else {
  Write-Host "backend\.venv not found; using uv run from backend" -ForegroundColor Yellow
  Set-Location (Join-Path $Repo "backend")
  uv pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2"
  $env:PYTHONPATH = "$Api;$Harness;$ScholarMcp"
  uv run --directory $Api python -m scholarflow_api
}
