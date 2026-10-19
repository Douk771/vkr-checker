"""Перемещения абзацев между разделами (DIF-02, ARCHITECTURE_CHECKS.md §5.3)."""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from vkr_checker.model.document import Document
from vkr_checker.report.schema import Move, ParagraphDiff
from vkr_checker.thresholds import Thresholds

from .sections import SectionMatch, diffable_paragraphs
from .words import fold, squash, word_segments


@dataclass(frozen=True)
class MovedPair:
    old_idx: int
    new_idx: int
    old_text: str
    new_text: str


@dataclass(frozen=True)
class _Ref:
    match: int  # позиция в списке SectionMatch
    pos: int  # позиция абзаца в match.paragraphs

    def get(self, matches: list[SectionMatch]) -> ParagraphDiff:
        return matches[self.match].paragraphs[self.pos]


def _title(unit) -> str:
    return unit.title if unit is not None else ""


def _ordinals(doc: Document) -> dict[int, int]:
    return {p.idx: n for n, p in enumerate(diffable_paragraphs(doc))}


def _find_pairs(matches: list[SectionMatch], th: Thresholds) -> list[tuple[_Ref, _Ref]]:
    deleted = [
        _Ref(m, k)
        for m, sm in enumerate(matches)
        for k, p in enumerate(sm.paragraphs)
        if p.status == "deleted"
    ]
    inserted = [
        _Ref(m, k)
        for m, sm in enumerate(matches)
        for k, p in enumerate(sm.paragraphs)
        if p.status == "inserted"
    ]
    texts = {r: fold(r.get(matches).text or "") for r in [*deleted, *inserted]}
    free = list(inserted)
    pairs: list[tuple[_Ref, _Ref]] = []
    for d in deleted:
        dt = texts[d]
        if len(squash(dt)) < th.MOVE_MIN_CHARS or not free:
            continue
        lo, hi = len(dt) * (1 - th.MOVE_LEN_TOL), len(dt) * (1 + th.MOVE_LEN_TOL)
        pool = [r for r in free if lo <= len(texts[r]) <= hi]
        if not pool:
            continue
        found = process.extractOne(
            dt, [texts[r] for r in pool], scorer=fuzz.ratio, score_cutoff=th.MOVE_RATIO * 100
        )
        if found is None:
            continue
        target = pool[found[2]]
        free.remove(target)
        pairs.append((d, target))
    return pairs


def _groups(
    pairs: list[tuple[_Ref, _Ref]],
    matches: list[SectionMatch],
    old_ord: dict[int, int],
    new_ord: dict[int, int],
) -> list[list[tuple[_Ref, _Ref]]]:
    """Подряд идущие перемещения в подряд идущие цели склеиваются в одну запись."""

    def key(pair):
        d, i = pair
        return (old_ord.get(d.get(matches).old_idx, -1), new_ord.get(i.get(matches).new_idx, -1))

    groups: list[list[tuple[_Ref, _Ref]]] = []
    for pair in sorted(pairs, key=key):
        if groups:
            prev = groups[-1][-1]
            (po, pn), (co, cn) = key(prev), key(pair)
            if (
                co == po + 1
                and cn == pn + 1
                and prev[0].match == pair[0].match
                and prev[1].match == pair[1].match
            ):
                groups[-1].append(pair)
                continue
        groups.append([pair])
    return groups


def detect_moves(
    matches: list[SectionMatch],
    old_doc: Document,
    new_doc: Document,
    th: Thresholds,
) -> tuple[list[Move], list[MovedPair]]:
    """Заменяет deleted/inserted на moved_out/moved_in прямо в `matches`."""
    pairs = _find_pairs(matches, th)
    groups = _groups(pairs, matches, _ordinals(old_doc), _ordinals(new_doc))
    moves: list[Move] = []
    moved: list[MovedPair] = []
    for n, group in enumerate(groups, 1):
        move_id = f"m{n}"
        old_idx: list[int] = []
        new_idx: list[int] = []
        old_texts: list[str] = []
        new_texts: list[str] = []
        for d, i in group:
            dp, ip = d.get(matches), i.get(matches)
            old_idx.append(dp.old_idx or 0)
            new_idx.append(ip.new_idx or 0)
            old_texts.append(dp.text or "")
            new_texts.append(ip.text or "")
            moved.append(MovedPair(dp.old_idx or 0, ip.new_idx or 0, dp.text or "", ip.text or ""))
            matches[d.match].paragraphs[d.pos] = dp.model_copy(
                update={"status": "moved_out", "move_id": move_id}
            )
            matches[i.match].paragraphs[i.pos] = ip.model_copy(
                update={"status": "moved_in", "move_id": move_id}
            )
        first_d, first_i = group[0]
        moves.append(
            Move(
                id=move_id,
                from_section=_title(matches[first_d.match].old),
                to_section=_title(matches[first_i.match].new),
                old_idx=old_idx,
                new_idx=new_idx,
                segments=word_segments("\n".join(old_texts), "\n".join(new_texts)),
            )
        )
    return moves, moved
