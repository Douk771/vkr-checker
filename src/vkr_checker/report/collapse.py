"""Схлопывание однотипных находок (ARCHITECTURE_CHECKS.md §8.2).

Ключ - (rule_id, fingerprint, level, not_run): правило строит fingerprint из объекта и подвида
без координат ячеек, поэтому «красная строка в 42 ячейках» таблицы 3 даёт одну находку.
"""

from __future__ import annotations

from vkr_checker.model.finding import Finding, Location

LEVEL_RANK = {"violation": 0, "suspicion": 1, "not_checked": 2}


def describe_location(loc: Location) -> str:
    """Краткое место для values.all_cells: «Таблица 3, строка 2, столбец 1» | «абзац 12»."""
    if loc.table is not None:
        parts = [loc.table.number_label]
        if loc.table.row is not None:
            parts.append(f"строка {loc.table.row}")
        if loc.table.col is not None:
            parts.append(f"столбец {loc.table.col}")
        return ", ".join(parts)
    if loc.paragraph_idx is not None:
        return f"абзац {loc.paragraph_idx}"
    return loc.quote[:40]


def _merge(group: list[Finding], show: int) -> Finding:
    first = group[0]
    total = sum(f.count for f in group)
    locations: list[Location] = [loc for f in group for loc in f.locations]
    values = dict(first.values)
    if len(group) > 1:
        values["all_cells"] = [describe_location(loc) for loc in locations]
    return first.model_copy(
        update={
            "count": total,
            "message": first.message.replace("{count}", str(total)),
            "locations": locations[:show],
            "values": values,
        }
    )


def collapse_findings(findings: list[Finding], show_locations: int) -> list[Finding]:
    """Объединяет находки с одинаковым ключом; порядок групп - по первому появлению."""
    groups: dict[tuple, list[Finding]] = {}
    for f in findings:
        groups.setdefault((f.rule_id, f.fingerprint, f.level, f.not_run), []).append(f)
    return [_merge(g, show_locations) for g in groups.values()]
