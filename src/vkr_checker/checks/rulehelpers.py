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


def section_id_of(ctx: CheckContext, m: Mention) -> str | None:
    """Раздел, в котором лежит место факта (абзац или таблица)."""
    if m.cell is not None:
        return ctx.doc.table(m.cell.table_idx).section_id
    if m.paragraph_idx is None:
        return None
    return ctx.doc.paragraph(m.paragraph_idx).section_id


def in_section_tree(ctx: CheckContext, section_id: str | None, root_id: str) -> bool:
    """section_id лежит в поддереве root_id."""
    doc = ctx.doc
    seen: set[str] = set()
    sec = doc.section_by_id(section_id)
    while sec is not None and sec.id not in seen:
        if sec.id == root_id:
            return True
        seen.add(sec.id)
        sec = doc.section_by_id(sec.parent_id)
    return False
