"""Evidence aggregation and deduplication helpers."""

from __future__ import annotations

from scholarflow.scholar.models import PaperEvidence, RepositoryEvidence, SourceRecord


def _normalize_title(title: str) -> str:
    return " ".join(title.lower().split())


def dedupe_papers(items: list[PaperEvidence]) -> list[PaperEvidence]:
    seen: set[str] = set()
    result: list[PaperEvidence] = []
    for item in items:
        key = item.identifier or _normalize_title(item.title)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def dedupe_repositories(items: list[RepositoryEvidence]) -> list[RepositoryEvidence]:
    seen: set[str] = set()
    result: list[RepositoryEvidence] = []
    for item in items:
        key = item.repository.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def merge_sources(
    papers: list[PaperEvidence],
    repositories: list[RepositoryEvidence],
    extra: list[SourceRecord] | None = None,
) -> list[SourceRecord]:
    records: list[SourceRecord] = list(extra or [])
    seen = {r.url for r in records}
    for paper in papers:
        if paper.source_url in seen:
            continue
        records.append(
            SourceRecord(
                evidence_id=paper.evidence_id,
                kind="paper",
                title=paper.title,
                url=paper.source_url,
                verification_status=paper.verification_status,
            )
        )
        seen.add(paper.source_url)
    for repo in repositories:
        if repo.source_url in seen:
            continue
        records.append(
            SourceRecord(
                evidence_id=repo.evidence_id,
                kind="repository",
                title=repo.repository,
                url=repo.source_url,
                verification_status=repo.verification_status,
            )
        )
        seen.add(repo.source_url)
    return records
