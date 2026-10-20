"""Итог вёрстки и откат (ARCHITECTURE.md §8.5): Layout или причина, по которой его нет."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from vkr_checker.model.document import Document, Layout
from vkr_checker.thresholds import DEFAULT_THRESHOLDS, Thresholds

from .align import align_or_fail
from .fonts import font_substitutions
from .pdftext import extract_pages
from .soffice import LayoutError

log = logging.getLogger(__name__)
DISCLAIMER = "Вёрстка LibreOffice может расходиться с Word на 1-2 страницы."


@dataclass(frozen=True)
class LayoutOutcome:
    layout: Layout | None
    reason: str | None = None  # причина отката, показывается в отчёте

    @property
    def failed(self) -> bool:
        return self.layout is None


def compute_layout(
    doc: Document,
    convert: Callable[[], Path],
    *,
    engine: str | None = None,
    th: Thresholds = DEFAULT_THRESHOLDS,
) -> LayoutOutcome:
    """PDF -> текст -> привязка. Любой сбой вёрстки -> LayoutOutcome(None, причина)."""
    try:
        pdf_path = convert()
        pages = extract_pages(pdf_path)
        layout = align_or_fail(doc, pages, th)
    except LayoutError as exc:
        return LayoutOutcome(None, exc.reason)
    except Exception:  # noqa: BLE001 - вёрстка не должна ронять проверку
        log.exception("неожиданная ошибка вёрстки")
        return LayoutOutcome(None, "внутренняя ошибка вёрстки")
    layout = replace(
        layout,
        engine=engine,
        font_substitutions=tuple(font_substitutions(doc)),
        broken_notations=pages.broken,
    )
    return LayoutOutcome(layout)


def with_layout(doc: Document, outcome: LayoutOutcome) -> Document:
    """Document с Layout либо с причиной отката в meta.warnings."""
    if outcome.layout is not None:
        if outcome.layout.status == "partial":
            note = "Вёрстка привязана частично: проверки по страницам дают не выше подозрения."
            meta = replace(doc.meta, warnings=(*doc.meta.warnings, note))
            return replace(doc, layout=outcome.layout, meta=meta)
        return replace(doc, layout=outcome.layout)
    note = f"Вёрстка не удалась: {outcome.reason}. Проверки по страницам заменены оценкой."
    return replace(doc, layout=None, meta=replace(doc.meta, warnings=(*doc.meta.warnings, note)))
