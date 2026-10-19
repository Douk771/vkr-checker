"""Объём основной части: по вёрстке или оценка по тексту (ARCHITECTURE.md §8.1, §8.5)."""

from __future__ import annotations

from dataclasses import dataclass, field

from vkr_checker.model.document import Document, Section
from vkr_checker.thresholds import DEFAULT_THRESHOLDS, Thresholds

ESTIMATE_FORMULA = (
    "страницы = символы с пробелами / {chars} + строки таблиц × {row} + рисунки × {img}"
)
_MAIN_KINDS = ("INTRO", "CHAPTER", "CONCLUSION")
_END_KINDS = ("BIBLIOGRAPHY", "APPENDIX")


@dataclass(frozen=True)
class Volume:
    method: str  # layout | estimate
    pages_main: float | None
    by_section: tuple[tuple[str, float], ...] = ()
    formula: str | None = None
    note: str | None = None
    unavailable: bool = field(default=False)


def main_sections(doc: Document) -> list[Section]:
    """Корневые разделы основной части: от введения до заключения включительно."""
    roots = [s for s in doc.sections if s.parent_id is None]
    intro = next((i for i, s in enumerate(roots) if s.kind == "INTRO"), None)
    if intro is None:
        return []
    result: list[Section] = []
    for s in roots[intro:]:
        if s.kind in _END_KINDS:
            break
        if s.kind in _MAIN_KINDS or s.kind in ("UNKNOWN", "CHAPTER_CONCLUSIONS"):
            result.append(s)
    return result


def _label(s: Section) -> str:
    return f"{s.number} {s.title}".strip() if s.number else s.title


def volume_by_layout(doc: Document) -> Volume | None:
    """Страницы от заголовка введения до страницы перед списком литературы/приложениями."""
    if doc.layout is None:
        return None
    pages = doc.layout.heading_pages
    secs = main_sections(doc)
    roots = [s for s in doc.sections if s.parent_id is None]
    end_sec = next((s for s in roots if s.kind in _END_KINDS), None)
    if not secs or secs[0].id not in pages:
        return None
    end_page = pages.get(end_sec.id) if end_sec else doc.layout.page_count + 1
    if end_page is None:
        return None
    by_section: list[tuple[str, float]] = []
    for i, s in enumerate(secs):
        start = pages.get(s.id)
        if start is None:
            continue
        nxt = next((pages[n.id] for n in secs[i + 1 :] if n.id in pages), end_page)
        by_section.append((_label(s), float(max(nxt - start, 0))))
    total = float(max(end_page - pages[secs[0].id], 0))
    return Volume("layout", total, tuple(by_section))


def _section_chars(doc: Document, section: Section) -> int:
    ids = _subtree(doc, section)
    return sum(
        len(p.text)
        for p in doc.paragraphs
        if p.section_id in ids and p.cell is None and p.container == "body"
    )


def _subtree(doc: Document, section: Section) -> set[str]:
    ids: set[str] = set()
    stack = [section.id]
    while stack:
        sid = stack.pop()
        if sid in ids:
            continue
        ids.add(sid)
        sec = doc.section_by_id(sid)
        if sec:
            stack.extend(sec.children)
    return ids


def volume_by_estimate(doc: Document, th: Thresholds = DEFAULT_THRESHOLDS) -> Volume:
    """Оценка без вёрстки: символы, строки таблиц и рисунки основной части."""
    formula = ESTIMATE_FORMULA.format(
        chars=th.CHARS_PER_PAGE, row=th.TABLE_ROW_PAGE_SHARE, img=th.IMAGE_PAGE_SHARE
    )
    secs = main_sections(doc)
    if not secs:
        return Volume("estimate", None, (), formula, "основная часть не найдена", True)
    by_section: list[tuple[str, float]] = []
    for s in secs:
        ids = _subtree(doc, s)
        rows = sum(
            len(t.rows) for t in doc.tables if t.section_id in ids and t.parent_table_idx is None
        )
        para_idx = {p.idx for p in doc.paragraphs if p.section_id in ids}
        images = sum(1 for i in doc.images if i.paragraph_idx in para_idx)
        pages = (
            _section_chars(doc, s) / th.CHARS_PER_PAGE
            + rows * th.TABLE_ROW_PAGE_SHARE
            + images * th.IMAGE_PAGE_SHARE
        )
        by_section.append((_label(s), round(pages, 1)))
    total = round(sum(v for _, v in by_section), 1)
    return Volume("estimate", total, tuple(by_section), formula)


def compute_volume(doc: Document, th: Thresholds = DEFAULT_THRESHOLDS) -> Volume:
    """По вёрстке, если она есть и покрывает основную часть, иначе оценка (откат)."""
    return volume_by_layout(doc) or volume_by_estimate(doc, th)
