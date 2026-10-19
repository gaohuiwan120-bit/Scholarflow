#!/usr/bin/env bash
# ScholarFlow verification script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

echo "=== ScholarFlow Verification ==="

# Health
if curl -sf http://localhost:2026/health >/dev/null 2>&1; then
  pass "ScholarFlow health (http://localhost:2026/health)"
else
  fail "ScholarFlow not reachable — run: ./scripts/docker.sh start"
fi

# Schema + evaluation tests
cd "$ROOT/backend"
uv run pytest tests/test_scholar_schemas.py tests/test_evaluation_scorer.py -q
pass "Schema + evaluation unit tests"

# MCP tests
cd "$ROOT/extensions/scholar_mcp"
uv sync --group dev >/dev/null 2>&1
uv run pytest -q
pass "MCP unit tests"

# Offline evaluation (fixture)
uv run python ../evaluation/run_eval.py >/dev/null
pass "Offline evaluation (20 tasks)"

# E2E benchmark (golden)
uv run python ../evaluation/run_benchmark.py --mode golden >/dev/null
pass "E2E benchmark golden (10 tasks)"

# Docker mounts
if docker ps --format '{{.Names}}' | grep -q '^scholarflow-gateway$'; then
  docker exec scholarflow-gateway test -d /app/skills/custom/scientific-research-orchestration
  pass "Custom skills mounted in gateway container"
  docker exec scholarflow-gateway test -d /app/project/extensions/scholar_mcp
  pass "scholar_mcp mounted in gateway container"
fi

# API key reminder
if grep -q 'DEEPSEEK_API_KEY=your-deepseek-api-key' "$ROOT/.env" 2>/dev/null; then
  echo -e "${RED}[WARN]${NC} DEEPSEEK_API_KEY is still placeholder — set a real key for E2E chat"
else
  pass "DEEPSEEK_API_KEY appears configured"
fi

echo "=== All automated checks passed ==="
