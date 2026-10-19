"""Находка и результат правила (ARCHITECTURE_CHECKS.md §1); имена классов = имена схем openapi."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Level = Literal["violation", "suspicion", "not_checked"]
Outcome = Literal["passed", "findings", "not_run", "not_checked"]
Method = Literal["style", "regex", "morph", "fuzzy", "layout", "estimate", "count"]
BlockId = Literal[
    "structure",
    "intro",
    "volume",
    "tables",
    "numbering",
    "consistency",
    "methods",
    "hypothesis",
    "wording",
    "tasks",
    "not_checked",
    "diff_impact",
]

RULE_ID_PATTERN = r"^[A-Z]{2,4}-\d{2}(\.\d+)?$"


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TableRef(ApiModel):
    number_label: str
    table_idx: int = Field(ge=1)
    row: int | None = Field(default=None, ge=1)
    col: int | None = Field(default=None, ge=1)


class Location(ApiModel):
    section_path: list[str]
    paragraph_idx: int | None = Field(default=None, ge=1)
    table: TableRef | None = None
    quote: str
    highlight: tuple[int, int] | None = None
    page: int | None = Field(default=None, ge=1)


class FindingSource(ApiModel):
    doc: Literal["M", "CH"]
    section: str


class Finding(ApiModel):
    id: str = Field(pattern=r"^[0-9a-f]{12}$")
    rule_id: str = Field(pattern=RULE_ID_PATTERN)
    title: str
    block: BlockId
    level: Level
    not_run: bool
    source: FindingSource
    message: str
    values: dict[str, Any]
    locations: list[Location]
    count: int = Field(ge=1)
    hint: str | None = None
    method: Method
    fingerprint: str
    origin: str = Field(pattern=r"^(rules|model:[a-z0-9_.-]+)$")


class RuleResult(ApiModel):
    rule_id: str = Field(pattern=RULE_ID_PATTERN)
    title: str
    block: BlockId
    outcome: Outcome
    findings: list[Finding]
    artifacts: dict[str, Any]
    skipped_reason: str | None = None


def location_to_api(loc: object) -> Location:
    """Преобразует внутренний dataclass `model.location.Location` в API-модель."""
    table = getattr(loc, "table", None)
    return Location(
        section_path=list(loc.section_path),  # type: ignore[attr-defined]
        paragraph_idx=loc.paragraph_idx,  # type: ignore[attr-defined]
        table=None
        if table is None
        else TableRef(
            number_label=table.number_label,
            table_idx=table.table_idx,
            row=table.row,
            col=table.col,
        ),
        quote=loc.quote,  # type: ignore[attr-defined]
        highlight=loc.highlight,  # type: ignore[attr-defined]
        page=loc.page,  # type: ignore[attr-defined]
    )
