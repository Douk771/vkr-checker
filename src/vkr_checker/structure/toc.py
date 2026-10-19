"""Оглавление: диапазон абзацев и записи (ARCHITECTURE.md §7 п.5)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from vkr_checker.model.document import Document, Paragraph, Section, Toc, TocEntry
from vkr_checker.nlp.normalize import normalize_text
from vkr_checker.thresholds import Thresholds

from .patterns import (
    CHAPTER_NUM,
    NUMBERED,
    TOC_LINE,
    TOC_LINE_STRICT,
    TOC_STYLE,
    classify_name,
    clean_number,
    number_depth,
)

_TRAIL_LEADER = re.compile(r"[\s.·…_\-–—\t]+$")
_MAX_GAP = 2  # пустых абзацев подряд внутри оглавления


@dataclass(frozen=True)
class TocRange:
    source: str  # toc_field | toc_styles | text_pattern
    first: int
    last: int


def _body(doc: Document) -> list[Paragraph]:
    return [p for p in doc.paragraphs if p.cell is None]


def _is_toc_style(p: Paragraph) -> bool:
    """Стили «TOC N» / «Оглавление N»: обязательно с номером уровня."""
    for name in (p.style_name, p.style_id):
        m = TOC_STYLE.match((name or "").strip())
        if m and m.group(2):
            return True
    return False


def find_range(doc: Document) -> TocRange | None:
    """Диапазон абзацев оглавления: поле TOC > стили TOC N > текстовый шаблон."""
    for f in doc.fields:
        if f.kind == "TOC" and f.paragraph_idx is not None:
            last = f.paragraph_idx + f.result.count("\n")
            return TocRange("toc_field", f.paragraph_idx, min(last, len(doc.paragraphs)))
    styled = [p.idx for p in _body(doc) if _is_toc_style(p)]
    if styled:
        return TocRange("toc_styles", styled[0], styled[-1])
    return _text_pattern_range(doc)


def _text_pattern_range(doc: Document) -> TocRange | None:
    paras = _body(doc)
    for i, p in enumerate(paras):
        name = normalize_text(p.full_text)
        if classify_name(p.full_text) != "TOC" or len(name) > 40:
            continue
        first = last = None
        gap = 0
        for q in paras[i + 1 :]:
            if not q.text.strip():
                gap += 1
                if gap > _MAX_GAP:
                    break
                continue
            if not TOC_LINE_STRICT.match(q.full_text.strip()):
                break
            gap = 0
            first = q.idx if first is None else first
            last = q.idx
        if first is not None and last is not None and last - first >= 1:
            return TocRange("text_pattern", first, last)
    return None


def _parse_entry(p: Paragraph) -> TocEntry | None:
    raw = p.full_text.strip()
    if not raw:
        return None
    m = TOC_LINE.match(raw)
    text, page_text = (m.group("text"), m.group("page")) if m else (raw, None)
    if m and len(text.split()) == 1 and classify_name(text) in ("CHAPTER", "APPENDIX"):
        text, page_text = raw, None  # «Глава 1»: единица - номер главы, а не страница
    text = _TRAIL_LEADER.sub("", text.replace("\t", " ")).strip()
    if not text:
        return None
    number = None
    cm = CHAPTER_NUM.match(text)
    if cm:
        number = clean_number(cm.group("n"))
    else:
        nm = NUMBERED.match(text)
        if nm:
            number = clean_number(nm.group("n"))
    level = _level(p, number)
    page_num = None
    if page_text:
        page_num = int(page_text)
    return TocEntry(
        text=text, number=number, level=level, page_text=page_text, page_num=page_num,
        paragraph_idx=p.idx,
    )  # fmt: skip


def _level(p: Paragraph, number: str | None) -> int:
    for name in (p.style_name, p.style_id):
        m = TOC_STYLE.match((name or "").strip())
        if m and m.group(2):
            return int(m.group(2))
    return max(number_depth(number), 1)


def _key(text: str) -> str:
    return normalize_text(re.sub(r"[.\s]+$", "", text))


def _section_titles(sec: Section) -> list[str]:
    full = f"{sec.number} {sec.title}".strip() if sec.number else sec.title
    variants = [full, sec.title]
    if sec.kind == "CHAPTER" and sec.number:
        variants.append(f"глава {sec.number} {sec.title}")
    return [_key(v) for v in variants if v]


def resolve_entries(entries: list[TocEntry], sections: list[Section], th: Thresholds):
    """Сопоставление записей с разделами: точное совпадение, затем token_set_ratio >= порога."""
    from dataclasses import replace

    used: set[str] = set()
    result: list[TocEntry] = []
    for e in entries:
        ekey = _key(e.text)
        best, best_score = None, 0.0
        for s in sections:
            if s.id in used or s.kind == "TOC":
                continue
            score = max((100.0 if ekey == t else fuzz.token_set_ratio(ekey, t) for t in
                         _section_titles(s)), default=0.0)  # fmt: skip
            if e.number and s.number and e.number != s.number:
                score = min(score, 50.0)
            if score > best_score:
                best, best_score = s, score
        if best is not None and best_score >= th.TOC_MATCH_RATIO:
            used.add(best.id)
            e = replace(e, resolved_section_id=best.id)
        result.append(e)
    return result


def build_toc(doc: Document, rng: TocRange | None) -> Toc | None:
    if rng is None:
        return None
    entries = [
        e
        for p in doc.paragraphs
        if p.cell is None and rng.first <= p.idx <= rng.last
        for e in [_parse_entry(p)]
        if e is not None
    ]
    return Toc(source=rng.source, entries=tuple(entries))  # type: ignore[arg-type]
