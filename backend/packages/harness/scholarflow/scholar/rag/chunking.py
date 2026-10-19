"""Chunk ScholarFlow artifacts into retrievable evidence passages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class EvidenceChunk:
    chunk_id: str
    evidence_id: str
    kind: str  # paper | repository | report | review | plan | experiment
    title: str
    text: str
    source_url: str
    verification_status: str
    task_id: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clip(text: str, limit: int = 1800) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def load_chunks_from_artifacts_dir(artifacts_dir: Path, task_id: str | None = None) -> list[EvidenceChunk]:
    """Build chunks from a ScholarFlow 9-artifact directory."""
    root = Path(artifacts_dir)
    task = task_id or root.name
    chunks: list[EvidenceChunk] = []

    papers_path = root / "paper_evidence.json"
    if papers_path.exists():
        payload = json.loads(papers_path.read_text(encoding="utf-8"))
        for i, item in enumerate(payload.get("items", [])):
            eid = str(item.get("evidence_id") or f"paper-{i}")
            parts = [
                item.get("title") or "",
                item.get("research_problem") or "",
                item.get("methodology") or "",
                " ".join(item.get("key_findings") or []),
                " ".join(item.get("limitations") or []),
            ]
            chunks.append(
                EvidenceChunk(
                    chunk_id=f"{eid}::main",
                    evidence_id=eid,
                    kind="paper",
                    title=str(item.get("title") or eid),
                    text=_clip(" | ".join(p for p in parts if p)),
                    source_url=str(item.get("source_url") or ""),
                    verification_status=str(item.get("verification_status") or "unverified"),
                    task_id=task,
                    metadata={"year": item.get("year"), "identifier": item.get("identifier")},
                )
            )

    repos_path = root / "repository_evidence.json"
    if repos_path.exists():
        payload = json.loads(repos_path.read_text(encoding="utf-8"))
        for i, item in enumerate(payload.get("items", [])):
            eid = str(item.get("evidence_id") or f"repo-{i}")
            parts = [
                item.get("repository") or "",
                item.get("description") or "",
                item.get("architecture_summary") or "",
                " ".join(item.get("key_modules") or []),
            ]
            chunks.append(
                EvidenceChunk(
                    chunk_id=f"{eid}::main",
                    evidence_id=eid,
                    kind="repository",
                    title=str(item.get("repository") or eid),
                    text=_clip(" | ".join(p for p in parts if p)),
                    source_url=str(item.get("source_url") or ""),
                    verification_status=str(item.get("verification_status") or "unverified"),
                    task_id=task,
                    metadata={"language": item.get("language")},
                )
            )

    sources_path = root / "sources.json"
    if sources_path.exists():
        payload = json.loads(sources_path.read_text(encoding="utf-8"))
        items = payload.get("items") or payload.get("sources") or []
        for i, item in enumerate(items):
            eid = str(item.get("evidence_id") or f"source-{i}")
            if any(c.evidence_id == eid for c in chunks):
                continue
            chunks.append(
                EvidenceChunk(
                    chunk_id=f"{eid}::source",
                    evidence_id=eid,
                    kind=str(item.get("kind") or "paper"),
                    title=str(item.get("title") or eid),
                    text=_clip(str(item.get("title") or "")),
                    source_url=str(item.get("url") or item.get("source_url") or ""),
                    verification_status=str(item.get("verification_status") or "unverified"),
                    task_id=task,
                    metadata={},
                )
            )

    for name, kind in (
        ("research_report.md", "report"),
        ("experiment_plan.md", "experiment"),
        ("research_plan.json", "plan"),
        ("evidence_review.json", "review"),
    ):
        path = root / name
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8")
        if name.endswith(".json"):
            try:
                raw = json.dumps(json.loads(raw), ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        # Split long markdown into ~1200 char windows
        step = 1200
        for i in range(0, max(len(raw), 1), step):
            piece = raw[i : i + step].strip()
            if len(piece) < 40:
                continue
            chunks.append(
                EvidenceChunk(
                    chunk_id=f"{kind}-{task}::{i}",
                    evidence_id=f"{kind}-{task}",
                    kind=kind,
                    title=f"{kind}:{task}",
                    text=_clip(piece, 1500),
                    source_url="",
                    verification_status="verified",
                    task_id=task,
                    metadata={"artifact": name, "offset": i},
                )
            )

    return chunks
