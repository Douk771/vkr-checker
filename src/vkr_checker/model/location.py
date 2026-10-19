"""Location: общий тип места находки (ARCHITECTURE.md §5). Строится только через make_location."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .document import CellRef, Document

QUOTE_LEN = 100


@dataclass(frozen=True, slots=True)
class TableRef:
    number_label: str
    table_idx: int
    row: int | None = None
    col: int | None = None


@dataclass(frozen=True, slots=True)
class Location:
    section_path: list[str] = field(default_factory=list)
    paragraph_idx: int | None = None
    table: TableRef | None = None
    quote: str = ""
    highlight: tuple[int, int] | None = None
    page: int | None = None


def make_quote(text: str, char_span: tuple[int, int] | None, width: int = QUOTE_LEN):
    """Цитата ~width символов вокруг span; возвращает (quote, highlight внутри quote)."""
    text = " ".join(text.split()) if char_span is None else text
    if char_span is None:
        return text[:width], None
    start, end = max(0, char_span[0]), min(len(text), char_span[1])
    if end <= start:
        return text[:width], None
    span_len = end - start
    if span_len >= width:
        return text[start : start + width], (0, width)
    pad = (width - span_len) // 2
    lo = max(0, start - pad)
    hi = min(len(text), lo + width)
    lo = max(0, hi - width)
    return text[lo:hi], (start - lo, end - lo)


def make_location(
    doc: Document,
    paragraph_idx: int | None = None,
    cell_ref: CellRef | None = None,
    char_span: tuple[int, int] | None = None,
) -> Location:
    """Единственный способ построить Location: путь раздела, цитата, подсветка, страница."""
    if (paragraph_idx is None) == (cell_ref is None):
        raise ValueError("нужен ровно один из paragraph_idx / cell_ref")
    if paragraph_idx is not None:
        para = doc.paragraph(paragraph_idx)
        quote, hl = make_quote(para.text, char_span)
        return Location(
            section_path=doc.section_path(para.section_id),
            paragraph_idx=paragraph_idx,
            quote=quote,
            highlight=hl,
            page=doc.page_of_paragraph(paragraph_idx),
        )
    table = doc.table(cell_ref.table_idx)
    cell = table.cell(cell_ref.row, cell_ref.col)
    quote, hl = make_quote(cell.text if cell else "", char_span)
    label = table.number_label(doc)
    return Location(
        section_path=doc.section_path(table.section_id),
        table=TableRef(label, table.idx, cell_ref.row, cell_ref.col),
        quote=quote,
        highlight=hl,
        page=doc.page_of_table(table.idx),
    )
