"""Pydantic schemas for ScholarFlow research artifacts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

EvidenceLevel = Literal["abstract_only", "metadata_only", "full_text", "secondary_source"]
VerificationStatus = Literal["verified", "partially_verified", "unverified", "inaccessible"]
ReviewStatus = Literal[
    "supported",
    "partially_supported",
    "unsupported",
    "conflicting",
    "unverified",
]


class DateRange(BaseModel):
    start: str | None = None
    end: str | None = None


class ResearchPlan(BaseModel):
    task_id: str
    title: str
    objective: str
    research_questions: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    code_search_queries: list[str] = Field(default_factory=list)
    date_range: DateRange = Field(default_factory=DateRange)
    expected_outputs: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)


class PaperEvidence(BaseModel):
    evidence_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    identifier: str | None = None
    source_url: str
    research_problem: str = ""
    methodology: str = ""
    datasets: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_level: EvidenceLevel = "abstract_only"
    verification_status: VerificationStatus = "unverified"

    @field_validator("source_url")
    @classmethod
    def source_url_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_url must not be empty")
        return value


class RepositoryEvidence(BaseModel):
    evidence_id: str
    repository: str
    source_url: str
    description: str = ""
    language: str | None = None
    framework: list[str] = Field(default_factory=list)
    architecture_summary: str = ""
    key_modules: list[str] = Field(default_factory=list)
    installation_summary: str = ""
    reproducibility_notes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = "unverified"


class ExperimentPlan(BaseModel):
    objective: str
    hypotheses: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list)
    proposed_pipeline: list[str] = Field(default_factory=list)
    evaluation_metrics: list[str] = Field(default_factory=list)
    ablation_studies: list[str] = Field(default_factory=list)
    resource_requirements: list[str] = Field(default_factory=list)
    implementation_steps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    claim: str
    related_evidence_ids: list[str] = Field(default_factory=list)
    status: ReviewStatus
    reason: str
    recommended_action: str


class SourceRecord(BaseModel):
    evidence_id: str
    kind: Literal["paper", "repository", "upload", "web"]
    title: str
    url: str
    accessed_at: str | None = None
    verification_status: VerificationStatus = "unverified"


class PaperEvidenceCollection(BaseModel):
    items: list[PaperEvidence] = Field(default_factory=list)


class RepositoryEvidenceCollection(BaseModel):
    items: list[RepositoryEvidence] = Field(default_factory=list)


class ReviewFindingCollection(BaseModel):
    items: list[ReviewFinding] = Field(default_factory=list)


class SourceCollection(BaseModel):
    items: list[SourceRecord] = Field(default_factory=list)
