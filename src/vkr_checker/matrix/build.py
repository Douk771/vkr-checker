"""Матрица связности (MAT-01, ARCHITECTURE_CHECKS.md §7): строки из фактов, ячейки автоматически."""

from __future__ import annotations

import re

from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.facts.hypothesis import STATUS_TITLES, HypothesisPart
from vkr_checker.checks.facts.tasks import ListItem
from vkr_checker.checks.rulehelpers import mention_location
from vkr_checker.checks.tasks import _prepare, match_greedy
from vkr_checker.nlp.morph import content_lemma_set, jaccard
from vkr_checker.report.schema import Matrix, MatrixCell, MatrixCells, MatrixRow, MatrixStats

from .cells import (
    TheoryIndex,
    auto,
    find_calculation,
    find_instrument,
    find_result,
    gap,
    not_required,
    short,
)

_THEORETICAL = re.compile(
    r"проанализир\w*\s+(?:\w+\s+){0,3}литератур|теоретическ\w+\s+(?:обоснова|анализ)|"
    r"раскры\w+\s+(?:\w+\s+){0,2}(?:понят|сущност|содержан)|изуч\w+\s+теоретическ|"
    r"обобщ\w+\s+(?:\w+\s+){0,2}(?:подход|литератур)",
    re.IGNORECASE,
)
WARN_NO_HYPOTHESIS = (
    "Гипотеза во введении не найдена: строки для частей гипотезы не построены (правило HYP-01)."
)
WARN_NO_TASKS = "Задачи во введении не найдены: строки для задач не построены (правило TSK-01)."
WARN_NO_DEFENSE = "Положения на защиту не найдены: соответствующих строк нет."
WARN_NO_THEORY = "В главе 1 не найдены подразделы: столбец «Теория» не заполнен."
WARN_NO_INSTRUMENTS = "Методики в параграфе 2.1 не распознаны: столбец «Методика» не заполнен."
WARN_ERROR = "Матрица связности не построена из-за внутренней ошибки."


def is_theoretical(statement: str) -> bool:
    return bool(_THEORETICAL.search(statement))


def _best_item(text: str, items: list[ListItem], min_sim: float) -> ListItem | None:
    keys = content_lemma_set(text)
    best, best_sim = None, 0.0
    for it in items:
        sim = jaccard(keys, content_lemma_set(it.text)) if keys else 0.0
        if sim > best_sim:
            best, best_sim = it, sim
    return best if best is not None and best_sim >= min_sim else None


def _chapter_items(ctx: CheckContext) -> list[ListItem]:
    return [it for items in ctx.facts.chapter_conclusions.values() for it in items]


def _conclusion_cell(ctx: CheckContext, main: ListItem | None, statement: str) -> MatrixCell:
    min_sim = ctx.th.TSK_MATCH_MIN
    extra = _best_item(statement, _chapter_items(ctx), min_sim)
    texts, where = [], []
    if main is not None:
        texts.append(f"Заключение, вывод {main.index}: {short(main.text)}")
        where.append(ctx.loc.paragraph(main.paragraph_idx, main.span))
    if extra is not None:
        texts.append(f"выводы к главе: {short(extra.text)}")
        where.append(ctx.loc.paragraph(extra.paragraph_idx, extra.span))
    return auto("; ".join(texts), where) if texts else gap()


def _hypothesis_conclusion(ctx: CheckContext, part: HypothesisPart) -> MatrixCell:
    mentions = ctx.facts.hypothesis_mentions
    for kind in ("CONCLUSION", "CHAPTER_CONCLUSIONS"):
        scoped = [m for m in mentions if m.section_kind == kind]
        if not scoped:
            continue
        keys = content_lemma_set(part.text)
        best = max(scoped, key=lambda m: jaccard(keys, content_lemma_set(m.text)))
        status = STATUS_TITLES.get(best.status or "", "статус не указан")
        where = "Заключение" if kind == "CONCLUSION" else "Выводы к главе"
        return auto(f"{where}: гипотеза {status}", [mention_location(ctx, best.loc)])
    return gap()


def _row(ctx, kind, label, statement, loc, theory, task_map, part=None, item=None) -> MatrixRow:
    keys = set(content_lemma_set(statement))
    theoretical = is_theoretical(statement)
    calc_cell, fragment = (not_required(), None) if theoretical else find_calculation(ctx, keys)
    if kind == "hypothesis_part" and part is not None:
        conclusion = _hypothesis_conclusion(ctx, part)
    elif kind == "task" and item is not None:
        conclusion = _conclusion_cell(ctx, task_map.get(item.index), statement)
    else:
        main = _best_item(statement, ctx.facts.conclusions, ctx.th.TSK_MATCH_MIN)
        conclusion = _conclusion_cell(ctx, main, statement)
    return MatrixRow(
        kind=kind,
        label=label,
        statement=statement,
        statement_loc=loc,
        is_theoretical=theoretical,
        cells=MatrixCells(
            theory=theory.find(keys) if theory else gap(),
            instrument=not_required() if theoretical else find_instrument(ctx, keys),
            calculation=calc_cell,
            result=not_required() if theoretical else find_result(ctx, fragment),
            conclusion=conclusion,
        ),
    )


def _task_map(ctx: CheckContext) -> dict[int, ListItem]:
    tasks, concl = _prepare(ctx.facts.tasks), _prepare(ctx.facts.conclusions)
    matched, _ = match_greedy(tasks, concl, ctx.th.TSK_MATCH_MIN)
    return {tasks[i].item.index: concl[j].item for i, (j, _) in matched.items()}


def build_matrix(ctx: CheckContext) -> Matrix:
    facts = ctx.facts
    theory = TheoryIndex(ctx)
    task_map = _task_map(ctx)
    warnings: list[str] = []
    rows: list[MatrixRow] = []
    if not theory.sections:
        warnings.append(WARN_NO_THEORY)
    if not facts.instruments:
        warnings.append(WARN_NO_INSTRUMENTS)

    if facts.hypotheses:
        for part in facts.hypotheses:
            loc = mention_location(ctx, part.loc)
            rows.append(
                _row(
                    ctx,
                    "hypothesis_part",
                    f"Гипотеза, ч.{part.index}",
                    part.text,
                    loc,
                    theory,
                    task_map,
                    part=part,
                )
            )
    else:
        warnings.append(WARN_NO_HYPOTHESIS)
    if facts.defense_positions:
        for it in facts.defense_positions:
            loc = ctx.loc.paragraph(it.paragraph_idx, it.span)
            rows.append(
                _row(
                    ctx,
                    "defense_position",
                    f"Положение {it.index}",
                    it.text,
                    loc,
                    theory,
                    task_map,
                    item=it,
                )
            )
    else:
        warnings.append(WARN_NO_DEFENSE)
    if facts.tasks:
        for it in facts.tasks:
            loc = ctx.loc.paragraph(it.paragraph_idx, it.span)
            rows.append(
                _row(ctx, "task", f"Задача {it.index}", it.text, loc, theory, task_map, item=it)
            )
    else:
        warnings.append(WARN_NO_TASKS)

    cells = [c for r in rows for c in r.cells.model_dump().values()]
    stats = MatrixStats(
        rows=len(rows),
        gaps=sum(1 for c in cells if c["status"] == "gap"),
        auto_cells=sum(1 for c in cells if c["status"] == "auto"),
        warnings=warnings,
    )
    return Matrix(rows=rows, stats=stats)


def failed_matrix() -> Matrix:
    return Matrix(rows=[], stats=MatrixStats(rows=0, gaps=0, auto_cells=0, warnings=[WARN_ERROR]))
