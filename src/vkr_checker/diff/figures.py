"""Сравнение рисунков по подписям (DIF-04, без содержимого)."""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from vkr_checker.model.document import Document
from vkr_checker.report.schema import ObjectDiff
from vkr_checker.thresholds import Thresholds

from .model import ObjectMatch
from .pairing import greedy_pairs
from .words import fold


@dataclass(frozen=True)
class FigureInfo:
    number: str
    norm: str
    label: str


def figure_infos(doc: Document) -> list[FigureInfo]:
    return [
        FigureInfo(c.number, fold(c.title), f"Рисунок {c.number}")
        for c in doc.captions
        if c.kind == "figure"
    ]


def diff_figures(
    old_doc: Document, new_doc: Document, th: Thresholds
) -> tuple[list[ObjectDiff], list[ObjectMatch]]:
    old, new = figure_infos(old_doc), figure_infos(new_doc)
    used_o: set[int] = set()
    used_n: set[int] = set()
    pairs = greedy_pairs(
        [
            (fuzz.ratio(o.norm, n.norm), i, j)
            for i, o in enumerate(old)
            for j, n in enumerate(new)
            if o.number == n.number and fuzz.ratio(o.norm, n.norm) >= th.TBL_TITLE_RATIO
        ],
        used_o,
        used_n,
    )
    pairs += greedy_pairs(
        [
            (fuzz.ratio(o.norm, n.norm), i, j)
            for i, o in enumerate(old)
            for j, n in enumerate(new)
            if i not in used_o and j not in used_n and o.norm and n.norm
            and fuzz.ratio(o.norm, n.norm) >= th.TBL_TITLE_RATIO
        ],
        used_o,
        used_n,
    )  # fmt: skip
    by_new = {j: i for i, j, _ in pairs}
    diffs: list[ObjectDiff] = []
    objects: list[ObjectMatch] = []
    for j, n in enumerate(new):
        if j not in by_new:
            diffs.append(ObjectDiff(status="added", flags=[], new_label=n.label, rows=[]))
            objects.append(ObjectMatch("figure", None, n.number, None, n.label))
            continue
        o = old[by_new[j]]
        flags = (["renumbered"] if o.number != n.number else []) + (
            ["retitled"] if o.norm != n.norm else []
        )
        diffs.append(
            ObjectDiff(
                status="unchanged", flags=flags, old_label=o.label, new_label=n.label, rows=[]
            )  # type: ignore[arg-type]
        )
        objects.append(ObjectMatch("figure", o.number, n.number, o.label, n.label))
    for i, o in enumerate(old):
        if i not in used_o:
            diffs.append(ObjectDiff(status="removed", flags=[], old_label=o.label, rows=[]))
            objects.append(ObjectMatch("figure", o.number, None, o.label, None))
    return diffs, objects
