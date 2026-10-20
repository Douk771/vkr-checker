"""Текст PDF по страницам в нормализованном виде (ARCHITECTURE.md §8.3)."""

from __future__ import annotations

import bisect
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from vkr_checker.model.document import BrokenNotation
from vkr_checker.nlp.normalize import join_hyphenated_lines, normalize_key

from .soffice import LayoutError

_NUMBER_LINE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$")


@dataclass(frozen=True)
class PdfPages:
    """Нормализованный текст страниц и общая строка со смещениями начала страниц."""

    pages: tuple[str, ...]
    joined: str
    starts: tuple[int, ...]
    broken: tuple[BrokenNotation, ...] = ()

    @classmethod
    def from_pages(cls, pages: list[str], broken: tuple[BrokenNotation, ...] = ()) -> PdfPages:
        starts: list[int] = []
        offset = 0
        for text in pages:
            starts.append(offset)
            offset += len(text)
        return cls(tuple(pages), "".join(pages), tuple(starts), broken)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def page_at(self, offset: int) -> int:
        """Номер страницы (с 1), на которой лежит смещение в `joined`."""
        return max(bisect.bisect_right(self.starts, offset), 1)


def normalize_page(raw: str) -> str:
    """Сырой текст страницы -> ключевая строка (только буквы и цифры нижнего регистра)."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = join_hyphenated_lines(text)
    lines = [ln for ln in text.split("\n") if not _NUMBER_LINE.match(ln)]  # колонтитулы-номера
    return normalize_key("\n".join(lines))


# Разрыв записи величины на границе строк (TBL-06): проблема не обычный пробел сам по себе,
# а то, что знак или единица уехали на следующую строку.
_SYM = r"(?:n|N|p|t|r|rs|U|H|F|M|SD|df|d|R[2²]|χ[2²]|β|α)"
_SIGN = r"[=<>≤≥]"
_UNITS = r"(?:%|ч|час\w*|мин|сек|лет|года?|г\.|мес|мм|см|км|мг|кг|мл|балл\w*|чел\.)"
_BREAKS = (
    (re.compile(r"(?:^|\s)(\d+(?:[,.]\d+)?)\s*$"), re.compile(rf"^\s*({_UNITS})(?![\w])")),
    (re.compile(rf"(?:^|[\s(;,])({_SYM})\s*$"), re.compile(rf"^\s*({_SIGN}\s*[-−–]?\d[\d,.]*)")),
    (re.compile(rf"(?:^|[\s(;,])({_SYM}\s*{_SIGN})\s*$"), re.compile(r"^\s*([-−–]?\d[\d,.]*)")),
)
_YEAR = re.compile(r"^(?:1[89]|20)\d{2}$")


def find_broken_notations(raw: str, page: int) -> list[BrokenNotation]:
    """Места, где число и его знак/единица оказались на разных строках."""
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # число отдельной строкой в начале или конце страницы — колонтитул с номером страницы,
    # а не продолжение записи
    while lines and (not lines[-1].strip() or _NUMBER_LINE.match(lines[-1])):
        lines.pop()
    while lines and (not lines[0].strip() or _NUMBER_LINE.match(lines[0])):
        lines.pop(0)
    out: list[BrokenNotation] = []
    for cur, nxt in zip(lines, lines[1:], strict=False):
        for end_re, start_re in _BREAKS:
            e, s = end_re.search(cur), start_re.match(nxt)
            if not e or not s:
                continue
            if _YEAR.match(e.group(1)) and s.group(1).startswith(("год", "г.")):
                continue  # «2025⏎года» — дата, а не величина
            out.append(BrokenNotation(page, cur.rstrip()[-30:], nxt.lstrip()[:30]))
            break
    return out


_PDFIUM_LOCK = threading.Lock()  # PDFium не потокобезопасен: все обращения строго по одному


def extract_pages(pdf_path: Path) -> PdfPages:
    """Читает PDF через pypdfium2; любой сбой -> LayoutError."""
    with _PDFIUM_LOCK:
        return _extract_pages_locked(pdf_path)


def _extract_pages_locked(pdf_path: Path) -> PdfPages:
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 - библиотека бросает разные типы на битый PDF
        raise LayoutError("PDF не читается") from exc
    try:
        pages: list[str] = []
        broken: list[BrokenNotation] = []
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                textpage = page.get_textpage()
                try:
                    raw = textpage.get_text_range()
                    pages.append(normalize_page(raw))
                    broken.extend(find_broken_notations(raw, i + 1))
                finally:
                    textpage.close()
            finally:
                page.close()
    except LayoutError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LayoutError("не удалось извлечь текст PDF") from exc
    finally:
        pdf.close()
    if not pages:
        raise LayoutError("в PDF нет страниц")
    return PdfPages.from_pages(pages, tuple(broken))
