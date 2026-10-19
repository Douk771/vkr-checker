"""Сборка DiffReport и CompareReport из двух проанализированных версий (B-60..B-64)."""

from __future__ import annotations

from datetime import datetime

from vkr_checker.report.schema import (
    SCHEMA_VERSION,
    CompareOld,
    CompareReport,
    DiffReport,
    SectionDiff,
)
from vkr_checker.thresholds import DEFAULT_THRESHOLDS, Thresholds

from .dynamics import build_dynamics
from .figures import diff_figures
from .impact import analyze_impact
from .model import DiffState, Side
from .moves import detect_moves
from .numbers import find_number_changes
from .sections import SectionMatch, align_sections
from .tables import diff_tables

CHANGED_ON_NEW = ("modified", "inserted", "moved_in")


def _section_diff(m: SectionMatch) -> SectionDiff:
    old_title = m.old.title if m.old else None
    new_title = m.new.title if m.new else None
    changed = any(p.status != "unchanged" for p in m.paragraphs)
    if m.old is None or m.new is None:
        status, basis = ("added" if m.old is None else "removed"), None
    elif m.basis != "exact":
        status, basis = "renamed", m.basis
    else:
        status, basis = ("modified" if changed else "unchanged"), None
    shown = m.paragraphs if (changed or status in ("added", "removed")) else []
    return SectionDiff(
        status=status,  # type: ignore[arg-type]
        rename_basis=basis,  # type: ignore[arg-type]
        old_title=old_title,
        new_title=new_title,
        paragraphs=list(shown),
    )


def build_diff(old: Side, new: Side, th: Thresholds = DEFAULT_THRESHOLDS) -> DiffReport:
    matches = align_sections(old.doc, new.doc, th)
    moves, moved_pairs = detect_moves(matches, old.doc, new.doc, th)

    state = DiffState()
    pairs: list[tuple[int, int]] = []
    for m in matches:
        for p in m.paragraphs:
            if p.new_idx is None:
                continue
            if p.status == "unchanged":
                state.unchanged_new.add(p.new_idx)
            elif p.status in CHANGED_ON_NEW:
                state.changed_new.add(p.new_idx)
            if p.status == "modified" and p.old_idx is not None:
                pairs.append((p.old_idx, p.new_idx))
    pairs.extend((mp.old_idx, mp.new_idx) for mp in moved_pairs)

    state.number_changes = find_number_changes(old, new, pairs, th)
    table_diffs, table_objects = diff_tables(old.doc, new.doc, th)
    figure_diffs, figure_objects = diff_figures(old.doc, new.doc, th)
    state.objects = [*table_objects, *figure_objects]

    return DiffReport(
        sections=[_section_diff(m) for m in matches],
        moves=moves,
        number_changes=[c.api for c in state.number_changes],
        tables=table_diffs,
        figures=figure_diffs,
        impact=analyze_impact(old, new, state),
        dynamics=build_dynamics(old.report, new.report),
    )


def build_compare_report(
    old: Side,
    new: Side,
    *,
    service_version: str,
    checked_at: datetime,
    th: Thresholds = DEFAULT_THRESHOLDS,
) -> CompareReport:
    return CompareReport(
        schema_version=SCHEMA_VERSION,  # type: ignore[arg-type]
        service_version=service_version,
        checked_at=checked_at,
        old=CompareOld(file=old.report.file, layout=old.report.layout, summary=old.report.summary),
        new=new.report,
        diff=build_diff(old, new, th),
    )
