"""Pydantic-схемы отчёта: CheckReport, CompareReport (ARCHITECTURE_CHECKS.md §7-§8)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from vkr_checker.model.finding import (
    RULE_ID_PATTERN,
    ApiModel,
    BlockId,
    Finding,
    Location,
    RuleResult,
)

SCHEMA_VERSION = "1.0"


class FileInfo(ApiModel):
    name: str = Field(max_length=200)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LayoutInfo(ApiModel):
    status: Literal["ok", "partial", "failed"]
    engine: str | None = None
    page_count: int | None = None
    coverage: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None
    font_substitutions: list[str] = Field(default_factory=list)
    disclaimer: str


class VolumeSection(ApiModel):
    title: str
    pages: float


class VolumeInfo(ApiModel):
    method: Literal["layout", "estimate"]
    pages_main: float | None = None
    by_section: list[VolumeSection]
    estimate_formula: str | None = None


class StructureNode(ApiModel):
    title: str
    kind: Literal[
        "TITLE", "TOC", "INTRO", "CHAPTER", "SUBSECTION", "CHAPTER_CONCLUSIONS",
        "CONCLUSION", "BIBLIOGRAPHY", "APPENDIX", "UNKNOWN",
    ]  # fmt: skip
    number: str | None = None
    detection: Literal["style", "pattern", "heuristic"]
    confidence: float = Field(ge=0, le=1)
    paragraph_idx: int | None = None
    children: list[StructureNode]


class Summary(ApiModel):
    violation: int = Field(ge=0)
    suspicion: int = Field(ge=0)
    not_checked: int = Field(ge=0)
    not_run: int = Field(ge=0)
    passed_rules: list[str]
    noise_warning: str | None = None


class ReportBlock(ApiModel):
    id: BlockId
    title: str
    rule_results: list[RuleResult]


class NcItem(ApiModel):
    id: str = Field(pattern=r"^NC-01\.\d+$")
    title: str
    source: str
    hint: str | None = None
    helper: str | None = None


class MatrixCell(ApiModel):
    status: Literal["auto", "gap", "n/a"]
    text: str
    candidates: list[str] = Field(max_length=3)
    locations: list[Location]


class MatrixCells(ApiModel):
    theory: MatrixCell
    instrument: MatrixCell
    calculation: MatrixCell
    result: MatrixCell
    conclusion: MatrixCell


class MatrixRow(ApiModel):
    kind: Literal["hypothesis_part", "defense_position", "task"]
    label: str
    statement: str
    statement_loc: Location | None = None
    is_theoretical: bool
    cells: MatrixCells


class MatrixStats(ApiModel):
    rows: int
    gaps: int
    auto_cells: int
    warnings: list[str]


class Matrix(ApiModel):
    rows: list[MatrixRow]
    stats: MatrixStats


class CheckReport(ApiModel):
    schema_version: Literal["1.0"]
    service_version: str
    checked_at: datetime
    file: FileInfo
    layout: LayoutInfo
    volume: VolumeInfo
    structure: list[StructureNode]
    summary: Summary
    blocks: list[ReportBlock]
    not_checked: list[NcItem]
    matrix: Matrix
    warnings: list[str]


class Segment(ApiModel):
    op: Literal["equal", "ins", "del"]
    text: str


class ParagraphDiff(ApiModel):
    status: Literal["unchanged", "modified", "inserted", "deleted", "moved_out", "moved_in"]
    old_idx: int | None = None
    new_idx: int | None = None
    text: str | None = None
    segments: list[Segment] = Field(default_factory=list)
    move_id: str | None = None


class SectionDiff(ApiModel):
    status: Literal["unchanged", "modified", "renamed", "added", "removed"]
    rename_basis: Literal["title", "content"] | None = None
    old_title: str | None = None
    new_title: str | None = None
    paragraphs: list[ParagraphDiff]


class Move(ApiModel):
    id: str
    from_section: str
    to_section: str
    old_idx: list[int]
    new_idx: list[int]
    segments: list[Segment]


class NumberChange(ApiModel):
    old: str
    new: str
    kind: str | None = None
    context: str
    loc_old: Location | None = None
    loc_new: Location | None = None


class CellChange(ApiModel):
    col: int = Field(ge=1)
    old: str
    new: str


class RowChange(ApiModel):
    status: Literal["added", "removed", "modified"]
    old_row: int | None = None
    new_row: int | None = None
    cells: list[CellChange] = Field(default_factory=list)


class ObjectDiff(ApiModel):
    """Таблица или рисунок; у рисунков rows всегда пуст."""

    status: Literal["unchanged", "modified", "added", "removed"]
    flags: list[Literal["renumbered", "retitled"]]
    old_label: str | None = None
    new_label: str | None = None
    rows: list[RowChange]


class DynamicsItem(ApiModel):
    fingerprint: str
    rule_id: str = Field(pattern=RULE_ID_PATTERN)
    title: str
    message: str
    count_old: int | None = None
    count_new: int | None = None
    trend: Literal["less", "more", "same"] | None = None


class Dynamics(ApiModel):
    fixed: list[DynamicsItem]
    new: list[DynamicsItem]
    remaining: list[DynamicsItem]


class DiffReport(ApiModel):
    sections: list[SectionDiff]
    moves: list[Move]
    number_changes: list[NumberChange]
    tables: list[ObjectDiff]
    figures: list[ObjectDiff]
    impact: list[Finding]
    dynamics: Dynamics


class CompareOld(ApiModel):
    file: FileInfo
    layout: LayoutInfo
    summary: Summary


class CompareReport(ApiModel):
    schema_version: Literal["1.0"]
    service_version: str
    checked_at: datetime
    old: CompareOld
    new: CheckReport
    diff: DiffReport


class MatrixExportRequest(ApiModel):
    file_name: str = Field(max_length=200)
    service_version: str | None = None
    checked_at: datetime | None = None
    matrix: Matrix


class ReportExportRequest(ApiModel):
    """Тело POST /api/export/report.docx: ровно один из отчётов."""

    check: CheckReport | None = None
    compare: CompareReport | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> ReportExportRequest:
        if (self.check is None) == (self.compare is None):
            raise ValueError("нужен ровно один из check или compare")
        return self


class Limits(ApiModel):
    max_upload_mb: int
    check_timeout_s: int
    compare_timeout_s: int


class Health(ApiModel):
    status: Literal["ok"]
    service_version: str
    mode: Literal["local", "server"]
    auth_required: bool
    authenticated: bool | None = None
    layout_available: bool
    layout_engine: str | None = None
    limits: Limits


class LoginRequest(ApiModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=256)


ERROR_CODES = Literal[
    "bad_request", "missing_file", "auth_required", "invalid_password", "file_too_large",
    "unsupported_format", "invalid_docx", "docx_limits_exceeded", "validation_error",
    "too_many_attempts", "server_busy", "processing_timeout", "internal_error",
]  # fmt: skip


class ErrorBody(ApiModel):
    code: ERROR_CODES
    message: str
    field: str | None = None
    request_id: str | None = None


class ErrorResponse(ApiModel):
    error: ErrorBody
