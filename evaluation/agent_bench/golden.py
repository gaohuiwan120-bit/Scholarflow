"""Golden Answer snapshot freeze and regression compare (Phase 6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

V1_GOLDEN = Path(__file__).resolve().parent / "v1" / "golden" / "snapshot.json"


def extract_snapshot(task_results: list[dict[str, Any]]) -> dict[str, Any]:
    tasks = {}
    for r in task_results:
        tid = r["task_id"]
        fields = dict(r.get("golden_fields") or {})
        fields["expect_outcome"] = r.get("expect_outcome")
        tasks[tid] = fields
    return {"version": "agent-bench-v1", "tasks": tasks}


def save_snapshot(snapshot: dict[str, Any], path: Path | None = None) -> Path:
    out = path or V1_GOLDEN
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def load_snapshot(path: Path | None = None) -> dict[str, Any] | None:
    p = path or V1_GOLDEN
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def compare_snapshots(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    b_tasks = baseline.get("tasks") or {}
    c_tasks = candidate.get("tasks") or {}
    diffs: list[dict[str, Any]] = []
    for tid in sorted(set(b_tasks) | set(c_tasks)):
        b = b_tasks.get(tid)
        c = c_tasks.get(tid)
        if b is None:
            diffs.append({"task_id": tid, "kind": "added", "candidate": c})
            continue
        if c is None:
            diffs.append({"task_id": tid, "kind": "removed", "baseline": b})
            continue
        field_diffs = {}
        for key in sorted(set(b) | set(c)):
            if b.get(key) != c.get(key):
                field_diffs[key] = {"baseline": b.get(key), "candidate": c.get(key)}
        if field_diffs:
            diffs.append({"task_id": tid, "kind": "changed", "fields": field_diffs})
    return {
        "pass": len(diffs) == 0,
        "diff_count": len(diffs),
        "diffs": diffs,
    }
