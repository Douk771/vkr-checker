"""Списки из введения и заключения: задачи, положения на защиту, выводы (TSK-01, матрица)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from vkr_checker.model.document import Document, Paragraph
from vkr_checker.nlp.sentences import split_sentences

from .common import heading_idx_set, paragraphs_in
from .intro import IntroElement

_ENUM = re.compile(r"(?:^|(?<=\s))\(?(\d{1,2})[.)]\s+(?=\S)")
_MARKER = re.compile(r"^[\s\d.)\-–—•*]+")
MIN_CONCLUSION_CHARS = 40


@dataclass(frozen=True, slots=True)
class ListItem:
    index: int  # порядковый номер в списке, с 1
    text: str
    paragraph_idx: int
    span: tuple[int, int]


def _clean(text: str) -> str:
    return _MARKER.sub("", text).strip()


def _split_inline(text: str, offset: int) -> list[tuple[str, tuple[int, int]]]:
    """«1) изучить X; 2) выявить Y» или «изучить X; выявить Y» -> элементы со смещениями."""
    marks = list(_ENUM.finditer(text))
    if len(marks) >= 2:
        bounds = [m.end() for m in marks] + [len(text)]
        starts = [m.start() for m in marks[1:]] + [len(text)]
        return [
            (text[b:e].strip(" ;. "), (offset + b, offset + e))
            for b, e in zip(bounds, starts, strict=False)
        ]
    parts = [(m.start(), m.end()) for m in re.finditer(r"[^;]+;?", text) if m.group().strip(" ;")]
    if len(parts) >= 2:
        return [(text[s:e].strip(" ;. "), (offset + s, offset + e)) for s, e in parts]
    stripped = text.strip()
    return [(stripped, (offset, offset + len(text)))] if stripped else []


def items_from_element(doc: Document, element: IntroElement) -> list[ListItem]:
    """Пункты элемента введения: остаток первого абзаца и следующие абзацы-пункты."""
    headings = heading_idx_set(doc)
    items: list[ListItem] = []
    first = doc.paragraph(element.paragraph_idx)
    if element.position != "heading" and element.text:
        offset = first.text.find(element.text)
        for text, span in _split_inline(element.text, max(offset, 0)):
            items.append(ListItem(0, _clean(text), first.idx, span))
    for idx in element.content_paragraphs[1:]:
        p = doc.paragraph(idx)
        if idx in headings or not p.text.strip():
            continue
        pieces = _split_inline(p.text, 0) if _ENUM.search(p.text) and not p.num_label else None
        if pieces and len(pieces) >= 2:
            items.extend(ListItem(0, _clean(t), p.idx, sp) for t, sp in pieces)
        else:
            items.append(ListItem(0, _clean(p.text), p.idx, (0, len(p.text))))
    items = [i for i in items if i.text]
    return [ListItem(n, i.text, i.paragraph_idx, i.span) for n, i in enumerate(items, 1)]


def _is_listed(p: Paragraph) -> bool:
    return bool(p.num_label) or bool(re.match(r"^\s*\d{1,2}[.)]\s+\S", p.text))


def conclusion_items(doc: Document, section_kind: str = "CONCLUSION") -> list[ListItem]:
    """Выводы раздела: нумерованные абзацы, иначе содержательные абзацы без заголовка."""
    section = next((s for s in doc.sections if s.kind == section_kind), None)
    return section_items(doc, section)


def section_items(doc: Document, section) -> list[ListItem]:
    if section is None:
        return []
    paras = [
        p
        for p in paragraphs_in(doc, section)
        if p.idx != section.heading_paragraph_idx and p.text.strip()
    ]
    chosen = [p for p in paras if _is_listed(p)] or [
        p for p in paras if len(p.text) >= MIN_CONCLUSION_CHARS
    ]
    result = []
    for n, p in enumerate(chosen, 1):
        sentences = split_sentences(p.text)
        text = _clean(p.text) if sentences else p.text
        result.append(ListItem(n, text, p.idx, (0, len(p.text))))
    return result
