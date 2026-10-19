"""Приложения (ARCHITECTURE.md §7 п.8)."""

from __future__ import annotations

from vkr_checker.model.document import Appendix, Document

from .patterns import APPENDIX_HEAD


def extract_appendices(doc: Document) -> tuple[Appendix, ...]:
    result: list[Appendix] = []
    for sec in doc.sections:
        if sec.kind != "APPENDIX" or sec.heading_paragraph_idx is None:
            continue
        heading = doc.paragraph(sec.heading_paragraph_idx)
        m = APPENDIX_HEAD.match(" ".join(heading.full_text.split()))
        if m is None or not m.group("key"):
            continue
        key = m.group("key").upper()
        title = m.group("title").strip()
        if not title:
            nxt = next(
                (p for p in doc.paragraphs
                 if p.idx > heading.idx and p.cell is None and p.text.strip()), None,
            )  # fmt: skip
            if nxt is not None and nxt.section_id == sec.id and len(nxt.text) <= 150:
                title = nxt.text.strip()
        result.append(
            Appendix(
                label=f"Приложение {key}",
                key=key,
                title=title,
                section_id=sec.id,
                starts_new_page=heading.page_break_before,
            )  # fmt: skip
        )
    return tuple(result)
