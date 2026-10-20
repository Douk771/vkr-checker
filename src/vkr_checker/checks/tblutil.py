"""Общие помощники правил оформления таблиц: обход ячеек, классификация, подсказки по origin."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from vkr_checker.model.document import Cell, Document, Paragraph, Table, Valued

# «n»/«N» без «п/п» — это объём выборки в статистических таблицах, а не номер строки.
NUMBER_HEADER = re.compile(
    r"^\s*(?:№|No\.?|#)\s*(?:п\s*/\s*п)?\s*$|^\s*(?:N\s*)?п\s*/\s*п\s*$", re.IGNORECASE
)
_DASH_ONLY = re.compile(r"^[—–\-−]+$")
_NUMERIC = re.compile(r"^[\d\s,.\-–−±<>=%*]+$")
_ORIGIN_HINTS = {
    "defaults": "значение пришло из настроек документа по умолчанию",
    "table_style": "значение пришло из стиля таблицы",
    "para_style": "значение пришло из стиля абзаца",
    "direct": "значение задано прямо в абзаце",
}
CellKind = Literal["header", "number", "numeric", "gray", "text"]


@dataclass(frozen=True, slots=True)
class CellPara:
    table: Table
    cell: Cell
    para: Paragraph


def iter_cell_paragraphs(doc: Document) -> Iterator[CellPara]:
    """Непустые абзацы ячеек всех таблиц в порядке документа."""
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if para.text.strip():
                        yield CellPara(table, cell, para)


def origin_hint(value: Valued | None, style_name: str | None = None) -> str:
    """«значение пришло из стиля абзаца „Обычный“» по origin эффективного значения."""
    if value is None:
        return ""
    base = _ORIGIN_HINTS.get(value.origin, "")
    if value.origin == "para_style" and style_name:
        return f"{base} «{style_name}»"
    return base


def number_columns(table: Table) -> set[int]:
    """Номера столбцов (с 1), чья шапка - «№» / «№ п/п»."""
    if not table.rows:
        return set()
    return {c.col for c in table.rows[0].cells if NUMBER_HEADER.match(c.text)}


def digit_share(text: str) -> float:
    chars = [ch for ch in text if not ch.isspace()]
    return sum(ch.isdigit() for ch in chars) / len(chars) if chars else 0.0


def classify_cell(table: Table, cell: Cell, gray: tuple[float, float]) -> CellKind | None:
    """Шапка, номер, число, сомнительная (серая зона по доле цифр) или текст; пустая - None."""
    text = cell.text.strip()
    if not text or _DASH_ONLY.match(text):
        return None  # «—» в ячейке — нет значения, ни число, ни текст
    if cell.row == 1:
        return "header"
    if cell.col in number_columns(table):
        return "number"
    if _NUMERIC.match(text) and any(ch.isdigit() for ch in text):
        return "numeric"
    share = digit_share(text)
    if gray[0] <= share <= gray[1]:
        return "gray"
    return "text"


def column_widths(table: Table) -> dict[int, float]:
    """Ширина столбцов сетки по номеру (с 1)."""
    return {i: w for i, w in enumerate(table.grid_cols_cm, 1)}
