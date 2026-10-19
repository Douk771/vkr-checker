"""TSK-01: задачи введения против выводов заключения (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.facts.tasks import ListItem
from vkr_checker.checks.registry import register
from vkr_checker.nlp.morph import content_lemmas

BIGRAM_BONUS = 0.1
BIGRAM_BONUS_CAP = 0.3
SHORT = 70


@dataclass(frozen=True)
class _Prepared:
    item: ListItem
    lemmas: frozenset[str]
    bigrams: frozenset[tuple[str, str]]


def _prepare(items: list[ListItem]) -> list[_Prepared]:
    result = []
    for it in items:
        seq = content_lemmas(it.text)
        result.append(_Prepared(it, frozenset(seq), frozenset(pairwise(seq))))
    return result


def similarity(a: _Prepared, b: _Prepared, weight: dict[str, float]) -> float:
    """Взвешенный Жаккар лемм (редкие слова весят больше) плюс бонус за общие биграммы."""
    union = a.lemmas | b.lemmas
    if not union:
        return 0.0
    num = sum(weight[x] for x in a.lemmas & b.lemmas)
    den = sum(weight[x] for x in union)
    bonus = min(len(a.bigrams & b.bigrams) * BIGRAM_BONUS, BIGRAM_BONUS_CAP)
    return min(num / den + bonus, 1.0) if den else 0.0


def match_greedy(tasks: list[_Prepared], concl: list[_Prepared], min_sim: float):
    """Жадное сопоставление по убыванию близости: (task_pos -> (concl_pos, sim))."""
    df: dict[str, int] = {}
    for p in [*tasks, *concl]:
        for lem in p.lemmas:
            df[lem] = df.get(lem, 0) + 1
    weight = {lem: 1.0 / n for lem, n in df.items()}
    pairs = sorted(
        (
            (-similarity(t, c, weight), i, j)
            for i, t in enumerate(tasks)
            for j, c in enumerate(concl)
        )
    )
    used_t: dict[int, tuple[int, float]] = {}
    used_c: set[int] = set()
    for neg, i, j in pairs:
        sim = -neg
        if sim < min_sim:
            break
        if i in used_t or j in used_c:
            continue
        used_t[i] = (j, sim)
        used_c.add(j)
    return used_t, used_c


def _short(text: str) -> str:
    return text if len(text) <= SHORT else text[: SHORT - 1].rstrip() + "…"


@register
class Tsk01TasksVsConclusions:
    id = "TSK-01"
    title = "Задачи и выводы заключения"
    block = "tasks"
    source = Source("CH", "Задачи и выводы")
    default_level = "suspicion"
    needs = frozenset({Need.INTRO, Need.CONCLUSION})
    priority = "must"

    def run(self, ctx: CheckContext):
        tasks_items, concl_items = ctx.facts.tasks, ctx.facts.conclusions
        if not tasks_items:
            return result_of(self, [], task_map=[])
        out = []
        tasks, concl = _prepare(tasks_items), _prepare(concl_items)
        matched, used_c = match_greedy(tasks, concl, ctx.th.TSK_MATCH_MIN)
        task_map = [
            {
                "task_index": t.item.index,
                "task": _short(t.item.text),
                "conclusion_index": concl[matched[i][0]].item.index if i in matched else None,
                "similarity": round(matched[i][1], 2) if i in matched else None,
            }
            for i, t in enumerate(tasks)
        ]
        if not concl:
            out.append(
                new_finding(
                    self,
                    "В заключении не удалось выделить выводы, чтобы сопоставить их с задачами.",
                    fingerprint="TSK-01|no_conclusions",
                    method="morph",
                    hint="Оформите выводы нумерованным списком или отдельными абзацами.",
                )  # fmt: skip
            )
            return result_of(self, out, task_map=task_map)
        for i, t in enumerate(tasks):
            if i not in matched:
                out.append(
                    new_finding(
                        self,
                        f"Задаче {t.item.index} («{_short(t.item.text)}») не находится "
                        "соответствующего вывода в заключении.",
                        fingerprint=f"TSK-01|task|{t.item.index}",
                        method="morph",
                        locations=[ctx.loc.paragraph(t.item.paragraph_idx, t.item.span)],
                        values={"task_index": t.item.index},
                    )  # fmt: skip
                )
        for j, c in enumerate(concl):
            if j not in used_c:
                out.append(
                    new_finding(
                        self,
                        f"Вывод {c.item.index} заключения не связан ни с одной задачей.",
                        fingerprint=f"TSK-01|conclusion|{c.item.index}",
                        method="morph",
                        locations=[ctx.loc.paragraph(c.item.paragraph_idx, c.item.span)],
                        values={"conclusion_index": c.item.index},
                    )  # fmt: skip
                )
        if abs(len(tasks) - len(concl)) > ctx.th.TSK_COUNT_DIFF:
            out.append(
                new_finding(
                    self,
                    f"Задач {len(tasks)}, а выводов в заключении {len(concl)}: "
                    "число сильно различается.",
                    fingerprint="TSK-01|count",
                    method="count",
                    values={"tasks": len(tasks), "conclusions": len(concl)},
                )  # fmt: skip
            )
        return result_of(self, out, task_map=task_map)
