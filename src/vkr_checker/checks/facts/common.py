"""Общие типы и обходы для фактов (ARCHITECTURE_CHECKS.md §3)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from vkr_checker.model.document import CellRef, Document, Paragraph, Section

SKIP_KINDS = frozenset({"TITLE", "TOC", "BIBLIOGRAPHY"})


@dataclass(frozen=True, slots=True)
class Mention:
    """Место в тексте: абзац (или ячейка таблицы) и смещения внутри его текста."""

    paragraph_idx: int | None
    span: tuple[int, int]
    cell: CellRef | None = None


def subtree_ids(doc: Document, section: Section) -> set[str]:
    """id раздела и всех его потомков."""
    result: set[str] = set()
    stack = [section.id]
    while stack:
        sid = stack.pop()
        if sid in result:
            continue
        result.add(sid)
        sec = doc.section_by_id(sid)
        if sec is not None:
            stack.extend(sec.children)
    return result


def paragraphs_in(doc: Document, section: Section | None) -> list[Paragraph]:
    """Абзацы тела раздела вместе с подразделами, в порядке документа."""
    if section is None:
        return []
    ids = subtree_ids(doc, section)
    return [p for p in doc.paragraphs if p.section_id in ids and p.cell is None]


def section_kind_of(doc: Document, section_id: str | None) -> str:
    """Вид раздела; для подраздела главы - вид корня-предка (CHAPTER), если сам не особый."""
    sec = doc.section_by_id(section_id)
    seen: set[str] = set()
    while sec is not None and sec.id not in seen:
        seen.add(sec.id)
        if sec.kind != "SUBSECTION":
            return sec.kind
        sec = doc.section_by_id(sec.parent_id)
    return "UNKNOWN"


def chapter_of(doc: Document, section_id: str | None) -> Section | None:
    """Глава (CHAPTER), содержащая раздел, либо None."""
    sec = doc.section_by_id(section_id)
    seen: set[str] = set()
    while sec is not None and sec.id not in seen:
        seen.add(sec.id)
        if sec.kind == "CHAPTER":
            return sec
        sec = doc.section_by_id(sec.parent_id)
    return None


def heading_idx_set(doc: Document) -> set[int]:
    return {s.heading_paragraph_idx for s in doc.sections if s.heading_paragraph_idx}


def iter_text_units(doc: Document, *, skip_kinds=SKIP_KINDS) -> Iterator[tuple[Mention, str, str]]:
    """(место с пустым span, текст, вид раздела) для абзацев тела и ячеек таблиц.

    Абзацы заголовков не отдаются: числа и методы в названиях разделов не факты.
    """
    headings = heading_idx_set(doc)
    for p in doc.paragraphs:
        if p.cell is not None or p.idx in headings:
            continue
        kind = section_kind_of(doc, p.section_id)
        if kind in skip_kinds:
            continue
        yield Mention(p.idx, (0, len(p.text))), p.text, kind
    for t in doc.tables:
        kind = section_kind_of(doc, t.section_id)
        if kind in skip_kinds:
            continue
        for row in t.rows:
            for c in row.cells:
                if c.text.strip():
                    yield (
                        Mention(None, (0, len(c.text)), CellRef(t.idx, c.row, c.col)),
                        c.text,
                        kind,
                    )


def chapter_number(doc: Document, section_id: str | None) -> int | None:
    """Порядковый номер главы (1, 2, ...) среди CHAPTER документа, для разделов внутри неё."""
    chapter = chapter_of(doc, section_id)
    if chapter is None:
        return None
    chapters = [s.id for s in doc.sections if s.kind == "CHAPTER"]
    return chapters.index(chapter.id) + 1
