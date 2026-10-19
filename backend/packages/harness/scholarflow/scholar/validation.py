"""Artifact validation helpers."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from scholarflow.scholar.exceptions import ScholarValidationError
from scholarflow.scholar.models import (
    ExperimentPlan,
    PaperEvidenceCollection,
    RepositoryEvidenceCollection,
    ResearchPlan,
    ReviewFindingCollection,
    SourceCollection,
)
from scholarflow.scholar.paths import REQUIRED_ARTIFACTS


_SCHEMA_MAP: dict[str, type] = {
    "research_plan.json": ResearchPlan,
    "paper_evidence.json": PaperEvidenceCollection,
    "repository_evidence.json": RepositoryEvidenceCollection,
    "evidence_review.json": ReviewFindingCollection,
    "sources.json": SourceCollection,
}


def validate_json_artifact(filename: str, payload: dict[str, Any]) -> dict[str, Any]:
    model = _SCHEMA_MAP.get(filename)
    if model is None:
        raise ScholarValidationError(f"no JSON schema registered for {filename}")
    try:
        return model.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise ScholarValidationError(str(exc)) from exc


def required_artifact_names() -> tuple[str, ...]:
    return REQUIRED_ARTIFACTS
