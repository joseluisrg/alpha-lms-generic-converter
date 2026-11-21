"""Versioned result contract for LMS certification runs."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

CERTIFICATION_SCHEMA_VERSION = 2


class ReportStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class CaseStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class ImportStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class FeatureOutcome(StrEnum):
    VERIFIED = "verified"
    EXPECTED_GAP = "expected_gap"
    NOT_VERIFIED = "not_verified"
    FAILED = "failed"


class EnvironmentInfo(BaseModel):
    target: str
    release: str
    patch: str
    components: dict[str, str] = Field(default_factory=dict)
    image: str | None = None
    image_digest: str | None = None


class ArtifactInfo(BaseModel):
    case_id: str
    target: str
    file_name: str
    sha256: str
    size_bytes: int


class ReimportInfo(BaseModel):
    status: ImportStatus
    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    duration_seconds: float = 0.0
    file_name: str
    sha256: str
    size_bytes: int
    log_file: str | None = None
    message: str | None = None


class ImportResult(BaseModel):
    status: ImportStatus
    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    duration_seconds: float = 0.0
    log_file: str | None = None
    message: str | None = None
    reimport: ReimportInfo | None = None


class FeatureResult(BaseModel):
    feature_id: str
    expected_status: str
    import_check: str
    evidence: str
    outcome: FeatureOutcome
    details: str | None = None


class CaseResult(BaseModel):
    case_id: str
    source: str
    target: str
    status: CaseStatus
    environment: EnvironmentInfo
    artifact: ArtifactInfo
    import_result: ImportResult
    features: list[FeatureResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ReportSummary(BaseModel):
    cases_total: int
    cases_passed: int
    cases_failed: int
    features_total: int
    features_verified: int
    features_expected_gap: int
    features_not_verified: int
    features_failed: int


class CertificationReport(BaseModel):
    schema_version: Literal[2] = 2
    matrix_version: int
    run_id: str
    generated_at: datetime
    status: ReportStatus
    cases: list[CaseResult] = Field(default_factory=list)
    summary: ReportSummary
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
