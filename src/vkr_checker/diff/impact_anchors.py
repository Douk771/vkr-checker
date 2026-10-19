"""DIF-05.2: якоря введения и их отражения в тексте новой версии."""

from __future__ import annotations

from vkr_checker.checks.facts.common import paragraphs_in
from vkr_checker.checks.tasks import _prepare, match_greedy
from vkr_checker.model.finding import Finding
from vkr_checker.nlp.morph import content_lemma_set, jaccard

from .impact_base import ImpactInput, finding

SINGLE = {"goal": "цель", "object": "объект", "subject": "предмет"}
SHARED_MIN = 2


def _intro_text(side, key: str) -> str:
    return " ".join(e.text for e in side.ctx.facts.intro_elements.get(key, []) if e.text)


def _changed(old: str, new: str, limit: float) -> bool:
    if not old.strip() or not new.strip():
        return False
    return jaccard(content_lemma_set(old), content_lemma_set(new)) < limit


def _conclusion_paragraphs(side) -> list[int]:
    sec = next((s for s in side.doc.sections if s.kind == "CONCLUSION"), None)
    return [
        p.idx
        for p in paragraphs_in(side.doc, sec)
        if p.idx != getattr(sec, "heading_paragraph_idx", 0)
    ]


def _hypothesis_reflections(inp: ImpactInput) -> list[int]:
    return [
        m.loc.paragraph_idx for m in inp.new.ctx.facts.hypothesis_mentions if m.loc.paragraph_idx
    ]


def _task_reflections(inp: ImpactInput) -> list[int]:
    facts = inp.new.ctx.facts
    tasks, concl = _prepare(facts.tasks), _prepare(facts.conclusions)
    matched, _ = match_greedy(tasks, concl, inp.new.ctx.th.TSK_MATCH_MIN)
    result = [concl[j].item.paragraph_idx for j, _ in matched.values()]
    for items in facts.chapter_conclusions.values():
        result.extend(it.paragraph_idx for it in items)
    return result


def _shared_reflections(inp: ImpactInput, old_text: str) -> list[int]:
    keys = content_lemma_set(old_text)
    result = []
    for idx in _conclusion_paragraphs(inp.new):
        if len(keys & content_lemma_set(inp.new.doc.paragraph(idx).text)) >= SHARED_MIN:
            result.append(idx)
    return result


def _anchor_locations(inp: ImpactInput, key: str):
    elements = inp.new.ctx.facts.intro_elements.get(key, [])
    if not elements:
        return []
    e = elements[0]
    return [inp.new.ctx.loc.paragraph(e.paragraph_idx, e.span)]


def impact_anchors(inp: ImpactInput) -> list[Finding]:
    limit = inp.new.ctx.th.ANCHOR_CHANGED
    out: list[Finding] = []
    unchanged, changed = inp.state.unchanged_new, inp.state.changed_new
    old_f, new_f = inp.old.ctx.facts, inp.new.ctx.facts

    anchors: list[tuple[str, str, str, str, list[int]]] = []  # key, title, old, new, reflections
    old_h = " ".join(p.text for p in old_f.hypotheses)
    new_h = " ".join(p.text for p in new_f.hypotheses)
    anchors.append(("hypothesis", "гипотеза", old_h, new_h, _hypothesis_reflections(inp)))
    old_t = " ".join(i.text for i in old_f.tasks)
    new_t = " ".join(i.text for i in new_f.tasks)
    anchors.append(("tasks", "задачи", old_t, new_t, _task_reflections(inp)))
    for key, name in SINGLE.items():
        old_s, new_s = _intro_text(inp.old, key), _intro_text(inp.new, key)
        anchors.append((key, name, old_s, new_s, _shared_reflections(inp, old_s)))

    for key, name, old_text, new_text, reflections in anchors:
        reflected = sorted(set(reflections))
        if _changed(old_text, new_text, limit):
            stale = [i for i in reflected if i in unchanged]
            if stale:
                out.append(finding(
                    "DIF-05.2",
                    f"Во введении изменилось: {name}. Места, где это отражено, остались прежними.",
                    f"{key}|forward",
                    _anchor_locations(inp, key) + [inp.new.ctx.loc.paragraph(i) for i in stale[:5]],
                    values={"anchor": key, "unsynced": len(stale)},
                    hint="Проверьте, согласуются ли выводы и заключение с новой формулировкой.",
                    method="morph",
                ))  # fmt: skip
        elif old_text.strip() and new_text.strip():
            moved = [i for i in reflected if i in changed]
            if moved:
                out.append(finding(
                    "DIF-05.2",
                    f"Изменились места, где отражено: {name}, а во введении оно прежнее.",
                    f"{key}|reverse",
                    [inp.new.ctx.loc.paragraph(i) for i in moved[:5]] + _anchor_locations(inp, key),
                    values={"anchor": key, "changed_places": len(moved)},
                    hint="Проверьте, не нужно ли обновить введение.",
                    method="morph",
                ))  # fmt: skip
    return out
