"""Текст PDF по страницам в нормализованном виде (ARCHITECTURE.md §8.3)."""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from pathlib import Path

from vkr_checker.nlp.normalize import join_hyphenated_lines, normalize_key

from .soffice import LayoutError

_NUMBER_LINE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$")


@dataclass(frozen=True)
class PdfPages:
    """Нормализованный текст страниц и общая строка со смещениями начала страниц."""

    pages: tuple[str, ...]
    joined: str
    starts: tuple[int, ...]

    @classmethod
    def from_pages(cls, pages: list[str]) -> PdfPages:
        starts: list[int] = []
        offset = 0
        for text in pages:
            starts.append(offset)
            offset += len(text)
        return cls(tuple(pages), "".join(pages), tuple(starts))

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


def extract_pages(pdf_path: Path) -> PdfPages:
    """Читает PDF через pypdfium2; любой сбой -> LayoutError."""
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 - библиотека бросает разные типы на битый PDF
        raise LayoutError("PDF не читается") from exc
    try:
        pages: list[str] = []
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                textpage = page.get_textpage()
                try:
                    pages.append(normalize_page(textpage.get_text_range()))
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
    return PdfPages.from_pages(pages)
