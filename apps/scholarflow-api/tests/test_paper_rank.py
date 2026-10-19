"""Unit tests for paper URL sanitize + relevance re-rank (no network)."""

from __future__ import annotations

from scholarflow_api.chat.paper_rank import (
    kind_hint_from_title,
    rerank_papers,
    sanitize_source_url,
    score_paper,
    slim_paper_for_tool,
)


def test_sanitize_strips_markdown_link() -> None:
    assert (
        sanitize_source_url("[arXiv](https://arxiv.org/abs/1234.5678)")
        == "https://arxiv.org/abs/1234.5678"
    )
    assert sanitize_source_url("https://arxiv.org/abs/1234.5678v1") == (
        "https://arxiv.org/abs/1234.5678v1"
    )


def test_weak_terms_alone_do_not_beat_phrase_match() -> None:
    query = "compressed sensing"
    strong = {
        "title": "A Survey on Compressed Sensing Theory and Algorithms",
        "abstract": "We review compressed sensing recovery guarantees.",
        "year": 2018,
    }
    weak = {
        "title": "Sparse Recovery via Nonconvex Optimization",
        "abstract": "We study sparse signal recovery without compressive sampling.",
        "year": 2020,
    }
    s_strong, sig_s = score_paper(query, strong)
    s_weak, sig_w = score_paper(query, weak)
    assert s_strong > s_weak
    assert any("phrase" in s or "strong_title" in s for s in sig_s)
    assert "penalty:weak_terms_without_strong" in sig_w or s_weak < s_strong


def test_rerank_prefers_title_match_and_preserves_url() -> None:
    papers = [
        {
            "evidence_id": "paper-a",
            "title": "Sparse Recovery for Imaging",
            "abstract": "sparse recovery methods",
            "source_url": "https://arxiv.org/abs/1111.1111",
            "year": 2021,
        },
        {
            "evidence_id": "paper-b",
            "title": "Compressed Sensing: A Tutorial",
            "abstract": "An introduction to compressed sensing.",
            "source_url": "[x](https://arxiv.org/abs/2222.2222)",
            "year": 2010,
            "authors": ["A Author"],
        },
    ]
    out = rerank_papers("compressed sensing", papers, top_k=2)
    assert out[0]["evidence_id"] == "paper-b"
    assert out[0]["source_url"] == "https://arxiv.org/abs/2222.2222"
    assert out[0]["kind_hint"] == "survey_or_review"
    slim = slim_paper_for_tool(out[0])
    assert slim["authors"] == ["A Author"]
    assert slim["abstract"]
    assert "classic" not in (slim.get("kind_hint") or "")


def test_kind_hint_only_from_real_title() -> None:
    assert kind_hint_from_title("Deep Learning for MRI") is None
    assert kind_hint_from_title("A Review of Compressed Sensing") == "survey_or_review"


def test_remote_sensing_penalized_for_compressed_sensing_query() -> None:
    query = "deep learning compressed sensing image reconstruction"
    cs = {
        "title": "High Speed Compressed Sensing Reconstruction in Dynamic Parallel MRI",
        "abstract": "compressed sensing reconstruction for MRI images",
        "year": 2018,
    }
    remote = {
        "title": "Oriented object detection in optical remote sensing images using deep learning: a survey",
        "abstract": "remote sensing imagery and deep learning detectors",
        "year": 2022,
    }
    assert score_paper(query, cs)[0] > score_paper(query, remote)[0]
    ranked = rerank_papers(query, [remote, cs], top_k=2)
    assert ranked[0]["title"].startswith("High Speed Compressed Sensing")
