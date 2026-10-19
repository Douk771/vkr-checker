"""Общие помощники правил: места по Mention, принадлежность разделам."""

from __future__ import annotations

from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.facts.common import Mention, section_kind_of
from vkr_checker.model.document import Table
from vkr_checker.model.finding import Location

MAIN_KINDS = frozenset({"INTRO", "CHAPTER", "CHAPTER_CONCLUSIONS", "CONCLUSION"})


def mention_location(ctx: CheckContext, m: Mention, span: tuple[int, int] | None = None):
    """Location для места факта (абзац или ячейка) с подсветкой span (по умолчанию из Mention)."""
    use = span if span is not None else m.span
    if m.cell is not None:
        return ctx.loc.cell(m.cell.table_idx, m.cell.row, m.cell.col, use)
    assert m.paragraph_idx is not None
    return ctx.loc.paragraph(m.paragraph_idx, use)


def table_in_main_part(ctx: CheckContext, table: Table) -> bool:
    """Таблица верхнего уровня в основной части (не приложение, не титул, не литература)."""
    if table.parent_table_idx is not None:
        return False
    return section_kind_of(ctx.doc, table.section_id) in MAIN_KINDS


def first_location(ctx: CheckContext, mentions: list[Mention], limit: int = 5) -> list[Location]:
    return [mention_location(ctx, m) for m in mentions[:limit]]
