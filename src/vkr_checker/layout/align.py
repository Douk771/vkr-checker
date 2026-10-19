"""Привязка абзацев и таблиц к страницам PDF: монотонное выравнивание (ARCHITECTURE.md §8.4)."""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from vkr_checker.model.document import Document, Layout, Paragraph, Table
from vkr_checker.nlp.normalize import normalize_key
from vkr_checker.thresholds import DEFAULT_THRESHOLDS, Thresholds

from .pdftext import PdfPages
from .soffice import LayoutError


@dataclass
class AlignResult:
    layout: Layout
    matched: int
    eligible: int


@dataclass
class _Cursor:
    pos: int = 0
    last_page: int = 1
    matched: int = 0
    eligible: int = 0
    pages: dict[int, int] = field(default_factory=dict)


class Aligner:
    def __init__(self, pdf: PdfPages, th: Thresholds) -> None:
        self.pdf = pdf
        self.th = th
        self.cur = _Cursor()

    def _find(self, key: str) -> tuple[int, int] | None:
        """(начало, конец) ключа в тексте PDF начиная с курсора или None."""
        th, text = self.th, self.pdf.joined
        lo = self.cur.pos
        hit = text.find(key, lo, lo + th.ALIGN_WINDOW)
        if hit >= 0:
            return hit, hit + len(key)
        window = text[lo : lo + th.ALIGN_WINDOW]
        if not window:
            return None
        res = fuzz.partial_ratio_alignment(key, window)
        if res is not None and res.score >= th.ALIGN_FUZZY_MIN:
            return lo + res.dest_start, lo + res.dest_end
        return None

    def locate(self, text: str) -> int | None:
        """Страница по началу текста; двигает курсор. None - не найдено или слишком коротко."""
        key = normalize_key(text)[: self.th.ALIGN_KEY_LEN]
        if len(key) < self.th.ALIGN_MIN_KEY:
            return None
        self.cur.eligible += 1
        found = self._find(key)
        if found is None:
            return None
        self.cur.matched += 1
        self.cur.pos = found[1]
        page = self.pdf.page_at(found[0])
        self.cur.last_page = page
        return page

    def locate_end(self, text: str) -> int | None:
        """Страница конца текста (ищет ключ из последних символов), курсор вперёд."""
        key = normalize_key(text)[-self.th.ALIGN_KEY_LEN :]
        if len(key) < self.th.ALIGN_MIN_KEY:
            return None
        found = self._find(key)
        if found is None:
            return None
        self.cur.pos = found[1]
        page = self.pdf.page_at(found[1] - 1)
        self.cur.last_page = max(self.cur.last_page, page)
        return page


def _cell_texts(table: Table) -> list[str]:
    return [c.text for r in table.rows for c in r.cells if len(normalize_key(c.text)) >= 8]


def align(doc: Document, pdf: PdfPages, th: Thresholds = DEFAULT_THRESHOLDS) -> AlignResult:
    """Страницы абзацев тела и таблиц. Непривязанные получают страницу предыдущего якоря."""
    al = Aligner(pdf, th)
    para_pages: dict[int, int | None] = {}
    first_pages: dict[int, int] = {}
    last_pages: dict[int, int] = {}
    for block in doc.blocks:
        if isinstance(block, Paragraph):
            para_pages[block.idx] = al.locate(block.full_text)
        else:
            texts = _cell_texts(block)
            first = al.locate(texts[0]) if texts else None
            last = al.locate_end(texts[-1]) if len(texts) > 1 else first
            if first is not None:
                first_pages[block.idx] = first
                last_pages[block.idx] = max(last or first, first)
    final: dict[int, int] = {}
    prev = next((p for p in para_pages.values() if p is not None), 1)
    for idx, page in para_pages.items():  # порядок словаря = порядок документа
        prev = page if page is not None else prev
        final[idx] = prev
    # абзацы ячеек и надписей: страница их таблицы; таблицы без якоря - страница предшественника
    for t in doc.tables:
        if t.idx not in first_pages:
            anchor = final.get(t.prev_paragraph_idx or 0) or (min(final.values(), default=1))
            first_pages[t.idx] = last_pages[t.idx] = anchor
    for p in doc.paragraphs:
        if p.cell is not None and p.cell.table_idx in first_pages:
            final[p.idx] = first_pages[p.cell.table_idx]
    total = al.cur.eligible
    coverage = al.cur.matched / total if total else 0.0
    status = "ok" if coverage >= th.LAYOUT_OK_COVERAGE else "partial"
    layout = Layout(
        page_count=pdf.page_count,
        paragraph_pages=final,
        table_pages=first_pages,
        status=status,  # type: ignore[arg-type]
        table_last_pages=last_pages,
        heading_pages={
            s.id: final[s.heading_paragraph_idx]
            for s in doc.sections
            if s.heading_paragraph_idx in final
        },
        coverage=round(coverage, 3),
    )
    return AlignResult(layout, al.cur.matched, total)


def align_or_fail(doc: Document, pdf: PdfPages, th: Thresholds = DEFAULT_THRESHOLDS) -> Layout:
    """Layout или LayoutError, если покрытие ниже порога отката (A §8.5)."""
    result = align(doc, pdf, th)
    if result.layout.coverage < th.LAYOUT_MIN_COVERAGE:
        raise LayoutError(
            f"привязка к страницам ненадёжна: покрытие {result.layout.coverage:.0%} "
            f"при минимуме {th.LAYOUT_MIN_COVERAGE:.0%}"
        )
    return result.layout
