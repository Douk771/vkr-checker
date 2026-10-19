"""Сравнение таблиц (DIF-04, ARCHITECTURE_CHECKS.md §5.5)."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from rapidfuzz import fuzz

from vkr_checker.model.document import Document, Row, Table
from vkr_checker.report.schema import CellChange, ObjectDiff, RowChange
from vkr_checker.thresholds import Thresholds

from .model import ObjectMatch
from .pairing import greedy_pairs
from .words import fold, squash


@dataclass(frozen=True)
class TableInfo:
    table: Table
    number: str | None
    title: str
    norm: str
    label: str
    cells: frozenset[str]


def table_infos(doc: Document) -> list[TableInfo]:
    result = []
    for t in doc.tables:
        if t.parent_table_idx is not None:
            continue
        has_caption = t.caption_idx is not None and 0 <= t.caption_idx < len(doc.captions)
        cap = doc.captions[t.caption_idx] if has_caption else None
        cells = frozenset(fold(c.text) for r in t.rows for c in r.cells if c.text.strip())
        result.append(
            TableInfo(
                t,
                cap.number if cap else None,
                cap.title if cap else "",
                fold(cap.title) if cap else "",
                t.number_label(doc),
                cells,
            )  # fmt: skip
        )
    return result


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def match_tables(
    old: list[TableInfo], new: list[TableInfo], th: Thresholds
) -> list[tuple[int, int]]:
    used_o: set[int] = set()
    used_n: set[int] = set()
    pairs: list[tuple[int, int]] = []

    def run(cands: list[tuple[float, int, int]]) -> None:
        pairs.extend((i, j) for i, j, _ in greedy_pairs(cands, used_o, used_n))

    run([
        (fuzz.ratio(o.norm, n.norm), i, j)
        for i, o in enumerate(old) for j, n in enumerate(new)
        if o.number is not None and o.number == n.number
        and fuzz.ratio(o.norm, n.norm) >= th.TBL_TITLE_RATIO
    ])  # fmt: skip
    run([
        (fuzz.ratio(o.norm, n.norm), i, j)
        for i, o in enumerate(old) for j, n in enumerate(new)
        if i not in used_o and j not in used_n and o.norm and n.norm
        and fuzz.ratio(o.norm, n.norm) >= th.TBL_TITLE_RATIO
    ])  # fmt: skip
    run([
        (_jaccard(o.cells, n.cells), i, j)
        for i, o in enumerate(old) for j, n in enumerate(new)
        if i not in used_o and j not in used_n
        and _jaccard(o.cells, n.cells) >= th.TBL_CONTENT_JACCARD
    ])  # fmt: skip
    return pairs


def _row_key(row: Row) -> str:
    return fold(row.cells[0].text) if row.cells else ""


def _cell_changes(old: Row, new: Row) -> list[CellChange]:
    a = {c.col: c.text for c in old.cells}
    b = {c.col: c.text for c in new.cells}
    return [
        CellChange(col=col, old=squash(a.get(col, "")), new=squash(b.get(col, "")))
        for col in sorted(set(a) | set(b))
        if fold(a.get(col, "")) != fold(b.get(col, ""))
    ]


def diff_rows(old: Table, new: Table) -> tuple[list[RowChange], list[tuple[int, int]]]:
    """Изменения строк и список изменённых ячеек новой таблицы (строка, столбец), с 1."""
    ra, rb = list(old.rows), list(new.rows)
    sm = SequenceMatcher(None, [_row_key(r) for r in ra], [_row_key(r) for r in rb], autojunk=False)
    changes: list[RowChange] = []
    cells_changed: list[tuple[int, int]] = []

    def modified(i: int, j: int) -> None:
        cc = _cell_changes(ra[i], rb[j])
        if cc:
            changes.append(RowChange(status="modified", old_row=i + 1, new_row=j + 1, cells=cc))
            cells_changed.extend((j + 1, c.col) for c in cc)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                modified(i1 + k, j1 + k)
            continue
        common = min(i2 - i1, j2 - j1) if tag == "replace" else 0
        for k in range(common):
            modified(i1 + k, j1 + k)
        changes.extend(RowChange(status="removed", old_row=i + 1) for i in range(i1 + common, i2))
        for j in range(j1 + common, j2):
            changes.append(RowChange(status="added", new_row=j + 1))
            cells_changed.extend((j + 1, c.col) for c in rb[j].cells)
    return changes, cells_changed


def _flags(o: TableInfo, n: TableInfo) -> list[str]:
    flags = []
    if o.number != n.number:
        flags.append("renumbered")
    if o.norm != n.norm:
        flags.append("retitled")
    return flags


def diff_tables(
    old_doc: Document, new_doc: Document, th: Thresholds
) -> tuple[list[ObjectDiff], list[ObjectMatch]]:
    old, new = table_infos(old_doc), table_infos(new_doc)
    pairs = match_tables(old, new, th)
    by_new = {j: i for i, j in pairs}
    matched_old = {i for i, _ in pairs}
    diffs: list[ObjectDiff] = []
    objects: list[ObjectMatch] = []
    for j, n in enumerate(new):
        if j not in by_new:
            diffs.append(ObjectDiff(status="added", flags=[], new_label=n.label, rows=[]))
            objects.append(
                ObjectMatch("table", None, n.number, None, n.label, new_table_idx=n.table.idx)
            )
            continue
        o = old[by_new[j]]
        rows, cells = diff_rows(o.table, n.table)
        diffs.append(
            ObjectDiff(
                status="modified" if rows else "unchanged",
                flags=_flags(o, n),
                old_label=o.label,
                new_label=n.label,
                rows=rows,
            )  # type: ignore[arg-type]  # fmt: skip
        )
        objects.append(
            ObjectMatch(
                "table",
                o.number,
                n.number,
                o.label,
                n.label,
                tuple((n.table.idx, r, c) for r, c in cells),
                n.table.idx,
            )  # fmt: skip
        )
    for i, o in enumerate(old):
        if i not in matched_old:
            diffs.append(ObjectDiff(status="removed", flags=[], old_label=o.label, rows=[]))
            objects.append(ObjectMatch("table", o.number, None, o.label, None))
    return diffs, objects
