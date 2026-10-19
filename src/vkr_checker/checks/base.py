"""Интерфейс правила и контекст проверки (ARCHITECTURE_CHECKS.md §2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol

from vkr_checker.checks.facts import Facts
from vkr_checker.model.document import CellRef, Document
from vkr_checker.model.finding import (
    BlockId,
    Finding,
    FindingSource,
    Level,
    Location,
    Method,
    RuleResult,
    location_to_api,
)
from vkr_checker.model.location import make_location
from vkr_checker.thresholds import Thresholds

PLACEHOLDER_ID = "0" * 12  # настоящий id присваивает движок после схлопывания и сортировки


class Need(str, Enum):  # noqa: UP042 - проект поддерживает Python 3.10, где нет StrEnum
    """Без чего правило не работает: движок сам ставит not_run / not_checked."""

    INTRO = "INTRO"
    CH1 = "CH1"
    CH2 = "CH2"
    SUB_2_1 = "SUB_2_1"
    CONCLUSION = "CONCLUSION"
    CH_CONCLUSIONS = "CH_CONCLUSIONS"
    TOC = "TOC"
    BIBLIOGRAPHY = "BIBLIOGRAPHY"
    APPENDICES = "APPENDICES"
    TABLES = "TABLES"
    LAYOUT = "LAYOUT"
    LAYOUT_OR_ESTIMATE = "LAYOUT_OR_ESTIMATE"


NEED_TITLES: dict[Need, str] = {
    Need.INTRO: "раздел «Введение»",
    Need.CH1: "первая глава",
    Need.CH2: "вторая глава",
    Need.SUB_2_1: "параграф 2.1",
    Need.CONCLUSION: "раздел «Заключение»",
    Need.CH_CONCLUSIONS: "выводы по главам",
    Need.TOC: "оглавление",
    Need.BIBLIOGRAPHY: "список литературы",
    Need.APPENDICES: "приложения",
    Need.TABLES: "таблицы",
    Need.LAYOUT: "вёрстка LibreOffice",
    Need.LAYOUT_OR_ESTIMATE: "основная часть для оценки объёма",
}


@dataclass(frozen=True)
class Source:
    """Откуда требование: doc M (методичка) | CH (чек-лист), section - пересказ названия."""

    doc: Literal["M", "CH"]
    section: str


class Rule(Protocol):
    id: str
    title: str
    block: BlockId
    source: Source
    default_level: Level
    needs: frozenset[Need]
    priority: Literal["must", "should", "could"]

    def run(self, ctx: CheckContext) -> RuleResult: ...


class LocationFactory:
    """Обёртка над make_location: возвращает API-модель Location."""

    def __init__(self, doc: Document) -> None:
        self._doc = doc

    def paragraph(self, idx: int, char_span: tuple[int, int] | None = None) -> Location:
        return location_to_api(make_location(self._doc, paragraph_idx=idx, char_span=char_span))

    def cell(
        self, table_idx: int, row: int, col: int, char_span: tuple[int, int] | None = None
    ) -> Location:
        ref = CellRef(table_idx, row, col)
        return location_to_api(make_location(self._doc, cell_ref=ref, char_span=char_span))


@dataclass
class CheckContext:
    doc: Document
    facts: Facts
    th: Thresholds
    loc: LocationFactory

    @classmethod
    def build(cls, doc: Document, th: Thresholds | None = None) -> CheckContext:
        from vkr_checker.thresholds import DEFAULT_THRESHOLDS

        return cls(doc, Facts(doc), th or DEFAULT_THRESHOLDS, LocationFactory(doc))


def new_finding(
    rule: Rule,
    message: str,
    *,
    fingerprint: str,
    level: Level | None = None,
    method: Method = "count",
    locations: list[Location] | None = None,
    values: dict | None = None,
    hint: str | None = None,
    count: int = 1,
) -> Finding:
    """Находка правила. `{count}` в message подставляется движком при схлопывании."""
    return Finding(
        id=PLACEHOLDER_ID,
        rule_id=rule.id,
        title=rule.title,
        block=rule.block,
        level=level or rule.default_level,
        not_run=False,
        source=FindingSource(doc=rule.source.doc, section=rule.source.section),
        message=message,
        values=values or {},
        locations=locations or [],
        count=count,
        hint=hint,
        method=method,
        fingerprint=fingerprint,
        origin="rules",
    )


def result_of(rule: Rule, findings: list[Finding], **artifacts: object) -> RuleResult:
    """RuleResult правила; outcome выставит движок по факту наличия находок."""
    return RuleResult(
        rule_id=rule.id,
        title=rule.title,
        block=rule.block,
        outcome="findings" if findings else "passed",
        findings=findings,
        artifacts=dict(artifacts),
    )
