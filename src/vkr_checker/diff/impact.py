"""Анализ последствий правок (DIF-05.1-6, ARCHITECTURE_CHECKS.md §5.6)."""

from __future__ import annotations

from vkr_checker.checks.facts.common import chapter_number
from vkr_checker.checks.numbering import _COUNT, _PHRASE_VERB, _count_main
from vkr_checker.checks.rulehelpers import in_section_tree, mention_location, section_id_of
from vkr_checker.model.finding import Finding
from vkr_checker.nlp.lexicons.methods import METHODS
from vkr_checker.nlp.sentences import split_sentences

from .impact_anchors import impact_anchors
from .impact_base import ImpactInput, assign_ids, finding
from .model import DiffState, Side

SHOW = 5


def _norm_no(value: str | None) -> str:
    return (value or "").replace(",", ".").upper()


def impact_numbers(inp: ImpactInput) -> list[Finding]:
    """DIF-05.1: число изменено, а старое значение осталось в неизменённом абзаце."""
    out: list[Finding] = []
    quantities = inp.new.ctx.facts.quantities
    for ch in inp.state.number_changes:
        if ch.key is None or ch.old_value is None:
            continue
        stale = [
            q for q in quantities
            if q.key == ch.key and q.value == ch.old_value
            and q.loc.paragraph_idx in inp.state.unchanged_new
        ]  # fmt: skip
        if not stale:
            continue
        where = ch.api.loc_new or ch.api.loc_old
        out.append(finding(
            "DIF-05.1",
            f"Значение изменено с {ch.api.old} на {ch.api.new}, но в тексте осталось старое "
            f"значение ({len(stale)} мест).",
            f"{ch.key[0]}|{ch.key[1]}|{ch.old_value}|{ch.api.new}",
            ([where] if where else [])
            + [mention_location(inp.new.ctx, q.loc) for q in stale[:SHOW]],
            values={
                "old": ch.api.old, "new": ch.api.new, "kind": ch.key[0], "unsynced": len(stale),
            },
            hint="Приведите все упоминания к одному значению.",
            method="regex",
        ))  # fmt: skip
    return out


def _methods_scope(side: Side) -> set[str]:
    """Методы, названные во введении и в параграфе 2.1."""
    ctx = side.ctx
    sec21 = next((s for s in ctx.doc.sections if s.number == "2.1"), None)
    found: set[str] = set()
    for m in ctx.facts.methods:
        if m.section_kind == "INTRO":
            found.add(m.method_id)
        elif sec21 is not None and in_section_tree(ctx, section_id_of(ctx, m.loc), sec21.id):
            found.add(m.method_id)
    return found


def impact_methods(inp: ImpactInput) -> list[Finding]:
    """DIF-05.3: метод убран из введения и 2.1, но упоминается в новой версии."""
    removed = _methods_scope(inp.old) - _methods_scope(inp.new)
    out: list[Finding] = []
    for method_id in sorted(removed):
        mentions = [m for m in inp.new.ctx.facts.methods if m.method_id == method_id]
        if not mentions:
            continue
        title = METHODS[method_id].title if method_id in METHODS else method_id
        out.append(finding(
            "DIF-05.3",
            f"Метод «{title}» убран из введения и параграфа 2.1, но упоминается в тексте "
            f"({len(mentions)} мест).",
            method_id,
            [mention_location(inp.new.ctx, m.loc) for m in mentions[:SHOW]],
            values={"method": method_id, "mentions": len(mentions)},
            hint="Уберите упоминания или верните метод в описание.",
            method="regex",
        ))  # fmt: skip
    return out


def impact_references(inp: ImpactInput) -> list[Finding]:
    """DIF-05.4: объект удалён или перенумерован, а ссылки в неизменённых абзацах прежние."""
    out: list[Finding] = []
    refs = inp.new.ctx.facts.refs
    for obj in inp.state.objects:
        if not (obj.removed or obj.renumbered) or obj.old_no is None:
            continue
        stale = [
            r for r in refs
            if r.kind == obj.kind and _norm_no(r.target) == _norm_no(obj.old_no)
            and r.loc.paragraph_idx in inp.state.unchanged_new
        ]  # fmt: skip
        if not stale:
            continue
        what = "удалена" if obj.removed else f"теперь имеет номер {obj.new_no}"
        out.append(finding(
            "DIF-05.4",
            f"{obj.old_label}: {what}, но ссылка в тексте, вероятно, на старый номер "
            f"({len(stale)} мест).",
            f"{obj.kind}|{_norm_no(obj.old_no)}|{_norm_no(obj.new_no)}",
            [mention_location(inp.new.ctx, r.loc) for r in stale[:SHOW]],
            values={"old_no": obj.old_no, "new_no": obj.new_no, "unsynced": len(stale)},
            hint="Проверьте номера в ссылках.",
            method="regex",
        ))  # fmt: skip
    return out


def _phrase_paragraphs(side: Side) -> list[int]:
    found: list[int] = []
    for p in side.doc.paragraphs:
        if p.cell is not None:
            continue
        if any(
            _PHRASE_VERB.search(s.text) and _COUNT.search(s.text) for s in split_sentences(p.text)
        ):
            found.append(p.idx)
    return found


def impact_totals(inp: ImpactInput) -> list[Finding]:
    """DIF-05.5: число таблиц или рисунков изменилось, а фраза о числе объектов нет."""
    old_n, new_n = _count_main(inp.old.ctx), _count_main(inp.new.ctx)
    diff = {k: (old_n[k], new_n[k]) for k in ("table", "figure") if old_n[k] != new_n[k]}
    if not diff:
        return []
    phrases = [i for i in _phrase_paragraphs(inp.new) if i in inp.state.unchanged_new]
    if not phrases:
        return []
    names = {"table": "таблиц", "figure": "рисунков"}
    parts = ", ".join(f"{names[k]}: было {a}, стало {b}" for k, (a, b) in diff.items())
    return [finding(
        "DIF-05.5",
        f"Число объектов изменилось ({parts}), а фраза о числе рисунков и таблиц осталась прежней.",
        "totals",
        [inp.new.ctx.loc.paragraph(i) for i in phrases[:SHOW]],
        values={k: {"old": a, "new": b} for k, (a, b) in diff.items()},
        hint="Обновите фразу о числе рисунков и таблиц.",
        method="count",
    )]  # fmt: skip


def impact_conclusions(inp: ImpactInput) -> list[Finding]:
    """DIF-05.6: изменены расчёты главы 2, а выводы к ней и заключение не тронуты."""
    new = inp.new
    doc = new.doc
    ch2 = lambda sid: chapter_number(doc, sid) == 2  # noqa: E731
    cells = [
        (t_idx, r, c)
        for obj in inp.state.objects
        for (t_idx, r, c) in obj.changed_cells
        if ch2(doc.table(t_idx).section_id)
    ]
    numbers = [
        ch for ch in inp.state.number_changes
        if ch.key is not None and ch2(doc.paragraph(ch.new_idx).section_id)
    ]  # fmt: skip
    if not cells and not numbers:
        return []
    facts = new.ctx.facts
    concl = {i.paragraph_idx for i in facts.conclusions}
    for items in facts.chapter_conclusions.values():
        concl.update(
            i.paragraph_idx for i in items if ch2(doc.paragraph(i.paragraph_idx).section_id)
        )
    if not concl or not concl <= inp.state.unchanged_new:
        return []
    places = [new.ctx.loc.cell(t, r, c) for t, r, c in cells[:SHOW]]
    places += [n.api.loc_new for n in numbers[:SHOW] if n.api.loc_new]
    places += [new.ctx.loc.paragraph(sorted(concl)[0])]
    return [finding(
        "DIF-05.6",
        f"В главе 2 изменены расчёты (ячеек таблиц: {len(cells)}, чисел: {len(numbers)}), "
        "а выводы к ней и заключение остались прежними. Проверьте, держатся ли выводы.",
        "ch2",
        places,
        values={"changed_cells": len(cells), "changed_numbers": len(numbers)},
        method="count",
    )]  # fmt: skip


def analyze_impact(old: Side, new: Side, state: DiffState, th: object = None) -> list[Finding]:
    inp = ImpactInput(old, new, state, th)
    findings: list[Finding] = []
    for step in (
        impact_numbers, impact_anchors, impact_methods, impact_references,
        impact_totals, impact_conclusions,
    ):  # fmt: skip
        findings.extend(step(inp))
    findings.sort(key=lambda f: (f.rule_id, f.fingerprint))
    return assign_ids(findings)
