"""Жадное попарное сопоставление по убыванию оценки (при равенстве - меньший индекс)."""

from __future__ import annotations

from collections.abc import Iterable


def greedy_pairs(
    candidates: Iterable[tuple[float, int, int]],
    used_old: set[int],
    used_new: set[int],
) -> list[tuple[int, int, float]]:
    """candidates: (оценка, индекс старого, индекс нового). Обновляет used_*."""
    result: list[tuple[int, int, float]] = []
    for score, i, j in sorted(candidates, key=lambda c: (-c[0], c[1], c[2])):
        if i in used_old or j in used_new:
            continue
        used_old.add(i)
        used_new.add(j)
        result.append((i, j, score))
    return result
