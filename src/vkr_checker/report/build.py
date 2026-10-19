"""Сборка CheckReport из результатов правил (ARCHITECTURE_CHECKS.md §8).

Готовые части (file, layout, volume, matrix) приходят снаружи: их строят конвейер (B-23),
volume.py и матрица. Здесь - блоки в порядке SPEC §3.4, сводка, noise_warning и NC-01.
"""

from __future__ import annotations

from datetime import datetime

from vkr_checker.checks.engine import BLOCK_ORDER
from vkr_checker.checks.not_checked import nc_items
from vkr_checker.model.document import Document, Section
from vkr_checker.model.finding import RuleResult
from vkr_checker.report.schema import (
    SCHEMA_VERSION,
    CheckReport,
    FileInfo,
    LayoutInfo,
    Matrix,
    ReportBlock,
    StructureNode,
    Summary,
    VolumeInfo,
)
from vkr_checker.thresholds import DEFAULT_THRESHOLDS, Thresholds

BLOCK_TITLES: dict[str, str] = {
    "structure": "Структура",
    "intro": "Введение",
    "volume": "Объём",
    "tables": "Таблицы (оформление)",
    "numbering": "Нумерация и ссылки",
    "consistency": "Согласованность цифр",
    "methods": "Методы и методики",
    "hypothesis": "Гипотеза",
    "wording": "Формулировки",
    "tasks": "Задачи и выводы",
    "not_checked": "Не проверяется кодом",
    "diff_impact": "Влияние изменений",
}
NOISE_TEXT = (
    "Много подозрений ({n} при бюджете {budget}): проверьте блок «Распознанная структура»; "
    "пороги требуют калибровки на корпусе."
)


def build_blocks(results: list[RuleResult]) -> list[ReportBlock]:
    """Непустые блоки в порядке отчёта; внутри блока результаты идут по rule_id."""
    by_block: dict[str, list[RuleResult]] = {}
    for r in sorted(results, key=lambda r: r.rule_id):
        by_block.setdefault(r.block, []).append(r)
    return [
        ReportBlock(id=block, title=BLOCK_TITLES[block], rule_results=by_block[block])
        for block in BLOCK_ORDER
        if block in by_block and block != "diff_impact"
    ]


def _findings(results: list[RuleResult]):
    return [f for r in results for f in r.findings]


def count_suspicions(results: list[RuleResult]) -> int:
    """Подозрения без служебных «проверка не выполнена»; схлопнутая находка считается за одну."""
    return sum(1 for f in _findings(results) if f.level == "suspicion" and not f.not_run)


def build_summary(results: list[RuleResult], th: Thresholds = DEFAULT_THRESHOLDS) -> Summary:
    findings = _findings(results)
    suspicion = count_suspicions(results)
    warning = (
        NOISE_TEXT.format(n=suspicion, budget=th.NOISE_SUSPICION_BUDGET)
        if suspicion > th.NOISE_SUSPICION_BUDGET
        else None
    )
    return Summary(
        violation=sum(1 for f in findings if f.level == "violation" and not f.not_run),
        suspicion=suspicion,
        not_checked=sum(1 for f in findings if f.level == "not_checked"),
        not_run=sum(1 for r in results if r.outcome == "not_run"),
        passed_rules=sorted(r.rule_id for r in results if r.outcome == "passed"),
        noise_warning=warning,
    )


def structure_tree(doc: Document) -> list[StructureNode]:
    """Распознанная структура: дерево разделов по parent_id (служебный блок отчёта)."""
    children: dict[str | None, list[Section]] = {}
    ids = {s.id for s in doc.sections}
    for s in doc.sections:
        parent = s.parent_id if s.parent_id in ids else None
        children.setdefault(parent, []).append(s)

    def node(s: Section, seen: frozenset[str]) -> StructureNode:
        kids = [] if s.id in seen else children.get(s.id, [])
        return StructureNode(
            title=s.title,
            kind=s.kind,
            number=s.number,
            detection=s.detection,
            confidence=s.confidence,
            paragraph_idx=s.heading_paragraph_idx,
            children=[node(k, seen | {s.id}) for k in kids],
        )

    return [node(s, frozenset()) for s in children.get(None, [])]


def assemble_check_report(
    doc: Document,
    results: list[RuleResult],
    *,
    file: FileInfo,
    layout: LayoutInfo,
    volume: VolumeInfo,
    matrix: Matrix,
    service_version: str,
    checked_at: datetime,
    warnings: list[str] | None = None,
    th: Thresholds = DEFAULT_THRESHOLDS,
) -> CheckReport:
    return CheckReport(
        schema_version=SCHEMA_VERSION,  # type: ignore[arg-type]
        service_version=service_version,
        checked_at=checked_at,
        file=file,
        layout=layout,
        volume=volume,
        structure=structure_tree(doc),
        summary=build_summary(results, th),
        blocks=build_blocks(results),
        not_checked=nc_items(layout_failed=doc.layout is None),
        matrix=matrix,
        warnings=list(warnings if warnings is not None else doc.meta.warnings),
    )


__all__ = [
    "BLOCK_TITLES", "assemble_check_report", "build_blocks", "build_summary",
    "count_suspicions", "structure_tree",
]  # fmt: skip
