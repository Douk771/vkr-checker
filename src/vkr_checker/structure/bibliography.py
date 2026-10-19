"""Список литературы (ARCHITECTURE.md §7 п.7)."""

from __future__ import annotations

import re

from vkr_checker.model.document import BibEntry, Document

_NUM = re.compile(r"^\s*(\d{1,4})\s*[.)]\s+")


def subtree(doc: Document, section_id: str) -> set[str]:
    ids: set[str] = set()
    stack = [section_id]
    while stack:
        sid = stack.pop()
        if sid in ids:
            continue
        ids.add(sid)
        sec = doc.section_by_id(sid)
        if sec:
            stack.extend(sec.children)
    return ids


def extract_bibliography(doc: Document) -> tuple[BibEntry, ...]:
    sec = next((s for s in doc.sections if s.kind == "BIBLIOGRAPHY"), None)
    if sec is None:
        return ()
    ids = subtree(doc, sec.id)
    headings = {s.heading_paragraph_idx for s in doc.sections}
    entries: list[BibEntry] = []
    for p in doc.paragraphs:
        if p.cell is not None or p.section_id not in ids or p.idx in headings:
            continue
        text = p.text.strip()
        if not text:
            continue
        number = None
        if p.num_label:
            number = p.num_label.strip().rstrip(".)") or None
        else:
            m = _NUM.match(text)
            if m:
                number, text = m.group(1), text[m.end() :].strip()
        entries.append(BibEntry(number=number, text=text, paragraph_idx=p.idx))
    return tuple(entries)
