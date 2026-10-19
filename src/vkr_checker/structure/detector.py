"""Заголовки и разделы: стили -> шаблоны -> эвристики (ARCHITECTURE.md §7 п.1-4)."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from vkr_checker.model.document import Document, Paragraph, Section
from vkr_checker.thresholds import Thresholds

from .patterns import (
    APPENDIX_HEAD,
    CHAPTER_NUM,
    HEADING_STYLE,
    NUMBER_ONLY,
    NUMBERED,
    ROLE_EMPIRIC,
    ROLE_THEORY,
    classify_name,
    clean_number,
    number_depth,
)

_END_PUNCT = re.compile(r"[.;:,]\s*$")
_ROOT_KINDS = ("TOC", "INTRO", "CONCLUSION", "BIBLIOGRAPHY", "APPENDIX")


@dataclass
class Candidate:
    idx: int
    kind: str | None
    number: str | None
    title: str
    style_level: int | None
    detection: str
    confidence: float
    auto_numbered: bool = False


def parse_heading(p: Paragraph) -> tuple[str | None, str | None, str]:
    """(вид по названию, номер, название) для текста заголовка."""
    full = " ".join(p.full_text.split())
    m = CHAPTER_NUM.match(full)
    if m:
        return "CHAPTER", clean_number(m.group("n")), m.group("title").strip() or full
    ap = APPENDIX_HEAD.match(full)
    if ap and classify_name(full) == "APPENDIX":
        return "APPENDIX", None, full
    n = NUMBERED.match(full)
    if n:
        title = n.group("title").strip()
        return classify_name(title), clean_number(n.group("n")), title
    if NUMBER_ONLY.match(full):
        return None, None, full
    return classify_name(full), None, full


def _style_level(p: Paragraph) -> int | None:
    for name in (p.style_name, p.style_id):
        m = HEADING_STYLE.match((name or "").strip())
        if m:
            return int(m.group(2))
    if p.outline_level is not None:
        return p.outline_level + 1
    return None


def _word_count(text: str) -> int:
    return len(text.split())


def _pattern_ok(p: Paragraph, kind: str | None, number: str | None, text: str) -> bool:
    """Допустимость заголовка, найденного только по тексту (без стиля)."""
    if not text or "\n" in text.strip():
        return False
    if kind in _ROOT_KINDS:
        return _word_count(text) <= 8 and not re.search(r"[,;]\s*$", text)
    if kind == "CHAPTER":
        return len(text) <= 150
    if kind == "CHAPTER_CONCLUSIONS":
        return len(text) <= 80 and _word_count(text) <= 8
    if number is not None:
        title = NUMBERED.match(text)
        body = title.group("title") if title else text
        if p.num_label is not None:  # автонумерация без стиля заголовка - скорее список
            return False
        return len(text) <= 100 and not _END_PUNCT.search(body) and body[:1].isupper()
    return False


def _is_bold(p: Paragraph) -> bool:
    return bool(p.runs) and all(r.bold for r in p.runs if r.text.strip())


def _heuristic_ok(p: Paragraph, th: Thresholds) -> bool:
    text = p.text.strip()
    if not text or len(text) >= th.HEURISTIC_HEADING_MAX_CHARS or text.endswith("."):
        return False
    letters = [c for c in text if c.isalpha()]
    caps = bool(letters) and all(c.isupper() for c in letters)
    centered = p.fmt.align is not None and p.fmt.align.value == "center"
    return (_is_bold(p) or caps) and (centered or p.page_break_before)


def find_candidates(doc: Document, skip: set[int], th: Thresholds) -> list[Candidate]:
    paras = [p for p in doc.paragraphs if p.cell is None and p.idx not in skip]
    found: dict[int, Candidate] = {}
    for p in paras:
        text = p.text.strip()
        if not text:
            continue
        level = _style_level(p)
        kind, number, title = parse_heading(p)
        if level is not None and len(text) <= th.HEADING_MAX_CHARS:
            conf = 1.0 if kind else 0.9
            found[p.idx] = Candidate(
                p.idx, kind, number, title, level, "style", conf, p.num_label is not None
            )  # fmt: skip
        elif _pattern_ok(p, kind, number, p.full_text.strip()) and (kind or number):
            found[p.idx] = Candidate(p.idx, kind, number, title, None, "pattern", 0.8)
    top = [c for c in found.values() if _is_top(c)]
    if len(top) < 3:
        for p in paras:
            if p.idx in found or not _heuristic_ok(p, th):
                continue
            kind, number, title = parse_heading(p)
            found[p.idx] = Candidate(p.idx, kind, number, title, None, "heuristic", 0.45)
    return [found[i] for i in sorted(found)]


def _is_top(c: Candidate) -> bool:
    return c.kind in (*_ROOT_KINDS, "CHAPTER") or (
        c.number is not None and number_depth(c.number) == 1
    )


def _role_hint(title: str, order: int) -> str | None:
    if ROLE_THEORY.search(title):
        return "theoretical"
    if ROLE_EMPIRIC.search(title):
        return "empirical"
    return {0: "theoretical", 1: "empirical"}.get(order)


def build_sections(doc: Document, cands: list[Candidate], boundary: int | None) -> list[Section]:
    """Дерево разделов: вид, уровень, родитель, диапазон абзацев."""
    first_of = {k: next((c.idx for c in cands if c.kind == k), None) for k in _ROOT_KINDS}
    main_lo = first_of["INTRO"] or 0
    ends = [i for k in ("CONCLUSION", "BIBLIOGRAPHY", "APPENDIX") if (i := first_of[k])]
    main_hi = min(ends) if ends else 10**9
    items: list[dict] = []
    for c in cands:
        kind, level = c.kind, c.style_level or 1
        if kind in _ROOT_KINDS or kind == "CHAPTER":
            level = 1
        elif kind == "CHAPTER_CONCLUSIONS":
            level = 2
        else:
            if c.number:
                level = number_depth(c.number)
            if level == 1:
                in_main = main_lo < c.idx < main_hi or (
                    first_of["INTRO"] is None and c.idx < main_hi
                )
                kind = "CHAPTER" if in_main else "UNKNOWN"
            else:
                kind = "SUBSECTION"
        items.append(dict(c=c, kind=kind, level=level))
    sections: list[Section] = []
    stack: list[Section] = []
    chapter_no = 0
    for it in items:
        c: Candidate = it["c"]
        while stack and stack[-1].level >= it["level"]:
            stack.pop()
        parent = stack[-1] if stack else None
        hint = None
        if it["kind"] == "CHAPTER":
            hint = _role_hint(c.title, chapter_no)
            chapter_no += 1
        sec = Section(
            id=f"s{len(sections) + 1}", kind=it["kind"], title=c.title, level=it["level"],
            number=c.number, heading_paragraph_idx=c.idx, start_idx=c.idx,
            parent_id=parent.id if parent else None, role_hint=hint,  # type: ignore[arg-type]
            detection=c.detection, confidence=c.confidence,  # type: ignore[arg-type]
        )  # fmt: skip
        sections.append(sec)
        stack.append(sec)
    return _with_title(doc, _link(doc, sections), boundary)


def _link(doc: Document, sections: list[Section]) -> list[Section]:
    last = len(doc.paragraphs)
    result: list[Section] = []
    for i, s in enumerate(sections):
        end = last
        for nxt in sections[i + 1 :]:
            if nxt.level <= s.level:
                end = nxt.start_idx - 1
                break
        children = tuple(x.id for x in sections if x.parent_id == s.id)
        result.append(replace(s, end_idx=end, children=children))
    return result


def _with_title(doc: Document, sections: list[Section], boundary: int | None) -> list[Section]:
    first_start = min((s.start_idx for s in sections), default=len(doc.paragraphs) + 1)
    if boundary is None:
        return sections
    end = min(first_start, boundary) - 1
    body = [p for p in doc.paragraphs if p.cell is None and p.idx <= end and p.text.strip()]
    if not body:
        return sections
    title = Section(
        id="s0", kind="TITLE", title="Титульный лист", level=1, heading_paragraph_idx=None,
        start_idx=1, end_idx=end, detection="heuristic", confidence=0.6,
    )  # fmt: skip
    return [title, *sections]


def assign_section_ids(doc: Document, sections: list[Section]) -> Document:
    """Paragraph.section_id и Table.section_id по самому глубокому разделу."""
    starts = sorted(((s.start_idx, s.id) for s in sections), key=lambda t: t[0])
    ids: dict[int, str | None] = {}
    cur: str | None = None
    k = 0
    for p in doc.paragraphs:
        while k < len(starts) and starts[k][0] <= p.idx:
            cur = starts[k][1]
            k += 1
        ids[p.idx] = cur
    paragraphs = tuple(replace(p, section_id=ids.get(p.idx)) for p in doc.paragraphs)
    by_idx = {p.idx: p for p in paragraphs}

    def table_section(t):
        for ref in (t.prev_paragraph_idx, t.next_paragraph_idx):
            if ref in by_idx:
                return by_idx[ref].section_id
        return None

    tables = tuple(replace(t, section_id=table_section(t)) for t in doc.tables)
    t_by = {t.idx: t for t in tables}
    blocks = tuple(by_idx[b.idx] if isinstance(b, Paragraph) else t_by[b.idx] for b in doc.blocks)
    return replace(
        doc, paragraphs=paragraphs, tables=tables, blocks=blocks, sections=tuple(sections)
    )
