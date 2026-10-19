# ScholarFlow demo preflight — read-only stability check before a live demo.
# Does NOT: kill processes, edit .env, start Docker/ScholarFlow/Dify, run full research_orchestration,
# or treat fixture/historical tasks as this run's results.
#
# Usage (repo root):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\preflight_scholarflow.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\preflight_scholarflow.ps1 -IncludeMcpProbe
#
# Exit code: 0 = no FAIL; 1 = one or more FAIL.

[CmdletBinding()]
param(
  [switch]$IncludeMcpProbe,
  [int]$HttpTimeoutSec = 5,
  [int]$McpTimeoutSec = 25
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
$ApiBase = "http://127.0.0.1:8100"
$WebBase = "http://127.0.0.1:5173"
$EnvFile = Join-Path $Repo ".env"
$StartApi = Join-Path $Repo "scripts\start_scholarflow_api.ps1"
$StartWeb = Join-Path $Repo "scripts\start_scholarflow_web.ps1"
$HealthScript = Join-Path $Repo "scripts\health_scholarflow.ps1"
$VenvPython = Join-Path $Repo "backend\.venv\Scripts\python.exe"
$ScholarMcpDir = Join-Path $Repo "extensions\scholar_mcp"

$script:FailCount = 0
$script:WarnCount = 0
$script:PassCount = 0
$Results = New-Object System.Collections.Generic.List[object]

function Write-Check {
  param(
    [string]$Name,
    [ValidateSet("PASS", "WARN", "FAIL")][string]$Status,
    [string]$Reason,
    [string]$Next = ""
  )
  $color = switch ($Status) {
    "PASS" { "Green" }
    "WARN" { "Yellow" }
    "FAIL" { "Red" }
  }
  Write-Host ("[{0}] {1}" -f $Status, $Name) -ForegroundColor $color
  Write-Host ("       reason: {0}" -f $Reason)
  if ($Next) {
    Write-Host ("       next:   {0}" -f $Next) -ForegroundColor DarkGray
  }
  $Results.Add([pscustomobject]@{ name = $Name; status = $Status; reason = $Reason; next = $Next }) | Out-Null
  switch ($Status) {
    "PASS" { $script:PassCount++ }
    "WARN" { $script:WarnCount++ }
    "FAIL" { $script:FailCount++ }
  }
}

function Test-EnvKeyConfigured {
  # Returns $true / $false only. Never returns or prints the value.
  param([string]$KeyName, [string]$Path)
  if (-not (Test-Path $Path)) { return $false }
  $found = $false
  Get-Content -Path $Path -Encoding UTF8 -ErrorAction SilentlyContinue | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or ($line -notmatch "=")) { return }
    $name, $raw = $line -split "=", 2
    if ($name.Trim() -ne $KeyName) { return }
    $val = $raw.Trim()
    if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
      $val = $val.Substring(1, $val.Length - 2)
    }
    if ([string]::IsNullOrWhiteSpace($val)) { return }
    if ($val.StartsWith("your-") -or $val -eq "`$$KeyName" -or $val -in @("changeme", "REPLACE_ME", "x", "token")) { return }
    $found = $true
  }
  # Process env also counts (already injected) — presence only.
  $proc = [Environment]::GetEnvironmentVariable($KeyName, "Process")
  if (-not [string]::IsNullOrWhiteSpace($proc)) {
    if (-not ($proc.StartsWith("your-") -or $proc -eq "`$$KeyName")) { $found = $true }
  }
  return $found
}

function Test-PortListening {
  param([int]$Port)
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  return [bool]$conns
}

Write-Host "=== ScholarFlow demo preflight ===" -ForegroundColor Cyan
Write-Host "Repo: $Repo"
Write-Host "Mode: read-only checks (no kill / no Docker / no full live workflow)"
Write-Host ""

# --- 0. Scripts present ---
if ((Test-Path $StartApi) -and (Test-Path $StartWeb) -and (Test-Path $HealthScript)) {
  Write-Check -Name "startup_scripts_present" -Status "PASS" `
    -Reason "Found start_scholarflow_api.ps1, start_scholarflow_web.ps1, health_scholarflow.ps1" `
    -Next "Use those scripts to start the stack; this preflight only checks readiness."
} else {
  Write-Check -Name "startup_scripts_present" -Status "FAIL" `
    -Reason "One or more expected scripts missing under scripts/" `
    -Next "Restore scripts from the repo; do not invent alternate Docker launches on 8GB hosts."
}

# --- 1. Start script includes scholar_mcp ---
if (Test-Path $StartApi) {
  $apiScript = Get-Content -Path $StartApi -Raw -ErrorAction SilentlyContinue
  $hasMcpPath = ($apiScript -match 'scholar_mcp') -and ($apiScript -match 'PYTHONPATH')
  $mcpDirOk = Test-Path $ScholarMcpDir
  if ($hasMcpPath -and $mcpDirOk) {
    Write-Check -Name "start_script_scholar_mcp_path" -Status "PASS" `
      -Reason "start_scholarflow_api.ps1 references scholar_mcp on PYTHONPATH; extensions\scholar_mcp exists" `
      -Next "Always start API via scripts\start_scholarflow_api.ps1 so in-process GitHub search works."
  } elseif (-not $mcpDirOk) {
    Write-Check -Name "start_script_scholar_mcp_path" -Status "FAIL" `
      -Reason "extensions\scholar_mcp directory missing" `
      -Next "Restore the scholar_mcp package; MCP tools and adapters depend on it."
  } else {
    Write-Check -Name "start_script_scholar_mcp_path" -Status "FAIL" `
      -Reason "start_scholarflow_api.ps1 does not appear to put scholar_mcp on PYTHONPATH" `
      -Next "Update the start script so PYTHONPATH includes extensions\scholar_mcp (required for live repo search)."
  }
}

# --- 2. API port ---
if (Test-PortListening -Port 8100) {
  Write-Check -Name "api_port_8100" -Status "PASS" `
    -Reason "TCP 8100 is listening" `
    -Next ""
} else {
  Write-Check -Name "api_port_8100" -Status "FAIL" `
    -Reason "Nothing listening on 127.0.0.1:8100" `
    -Next "Run: powershell -File .\scripts\start_scholarflow_api.ps1"
}

# --- 3. GET /health ---
$health = $null
try {
  $health = Invoke-RestMethod -Uri "$ApiBase/health" -TimeoutSec $HttpTimeoutSec
  if ($health.status -eq "ok") {
    Write-Check -Name "api_health" -Status "PASS" `
      -Reason "GET /health returned status=ok (service=$($health.service))" `
      -Next ""
  } else {
    Write-Check -Name "api_health" -Status "FAIL" `
      -Reason "GET /health responded but status!=ok" `
      -Next "Inspect API logs; restart with start_scholarflow_api.ps1"
  }
  if (-not $health.langgraph_available) {
    Write-Check -Name "api_langgraph" -Status "WARN" `
      -Reason "langgraph_available=false — research_orchestration may be unavailable" `
      -Next "Install langgraph into backend\.venv before demoing full workflows."
  } else {
    Write-Check -Name "api_langgraph" -Status "PASS" `
      -Reason "langgraph_available=true" `
      -Next ""
  }
} catch {
  Write-Check -Name "api_health" -Status "FAIL" `
    -Reason "GET /health failed: local API unreachable or timed out ($HttpTimeoutSec s)" `
    -Next "This is a LOCAL service fault. Start API: .\scripts\start_scholarflow_api.ps1 (do not confuse with GitHub/arXiv outages)."
}

# --- 4. Frontend ---
if (Test-PortListening -Port 5173) {
  try {
    $wr = Invoke-WebRequest -Uri $WebBase -TimeoutSec $HttpTimeoutSec -UseBasicParsing
    if ($wr.StatusCode -ge 200 -and $wr.StatusCode -lt 400) {
      Write-Check -Name "web_http_5173" -Status "PASS" `
        -Reason "Vite responded HTTP $($wr.StatusCode) at $WebBase" `
        -Next "Open http://127.0.0.1:5173 for the demo UI."
    } else {
      Write-Check -Name "web_http_5173" -Status "WARN" `
        -Reason "Port 5173 listening but HTTP status=$($wr.StatusCode)" `
        -Next "Restart web: .\scripts\start_scholarflow_web.ps1"
    }
  } catch {
    Write-Check -Name "web_http_5173" -Status "WARN" `
      -Reason "Port 5173 listening but HTTP request failed" `
      -Next "Restart web: .\scripts\start_scholarflow_web.ps1"
  }
} else {
  Write-Check -Name "web_http_5173" -Status "WARN" `
    -Reason "Frontend not reachable on 5173 (optional if demoing API-only)" `
    -Next "For UI demo run: .\scripts\start_scholarflow_web.ps1"
}

# --- 5. Model config (from /health + key presence only) ---
$deepseekConfigured = Test-EnvKeyConfigured -KeyName "DEEPSEEK_API_KEY" -Path $EnvFile
if ($null -ne $health) {
  if ($health.llm_configured -eq $true) {
    Write-Check -Name "llm_configured" -Status "PASS" `
      -Reason "API reports llm_configured=true (DeepSeek cloud path ready)" `
      -Next "Chat/LLM demo OK; still avoid burning quota with unnecessary full workflows."
  } else {
    Write-Check -Name "llm_configured" -Status "WARN" `
      -Reason "API reports llm_configured=false — chat/LLM features may fail" `
      -Next "Set DEEPSEEK_API_KEY in repo-root .env (never commit), then restart API via start script."
  }
} elseif ($deepseekConfigured) {
  Write-Check -Name "llm_configured" -Status "WARN" `
    -Reason "DEEPSEEK_API_KEY is configured in .env, but API health unreachable so runtime LLM status unknown" `
    -Next "Start API first; health.llm_configured is the authoritative runtime signal."
} else {
  Write-Check -Name "llm_configured" -Status "WARN" `
    -Reason "DEEPSEEK_API_KEY not configured (presence check only)" `
    -Next "Add key to .env for chat demos; research MCP paths may still work without LLM."
}

Write-Check -Name "deepseek_key_presence" -Status $(if ($deepseekConfigured) { "PASS" } else { "WARN" }) `
  -Reason $(if ($deepseekConfigured) { "DEEPSEEK_API_KEY: configured" } else { "DEEPSEEK_API_KEY: not configured" }) `
  -Next $(if ($deepseekConfigured) { "" } else { "Configure in .env; preflight never prints secret values." })

# --- 6. GitHub token presence only ---
$ghConfigured = Test-EnvKeyConfigured -KeyName "GITHUB_TOKEN" -Path $EnvFile
Write-Check -Name "github_token_presence" -Status $(if ($ghConfigured) { "PASS" } else { "WARN" }) `
  -Reason $(if ($ghConfigured) { "GITHUB_TOKEN: configured" } else { "GITHUB_TOKEN: not configured" }) `
  -Next $(if ($ghConfigured) {
      "Live GitHub search uses authenticated quota when API inherits .env via start script."
    } else {
      "Without a valid token, public unauthenticated GitHub limits (60/h) can break live repo demos."
    })

# --- 7. Optional light MCP probe (external) ---
if (-not $IncludeMcpProbe) {
  Write-Check -Name "github_mcp_probe" -Status "WARN" `
    -Reason "Skipped (default). Optional probe not run; avoids consuming GitHub/MCP quota." `
    -Next "Demo-day optional: re-run with -IncludeMcpProbe (timeout ${McpTimeoutSec}s). Does NOT run full research_orchestration."
} elseif (-not (Test-Path $VenvPython)) {
  Write-Check -Name "github_mcp_probe" -Status "WARN" `
    -Reason "backend\.venv python missing; cannot run MCP probe" `
    -Next "Create backend venv / uv sync before enabling -IncludeMcpProbe."
} elseif (-not (Test-PortListening -Port 8100)) {
  Write-Check -Name "github_mcp_probe" -Status "FAIL" `
    -Reason "MCP probe requested but local API port 8100 is down" `
    -Next "LOCAL fault: start API first. Do not attribute this to GitHub outage."
} else {
  $probeFile = Join-Path $env:TEMP "scholarflow_preflight_mcp_probe.py"
  $outFile = Join-Path $env:TEMP "scholarflow_preflight_mcp.txt"
  $errFile = Join-Path $env:TEMP "scholarflow_preflight_mcp_err.txt"
  $probePyBody = @"
import asyncio, json, sys
from scholarflow_api.mcp.client import ScholarMcpClient

async def main():
    timeout = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    client = ScholarMcpClient(timeout_seconds=timeout)
    raw = await client.call_tool(
        "get_repository_overview",
        {"repository": "jianzhangcs/ISTA-Net-PyTorch"},
    )
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict) or not data.get("repository"):
        raise SystemExit("unexpected_payload")
    print("MCP_PROBE_OK")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        # Never print secrets; short class+message only.
        msg = str(exc)
        for needle in ("Bearer ", "ghp_", "github_pat_"):
            if needle.lower() in msg.lower():
                msg = type(exc).__name__
                break
        print(f"MCP_PROBE_ERR {type(exc).__name__}: {msg[:240]}", file=sys.stderr)
        raise
"@
  # Avoid UTF-8 BOM (Windows PowerShell 5 Set-Content -Encoding UTF8 adds BOM and breaks Python).
  $probeUtf8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($probeFile, $probePyBody, $probeUtf8)

  $env:PYTHONPATH = "$(Join-Path $Repo 'apps\scholarflow-api');$(Join-Path $Repo 'backend\packages\harness');$ScholarMcpDir"
  $env:PYTHONIOENCODING = "utf-8"
  # Inherit GITHUB_TOKEN into this probe process only if present in .env — never print it.
  if ($ghConfigured -and [string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
    Get-Content -Path $EnvFile -Encoding UTF8 | ForEach-Object {
      $line = $_.Trim()
      if ($line -match '^\s*GITHUB_TOKEN\s*=\s*(.+)$') {
        $val = $Matches[1].Trim().Trim('"').Trim("'")
        if ($val -and -not $val.StartsWith("your-")) {
          Set-Item -Path "Env:GITHUB_TOKEN" -Value $val
        }
      }
    }
  }
  Remove-Item $outFile, $errFile -ErrorAction SilentlyContinue
  Push-Location (Join-Path $Repo "apps\scholarflow-api")
  try {
    # Use a background job so we can enforce timeout without Start-Process redirect quirks on Windows.
    $job = Start-Job -ScriptBlock {
      param($Py, $Probe, $TimeoutSec, $PythonPath, $WorkDir, $Token)
      Set-Location $WorkDir
      $env:PYTHONPATH = $PythonPath
      $env:PYTHONIOENCODING = "utf-8"
      if ($Token) { $env:GITHUB_TOKEN = $Token }
      $out = & $Py -u $Probe $TimeoutSec 2>&1 | Out-String
      return @{ exitCode = $LASTEXITCODE; output = $out }
    } -ArgumentList @(
      $VenvPython,
      $probeFile,
      $McpTimeoutSec,
      $env:PYTHONPATH,
      (Join-Path $Repo "apps\scholarflow-api"),
      $env:GITHUB_TOKEN
    )
    $done = Wait-Job -Job $job -Timeout ($McpTimeoutSec + 8)
    if (-not $done) {
      Stop-Job $job -ErrorAction SilentlyContinue
      Remove-Job $job -Force -ErrorAction SilentlyContinue
      Write-Check -Name "github_mcp_probe" -Status "WARN" `
        -Reason "MCP probe timed out after ${McpTimeoutSec}s — likely EXTERNAL GitHub/network slowdown, not necessarily local API crash" `
        -Next "Retry later or demo with cached narrative; do not mark fixture data as live."
    } else {
      $payload = Receive-Job $job -ErrorAction SilentlyContinue
      Remove-Job $job -Force -ErrorAction SilentlyContinue
      $combined = ""
      $code = 1
      if ($payload -is [hashtable]) {
        $combined = [string]$payload.output
        $code = [int]$payload.exitCode
      } else {
        $combined = ($payload | Out-String)
      }
      $combined = [regex]::Replace($combined, '(?i)(bearer\s+)\S+', '$1***')
      $combined = [regex]::Replace($combined, '(?i)(ghp_|github_pat_)[A-Za-z0-9_]+', '$1***')
      if ($code -eq 0 -and $combined -match "MCP_PROBE_OK") {
        Write-Check -Name "github_mcp_probe" -Status "PASS" `
          -Reason "Lightweight MCP get_repository_overview succeeded within timeout" `
          -Next "External GitHub path OK for demo. Still do not auto-run full live orchestration from preflight."
      } else {
        $hint = "EXTERNAL or MCP-tool failure"
        $low = $combined.ToLowerInvariant()
        if ($low -match "connection|timeout|timed out|network|tls|ssl|getaddrinfo") {
          $hint = "EXTERNAL network/DNS/TLS toward GitHub (local API may still be fine)"
        } elseif ($low -match "401|bad credentials|unauthorized") {
          $hint = "EXTERNAL auth: GitHub token rejected (401) — update .env GITHUB_TOKEN"
        } elseif ($low -match "403|rate limit|429") {
          $hint = "EXTERNAL rate limit (403/429) — wait or use a valid authenticated token"
        } elseif ($low -match "no module named|scholar_mcp") {
          $hint = "LOCAL import/path issue for scholar_mcp — use start_scholarflow_api.ps1"
        }
        Write-Check -Name "github_mcp_probe" -Status "WARN" `
          -Reason ("MCP probe failed. Classification: {0}" -f $hint) `
          -Next "Fix LOCAL path/API first if import errors; otherwise treat as external GitHub issue. Do not fall back to fixture and call it live."
      }
    }
  } catch {
    Write-Check -Name "github_mcp_probe" -Status "WARN" `
      -Reason "MCP probe could not start (local launcher issue)" `
      -Next "Check backend\.venv; distinguish launcher errors (local) from GitHub HTTP errors (external)."
  } finally {
    Pop-Location
    if (Test-Path Env:GITHUB_TOKEN) { Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue }
    Remove-Item $probeFile, $outFile, $errFile -ErrorAction SilentlyContinue
  }
}

# --- Summary ---
Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ("PASS={0}  WARN={1}  FAIL={2}" -f $script:PassCount, $script:WarnCount, $script:FailCount)
Write-Host "Legend: PASS=ready  WARN=demo possible with caveats  FAIL=fix before demo"
Write-Host "This preflight does NOT execute research_orchestration and does NOT validate historical task outputs."
Write-Host ""

if ($script:FailCount -gt 0) {
  Write-Host "Result: NOT READY (one or more FAIL)" -ForegroundColor Red
  Write-Host "Suggested order: start API -> start web -> re-run preflight -> optional -IncludeMcpProbe"
  exit 1
}

if ($script:WarnCount -gt 0) {
  Write-Host "Result: READY WITH WARNINGS" -ForegroundColor Yellow
  Write-Host "Review WARN items above before presenting live GitHub/LLM features."
  exit 0
}

Write-Host "Result: READY" -ForegroundColor Green
exit 0
