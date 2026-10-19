"""Tests for ScholarFlow MCP helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "backend" / "packages" / "harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from scholar_mcp.clients.arxiv import parse_arxiv_feed


SAMPLE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <summary>We propose the Transformer.</summary>
    <published>2017-06-12T00:00:00Z</published>
    <author><name>Alice Example</name></author>
  </entry>
</feed>
"""


def test_parse_arxiv_feed() -> None:
    papers = parse_arxiv_feed(SAMPLE_ARXIV_XML)
    assert len(papers) == 1
    assert papers[0]["identifier"] == "1706.03762v5"
    assert papers[0]["year"] == 2017


def test_generate_research_matrix_paper() -> None:
    from scholarflow.scholar.matrix import generate_paper_matrix
    from scholarflow.scholar.models import PaperEvidence

    csv_text = generate_paper_matrix(
        [
            PaperEvidence(
                evidence_id="p1",
                title="Demo",
                source_url="https://arxiv.org/abs/1",
            )
        ]
    )
    assert "evidence_id" in csv_text.splitlines()[0]


def test_validate_evidence_schema_roundtrip() -> None:
    from scholarflow.scholar.validation import validate_json_artifact

    payload = {"task_id": "t1", "title": "Title", "objective": "Obj"}
    validated = validate_json_artifact("research_plan.json", payload)
    assert validated["task_id"] == "t1"


def test_build_task_artifacts_has_nine_files() -> None:
    from scholarflow.scholar.artifacts import build_task_artifacts
    from scholarflow.scholar.models import ExperimentPlan, ResearchPlan

    artifacts = build_task_artifacts(
        ResearchPlan(task_id="t1", title="Demo", objective="Explore"),
        [],
        [],
        ExperimentPlan(objective="Validate"),
        [],
    )
    assert len(artifacts) == 9
    assert "research_report.md" in artifacts


@pytest.mark.asyncio
async def test_search_academic_papers_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    from scholar_mcp.clients import arxiv as arxiv_client

    class FakeResponse:
        text = SAMPLE_ARXIV_XML

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def get(self, url: str) -> FakeResponse:
            assert url.startswith("https://export.arxiv.org/")
            return FakeResponse()

        async def aclose(self) -> None:
            return None

    papers = await arxiv_client.search_academic_papers("transformer", client=FakeClient())  # type: ignore[arg-type]
    assert papers[0]["title"] == "Attention Is All You Need"
    assert papers[0]["evidence_id"].startswith("paper-")


def test_coerce_items_accepts_raw_list() -> None:
    from scholar_mcp.server import coerce_items, generate_research_matrix, parse_papers

    raw = [
        {
            "title": "Demo Paper",
            "source_url": "https://arxiv.org/abs/1234.5678",
            "identifier": "1234.5678",
        }
    ]
    assert len(coerce_items(raw)) == 1
    papers = parse_papers(raw)
    assert papers[0].evidence_id.startswith("paper-")
    csv_text = generate_research_matrix("paper", json.dumps(raw))
    assert "Demo Paper" in csv_text


def test_assemble_task_artifacts_autofills_evidence_id() -> None:
    from scholar_mcp.server import assemble_task_artifacts

    plan = {
        "task_id": "t1",
        "title": "Demo",
        "objective": "Explore",
    }
    papers = {
        "items": [
            {
                "title": "No Id Paper",
                "source_url": "https://arxiv.org/abs/9999.99999",
            }
        ]
    }
    repos = {
        "items": [
            {
                "repository": "org/demo",
                "source_url": "https://github.com/org/demo",
            }
        ]
    }
    experiment = {"objective": "Validate"}
    payload = json.loads(
        assemble_task_artifacts(
            json.dumps(plan),
            json.dumps(papers),
            json.dumps(repos),
            json.dumps(experiment),
        )
    )
    assert payload["artifact_count"] == 9
    assert "evidence_review.json" in payload["contents"]
    assert "sources.json" in payload["contents"]
