"""Рисунки абзаца: w:drawing и VML (ARCHITECTURE.md §6.5). Внешние картинки не загружаются."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from .revisions import W_R, walk_inline
from .xmlutil import NS, iter_descendants, qn, textbox_paragraphs

W_DRAWING = qn("w:drawing")
W_PICT = qn("w:pict")
_GRAPHIC_TAGS = {
    f"{{{NS['a']}}}blip": "picture",
    f"{{{NS['c']}}}chart": "chart",
    f"{{{NS['dgm']}}}relIds": "smartart",
    f"{{{NS['wpg']}}}wgp": "shape_group",
    f"{{{NS['v']}}}imagedata": "picture",
}
_PRIORITY = ("chart", "smartart", "shape_group", "picture")


@dataclass(frozen=True)
class RawImage:
    kind: str
    textbox: tuple[etree._Element, ...]  # абзацы надписи, в которой лежит рисунок


def _kind_of(holder: etree._Element) -> str | None:
    found: set[str] = set()
    for el in holder.iter():
        kind = _GRAPHIC_TAGS.get(el.tag) if isinstance(el.tag, str) else None
        if kind:
            found.add(kind)
    for kind in _PRIORITY:
        if kind in found:
            return kind
    return None


def paragraph_images(p: etree._Element) -> list[RawImage]:
    """Рисунки абзаца в порядке документа. Надпись без графики рисунком не считается."""
    images: list[RawImage] = []
    for event, run in walk_inline(p):
        if event != "run" or run.tag != W_R:
            continue
        holders = [d for d in iter_descendants(run) if d.tag in (W_DRAWING, W_PICT)]
        for holder in holders:
            kind = _kind_of(holder)
            if kind is None:
                continue
            images.append(RawImage(kind, tuple(textbox_paragraphs(holder))))
    return images
