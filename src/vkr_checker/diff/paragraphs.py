"""Сравнение абзацев пары разделов (DIF-01, ARCHITECTURE_CHECKS.md §5.2)."""

from __future__ import annotations

from difflib import SequenceMatcher

from rapidfuzz import fuzz

from vkr_checker.model.document import Paragraph
from vkr_checker.report.schema import ParagraphDiff
from vkr_checker.thresholds import Thresholds

from .words import squash, word_segments


def _inserted(p: Paragraph) -> ParagraphDiff:
    return ParagraphDiff(status="inserted", new_idx=p.idx, text=p.text)


def _deleted(p: Paragraph) -> ParagraphDiff:
    return ParagraphDiff(status="deleted", old_idx=p.idx, text=p.text)


def _modified(old: Paragraph, new: Paragraph) -> ParagraphDiff:
    return ParagraphDiff(
        status="modified",
        old_idx=old.idx,
        new_idx=new.idx,
        segments=word_segments(old.text, new.text),
    )


def _pair_block(old: list[Paragraph], new: list[Paragraph], th: Thresholds) -> list[ParagraphDiff]:
    """Блок replace: монотонное сопоставление похожих абзацев, остальное deleted/inserted."""
    out: list[ParagraphDiff] = []
    cursor = 0
    for o in old:
        best_j, best_score = -1, 0.0
        for j in range(cursor, min(len(new), cursor + th.PARA_PAIR_WINDOW)):
            score = fuzz.ratio(squash(o.text), squash(new[j].text))
            if score > best_score:
                best_j, best_score = j, score
        if best_j >= 0 and best_score >= th.PARA_MODIFIED_RATIO:
            out.extend(_inserted(p) for p in new[cursor:best_j])
            out.append(_modified(o, new[best_j]))
            cursor = best_j + 1
        else:
            out.append(_deleted(o))
    out.extend(_inserted(p) for p in new[cursor:])
    return out


def diff_paragraphs(
    old: list[Paragraph], new: list[Paragraph], th: Thresholds
) -> list[ParagraphDiff]:
    """Полный список операций над абзацами пары разделов в порядке новой версии."""
    a = [squash(p.text) for p in old]
    b = [squash(p.text) for p in new]
    out: list[ParagraphDiff] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.extend(
                ParagraphDiff(status="unchanged", old_idx=o.idx, new_idx=n.idx, text=n.text)
                for o, n in zip(old[i1:i2], new[j1:j2], strict=True)
            )
        elif tag == "delete":
            out.extend(_deleted(p) for p in old[i1:i2])
        elif tag == "insert":
            out.extend(_inserted(p) for p in new[j1:j2])
        else:
            out.extend(_pair_block(old[i1:i2], new[j1:j2], th))
    return out
