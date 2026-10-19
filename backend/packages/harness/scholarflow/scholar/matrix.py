"""Deterministic research matrix generation from evidence records."""

from __future__ import annotations

import csv
import io
from typing import Iterable

from scholarflow.scholar.models import PaperEvidence, RepositoryEvidence


PAPER_MATRIX_COLUMNS = [
    "evidence_id",
    "title",
    "year",
    "venue",
    "research_problem",
    "methodology",
    "datasets",
    "metrics",
    "key_findings",
    "limitations",
    "evidence_level",
    "verification_status",
    "source_url",
]

REPOSITORY_MATRIX_COLUMNS = [
    "evidence_id",
    "repository",
    "language",
    "framework",
    "architecture_summary",
    "key_modules",
    "installation_summary",
    "reproducibility_notes",
    "limitations",
    "verification_status",
    "source_url",
]


def _join_list(values: Iterable[str]) -> str:
    return "; ".join(v for v in values if v)


def paper_matrix_rows(items: list[PaperEvidence]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        rows.append(
            {
                "evidence_id": item.evidence_id,
                "title": item.title,
                "year": str(item.year) if item.year is not None else "",
                "venue": item.venue or "",
                "research_problem": item.research_problem,
                "methodology": item.methodology,
                "datasets": _join_list(item.datasets),
                "metrics": _join_list(item.metrics),
                "key_findings": _join_list(item.key_findings),
                "limitations": _join_list(item.limitations),
                "evidence_level": item.evidence_level,
                "verification_status": item.verification_status,
                "source_url": item.source_url,
            }
        )
    return rows


def repository_matrix_rows(items: list[RepositoryEvidence]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        rows.append(
            {
                "evidence_id": item.evidence_id,
                "repository": item.repository,
                "language": item.language or "",
                "framework": _join_list(item.framework),
                "architecture_summary": item.architecture_summary,
                "key_modules": _join_list(item.key_modules),
                "installation_summary": item.installation_summary,
                "reproducibility_notes": _join_list(item.reproducibility_notes),
                "limitations": _join_list(item.limitations),
                "verification_status": item.verification_status,
                "source_url": item.source_url,
            }
        )
    return rows


def render_csv(columns: list[str], rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in columns})
    return buffer.getvalue()


def generate_paper_matrix(items: list[PaperEvidence]) -> str:
    return render_csv(PAPER_MATRIX_COLUMNS, paper_matrix_rows(items))


def generate_repository_matrix(items: list[RepositoryEvidence]) -> str:
    return render_csv(REPOSITORY_MATRIX_COLUMNS, repository_matrix_rows(items))
