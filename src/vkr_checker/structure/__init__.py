"""Распознавание структуры работы (ARCHITECTURE.md §7)."""

from __future__ import annotations

from dataclasses import replace

from vkr_checker.model.document import Document
from vkr_checker.thresholds import DEFAULT_THRESHOLDS, Thresholds

from .appendices import extract_appendices
from .bibliography import extract_bibliography
from .captions import build_captions
from .detector import assign_section_ids, build_sections, find_candidates
from .toc import build_toc, find_range, resolve_entries

__all__ = ["analyze_structure"]


def analyze_structure(doc: Document, th: Thresholds = DEFAULT_THRESHOLDS) -> Document:
    """Разделы, оглавление, подписи, литература, приложения. Не меняет текст абзацев."""
    rng = find_range(doc)
    skip = set(range(rng.first, rng.last + 1)) if rng else set()
    candidates = find_candidates(doc, skip, th)
    toc_head = next((c.idx for c in candidates if c.kind == "TOC"), None)
    intro = next((c.idx for c in candidates if c.kind == "INTRO"), None)
    starts = [i for i in (toc_head, rng.first if rng else None, intro) if i is not None]
    boundary = min(starts) if starts else None
    sections = build_sections(doc, candidates, boundary)
    doc = assign_section_ids(doc, sections)
    toc = build_toc(doc, rng)
    if toc is not None:
        toc = replace(
            toc, entries=tuple(resolve_entries(list(toc.entries), list(doc.sections), th))
        )
    doc = replace(doc, toc=toc)
    kinds = {s.id: s.kind for s in doc.sections}

    def in_appendix(section_id: str | None) -> bool:
        sec = doc.section_by_id(section_id)
        while sec is not None:
            if sec.kind == "APPENDIX":
                return True
            sec = doc.section_by_id(sec.parent_id)
        return kinds.get(section_id or "") == "APPENDIX"

    doc = build_captions(doc, in_appendix)
    return replace(doc, bibliography=extract_bibliography(doc), appendices=extract_appendices(doc))
