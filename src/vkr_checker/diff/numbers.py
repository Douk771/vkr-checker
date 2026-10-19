"""Изменения чисел в изменённых и перенесённых абзацах (DIF-03, §5.4)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from vkr_checker.nlp.normalize import normalize_number
from vkr_checker.nlp.sentences import split_sentences
from vkr_checker.report.schema import NumberChange
from vkr_checker.thresholds import Thresholds

from .model import Side, TypedNumberChange

_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+|[^\w\s]")
_STAT_BEFORE = re.compile(r"(?<![A-Za-zА-Яа-я])(p|r|rs|U|t|F|H|χ2|χ²|d|M|SD)\s*[=<>≤≥]\s*$")
CONTEXT_MAX = 200


def _tokens(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(text)]


def _is_number(tok: str) -> bool:
    return tok[0].isdigit()


def _context(text: str, pos: int) -> str:
    for s in split_sentences(text):
        if s.start <= pos < s.end:
            return s.text.strip().rstrip(".")[:CONTEXT_MAX]
    return text[:CONTEXT_MAX]


def _quantity_at(side: Side, paragraph_idx: int, span: tuple[int, int]):
    for q in side.ctx.facts.quantities:
        if q.loc.paragraph_idx != paragraph_idx or q.loc.cell is not None:
            continue
        if q.loc.span[0] < span[1] and span[0] < q.loc.span[1]:
            return q
    return None


def _stat_kind(text: str, start: int) -> str | None:
    m = _STAT_BEFORE.search(text[max(0, start - 12) : start])
    return m.group(1) if m else None


def _changes_in_pair(old: Side, new: Side, old_idx: int, new_idx: int) -> list[TypedNumberChange]:
    old_text, new_text = old.doc.paragraph(old_idx).text, new.doc.paragraph(new_idx).text
    a, b = _tokens(old_text), _tokens(new_text)
    mask_a = ["#" if _is_number(t[0]) else t[0].lower() for t in a]
    mask_b = ["#" if _is_number(t[0]) else t[0].lower() for t in b]
    out: list[TypedNumberChange] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, mask_a, mask_b, autojunk=False).get_opcodes():
        if tag != "equal":
            continue
        for ta, tb in zip(a[i1:i2], b[j1:j2], strict=True):
            if not _is_number(ta[0]) or ta[0] == tb[0]:
                continue
            span_a, span_b = (ta[1], ta[2]), (tb[1], tb[2])
            qa = _quantity_at(old, old_idx, span_a)
            qb = _quantity_at(new, new_idx, span_b)
            typed = qa is not None and qb is not None and qa.key == qb.key and qa.value != qb.value
            kind = qb.kind if typed else _stat_kind(new_text, tb[1])
            api = NumberChange(
                old=ta[0],
                new=tb[0],
                kind=kind,
                context=_context(old_text, ta[1]),
                loc_old=old.ctx.loc.paragraph(old_idx, span_a),
                loc_new=new.ctx.loc.paragraph(new_idx, span_b),
            )
            out.append(
                TypedNumberChange(
                    api,
                    new_idx,
                    qb.key if typed else None,
                    qa.value if typed else normalize_number(ta[0]),
                )  # fmt: skip
            )
    return out


def find_number_changes(
    old: Side, new: Side, pairs: list[tuple[int, int]], th: Thresholds
) -> list[TypedNumberChange]:
    """pairs: (old_idx, new_idx) изменённых и перенесённых абзацев. Типизированные идут первыми."""
    result: list[TypedNumberChange] = []
    for old_idx, new_idx in pairs:
        result.extend(_changes_in_pair(old, new, old_idx, new_idx))
        if len(result) >= th.MAX_NUMBER_CHANGES:
            break
    rank = lambda c: 0 if c.key else (1 if c.api.kind else 2)  # noqa: E731
    return sorted(result[: th.MAX_NUMBER_CHANGES], key=rank)
