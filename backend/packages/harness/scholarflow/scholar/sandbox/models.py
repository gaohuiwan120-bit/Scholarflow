"""Sandbox I/O contracts for ScholarFlow."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SandboxStatus = Literal[
    "succeeded",
    "failed",
    "timed_out",
    "rejected",
    "resource_exhausted",
]

SandboxBackend = Literal["process_jail", "docker", "unavailable"]


class SandboxRequest(BaseModel):
    task_id: str = Field(..., min_length=2, max_length=80)
    code: str = Field(..., min_length=1, max_length=200_000)
    language: Literal["python"] = "python"
    timeout_seconds: float = Field(default=8.0, ge=0.5, le=60.0)
    memory_mb: int = Field(default=256, ge=64, le=1024)
    max_output_bytes: int = Field(default=64_000, ge=1024, le=2_000_000)
    allow_network: bool = False
    prefer_docker: bool = True
    filename: str = "main.py"


class SandboxResult(BaseModel):
    task_id: str
    status: SandboxStatus
    backend: SandboxBackend
    exit_code: int | None = None
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    error_summary: str | None = None
    work_dir: str | None = None
    limits: dict[str, Any] = Field(default_factory=dict)
    security_notes: list[str] = Field(default_factory=list)
