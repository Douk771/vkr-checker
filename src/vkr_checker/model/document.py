"""Внутренняя модель документа (ARCHITECTURE.md §5). Иммутабельные dataclass-ы, без зависимостей."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

SectionKind = Literal[
    "TITLE", "TOC", "INTRO", "CHAPTER", "SUBSECTION", "CHAPTER_CONCLUSIONS",
    "CONCLUSION", "BIBLIOGRAPHY", "APPENDIX", "UNKNOWN",
]  # fmt: skip
Origin = Literal["defaults", "table_style", "para_style", "direct"]
Container = Literal["body", "table_cell", "textbox", "footnote"]


@dataclass(frozen=True, slots=True)
class Valued:
    """Значение форматирования с источником (для подсказок)."""

    value: float | str | bool
    origin: Origin = "direct"


@dataclass(frozen=True, slots=True)
class ParaFormat:
    """None = не задано нигде. Размеры в см и pt."""

    first_line_cm: Valued | None = None
    hanging_cm: Valued | None = None
    left_cm: Valued | None = None
    right_cm: Valued | None = None
    line_spacing: Valued | None = None
    line_rule: Valued | None = None  # auto | exact | atLeast
    space_before_pt: Valued | None = None
    space_after_pt: Valued | None = None
    align: Valued | None = None
    v_align: Valued | None = None
    keep_next: Valued | None = None
    keep_lines: Valued | None = None
    page_break_before: Valued | None = None


@dataclass(frozen=True, slots=True)
class RunInfo:
    text: str
    bold: bool | None = None
    italic: bool | None = None
    size_pt: float | None = None
    font: str | None = None


@dataclass(frozen=True, slots=True)
class CellRef:
    table_idx: int
    row: int  # с 1
    col: int  # с 1


@dataclass(frozen=True, slots=True)
class Paragraph:
    idx: int  # сквозной номер абзаца тела, с 1
    text: str
    num_label: str | None = None
    style_id: str | None = None
    style_name: str | None = None
    outline_level: int | None = None
    fmt: ParaFormat = field(default_factory=ParaFormat)
    runs: tuple[RunInfo, ...] = ()
    container: Container = "body"
    cell: CellRef | None = None
    page_break_before: bool = False
    section_id: str | None = None

    @property
    def full_text(self) -> str:
        return f"{self.num_label} {self.text}" if self.num_label else self.text


@dataclass(frozen=True, slots=True)
class PageSetup:
    section_idx: int
    margin_left_cm: float | None = None
    margin_right_cm: float | None = None
    margin_top_cm: float | None = None
    margin_bottom_cm: float | None = None
    text_width_cm: float | None = None


@dataclass(frozen=True, slots=True)
class Cell:
    row: int
    col: int
    text: str = ""
    grid_span: int = 1
    v_merge: str | None = None  # restart | continue | None
    width: float | None = None
    paragraphs: tuple[Paragraph, ...] = ()


@dataclass(frozen=True, slots=True)
class Row:
    cells: tuple[Cell, ...] = ()
    height_twips: int | None = None
    height_rule: str | None = None
    cant_split: bool = False


@dataclass(frozen=True, slots=True)
class Table:
    idx: int  # с 1
    rows: tuple[Row, ...] = ()
    anchor_block: int = 0
    prev_paragraph_idx: int | None = None
    next_paragraph_idx: int | None = None
    grid_cols_cm: tuple[float, ...] = ()
    width_cm: float | None = None
    width_type: str = "auto"  # dxa | pct | auto
    layout_type: str = "autofit"  # fixed | autofit
    style_id: str | None = None
    style_exists: bool = True
    caption_idx: int | None = None
    parent_table_idx: int | None = None
    section_id: str | None = None

    def cell(self, row: int, col: int) -> Cell | None:
        for r in self.rows:
            for c in r.cells:
                if c.row == row and c.col == col:
                    return c
        return None

    def number_label(self, doc: Document) -> str:
        if self.caption_idx is not None and 0 <= self.caption_idx < len(doc.captions):
            return f"Таблица {doc.captions[self.caption_idx].number}"
        return f"таблица №{self.idx} без подписи"


@dataclass(frozen=True, slots=True)
class Image:
    idx: int
    paragraph_idx: int | None = None
    kind: Literal["picture", "chart", "smartart", "shape_group"] = "picture"
    in_textbox: bool = False
    textbox_paragraphs: tuple[Paragraph, ...] = ()
    caption_idx: int | None = None


@dataclass(frozen=True, slots=True)
class Caption:
    kind: Literal["table", "figure"]
    number: str
    title: str = ""
    label_text: str = ""
    number_parts: tuple[str, ...] = ()
    number_source: Literal["text", "seq_field", "autonum"] = "text"
    seq_field_stale_suspect: bool = False
    paragraph_idx: int | None = None
    image_idx: int | None = None  # для подписей в надписи
    target: int | None = None  # table_idx | image_idx
    in_appendix: bool = False


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    kind: SectionKind
    title: str
    level: int = 1
    number: str | None = None
    heading_paragraph_idx: int | None = None
    start_idx: int = 0
    end_idx: int = 0
    parent_id: str | None = None
    children: tuple[str, ...] = ()
    role_hint: Literal["theoretical", "empirical"] | None = None
    detection: Literal["style", "pattern", "heuristic"] = "style"
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class TocEntry:
    text: str
    number: str | None = None
    level: int = 1
    page_text: str | None = None
    page_num: int | None = None
    paragraph_idx: int | None = None
    resolved_section_id: str | None = None


@dataclass(frozen=True, slots=True)
class Toc:
    source: Literal["toc_field", "toc_styles", "text_pattern"]
    entries: tuple[TocEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class BibEntry:
    number: str | None
    text: str
    paragraph_idx: int


@dataclass(frozen=True, slots=True)
class Appendix:
    label: str
    key: str
    title: str = ""
    section_id: str | None = None
    starts_new_page: bool = False


@dataclass(frozen=True, slots=True)
class FieldRef:
    kind: str  # SEQ | REF | PAGEREF | TOC
    instruction: str
    result: str
    paragraph_idx: int | None = None


@dataclass(frozen=True, slots=True)
class Layout:
    """Привязка к страницам по вёрстке LibreOffice; None в Document = откат."""

    page_count: int
    paragraph_pages: dict[int, int] = field(default_factory=dict)
    table_pages: dict[int, int] = field(default_factory=dict)  # первая страница таблицы
    status: Literal["ok", "partial"] = "ok"
    # ARCHITECTURE.md §8.1: поля, добавленные к исходной модели (все с умолчаниями)
    table_last_pages: dict[int, int] = field(default_factory=dict)  # последняя страница
    heading_pages: dict[str, int] = field(default_factory=dict)  # section_id -> страница
    coverage: float = 1.0
    engine: str | None = None
    font_substitutions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocMeta:
    filename: str
    sha256: str
    parsed_at: datetime | None = None
    warnings: tuple[str, ...] = ()


Block = Paragraph | Table


@dataclass(frozen=True, slots=True)
class Document:
    meta: DocMeta
    page_setup: tuple[PageSetup, ...] = ()
    blocks: tuple[Block, ...] = ()
    paragraphs: tuple[Paragraph, ...] = ()
    tables: tuple[Table, ...] = ()
    images: tuple[Image, ...] = ()
    captions: tuple[Caption, ...] = ()
    sections: tuple[Section, ...] = ()
    toc: Toc | None = None
    bibliography: tuple[BibEntry, ...] = ()
    appendices: tuple[Appendix, ...] = ()
    fields: tuple[FieldRef, ...] = ()
    layout: Layout | None = None

    def paragraph(self, idx: int) -> Paragraph:
        """Абзац по сквозному номеру тела (с 1)."""
        if not 1 <= idx <= len(self.paragraphs) or self.paragraphs[idx - 1].idx != idx:
            for p in self.paragraphs:
                if p.idx == idx:
                    return p
            raise KeyError(f"нет абзаца {idx}")
        return self.paragraphs[idx - 1]

    def table(self, idx: int) -> Table:
        for t in self.tables:
            if t.idx == idx:
                return t
        raise KeyError(f"нет таблицы {idx}")

    def section_by_id(self, section_id: str | None) -> Section | None:
        for s in self.sections:
            if s.id == section_id:
                return s
        return None

    def section_path(self, section_id: str | None) -> list[str]:
        """Заголовки от корня до раздела: ["Глава 2", "2.1 Методы"]."""
        path: list[str] = []
        seen: set[str] = set()
        sec = self.section_by_id(section_id)
        while sec is not None and sec.id not in seen:
            seen.add(sec.id)
            path.append(f"{sec.number} {sec.title}".strip() if sec.number else sec.title)
            sec = self.section_by_id(sec.parent_id)
        return path[::-1]

    def page_of_paragraph(self, idx: int) -> int | None:
        return self.layout.paragraph_pages.get(idx) if self.layout else None

    def page_of_table(self, idx: int) -> int | None:
        return self.layout.table_pages.get(idx) if self.layout else None
