"""Phase-3 artifact persistence, path safety, schema checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scholarflow_api.config import repo_root
from scholarflow_api.graph.workflow import run_research_workflow
from scholarflow_api.services import artifact_store as store

ARTIFACTS = repo_root() / "docs" / "scholar-flow" / "samples" / "rag-test-001"


@pytest.fixture()
def tasks_tmpdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "tasks"
    monkeypatch.setenv("SCHOLARFLOW_TASKS_DIR", str(root))
    return root


def test_persist_nine_artifacts_and_manifest(tasks_tmpdir: Path) -> None:
    final = run_research_workflow(
        task_id="sf-persist-001",
        question="Blended RAG hybrid dense sparse vs Naive RAG",
        workflow_mode="research_orchestration",
        artifacts_dir=str(ARTIFACTS),
        data_mode="fixture",
        persist_artifacts=True,
    )
    assert final["overall_status"] in {"succeeded", "partial_succeeded"}
    man = final.get("artifact_manifest")
    assert man is not None
    assert man["task_id"] == "sf-persist-001"
    assert man["data_mode"] == "fixture"
    assert len(man["artifacts"]) == 9

    disk = store.list_artifacts("sf-persist-001")
    assert disk is not None
    assert len(disk.artifacts) == 9
    for meta in disk.artifacts:
        path = Path(meta.path)
        assert path.is_file()
        assert path.parent == store.task_dir("sf-persist-001")
        data, media = store.read_artifact_bytes("sf-persist-001", meta.filename)
        assert len(data) > 0
        assert media

    report = (store.task_dir("sf-persist-001") / "research_report.md").read_text(encoding="utf-8")
    assert "RAG" in report or "research" in report.lower()


def test_overwrite_policy_replace(tasks_tmpdir: Path) -> None:
    contents = {name: f"v1-{name}" for name in store.REQUIRED}
    store.persist_artifacts("sf-ow-1", contents, data_mode="fixture", overwrite=True)
    store.persist_artifacts(
        "sf-ow-1",
        {name: f"v2-{name}" for name in store.REQUIRED},
        data_mode="fixture",
        overwrite=True,
    )
    text = (store.task_dir("sf-ow-1") / "research_report.md").read_text(encoding="utf-8")
    assert text.startswith("v2-")


def test_path_traversal_rejected(tasks_tmpdir: Path) -> None:
    with pytest.raises(ValueError):
        store.resolve_artifact_path("sf-safe-1", "../secrets.txt")
    with pytest.raises(ValueError):
        store.validate_task_id("../evil")
    with pytest.raises(ValueError):
        store.validate_task_id("sf/../../x")


def test_schema_invalid_json_marked(tasks_tmpdir: Path) -> None:
    bad = {name: "ok" for name in store.REQUIRED}
    bad["paper_evidence.json"] = json.dumps({"items": [{"title": "missing fields"}]})
    man = store.persist_artifacts("sf-schema-1", bad, data_mode="fixture")
    paper = next(a for a in man.artifacts if a.filename == "paper_evidence.json")
    assert paper.schema_valid is False
    assert paper.schema_error
