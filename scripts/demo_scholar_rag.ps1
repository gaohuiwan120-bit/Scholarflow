# Interview one-click: ScholarFlow RAG
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\backend"

Write-Host "== Ensure RAG deps ==" -ForegroundColor Cyan
uv pip install fastembed chromadb rank-bm25 jieba

Write-Host "== Run demo ==" -ForegroundColor Cyan
$env:PYTHONIOENCODING = "utf-8"
# Unset lite force if present
Remove-Item Env:SCHOLAR_RAG_BACKEND -ErrorAction SilentlyContinue
uv run python ../evaluation/run_rag_demo.py @args
