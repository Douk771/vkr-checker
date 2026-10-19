"""HYP-01: гипотеза одинакова во введении, главе 2 и заключении (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

import difflib

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.facts.hypothesis import STATUS_TITLES
from vkr_checker.checks.registry import register
from vkr_checker.checks.rulehelpers import mention_location
from vkr_checker.nlp.morph import content_lemmas, jaccard

_STOP = frozenset({"гипотеза", "подтвердиться", "подтверждаться", "подтвердить", "гипотетический"})
MIN_LEMMAS = 4  # короче - это ссылка на статус («гипотеза подтвердилась»), а не пересказ
SCOPE_TITLES = {
    "CHAPTER": "в главе 2",
    "CHAPTER_CONCLUSIONS": "в выводах к главе",
    "CONCLUSION": "в заключении",
}


def _lemmas(text: str) -> list[str]:
    return [x for x in content_lemmas(text) if x not in _STOP]


def _diff(base: list[str], other: list[str]) -> dict[str, list[str]]:
    """Леммы, которых нет в другой формулировке, с сохранением порядка (difflib по леммам)."""
    sm = difflib.SequenceMatcher(a=base, b=other, autojunk=False)
    only_base: list[str] = []
    only_other: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            only_base += base[i1:i2]
        if tag in ("replace", "insert"):
            only_other += other[j1:j2]
    return {"only_in_intro": only_base, "only_in_text": only_other}


@register
class Hyp01HypothesisConsistency:
    id = "HYP-01"
    title = "Гипотеза во введении, главе 2 и заключении"
    block = "hypothesis"
    source = Source("CH", "Гипотеза")
    default_level = "suspicion"
    needs = frozenset({Need.INTRO})
    priority = "must"

    def run(self, ctx: CheckContext):
        parts = ctx.facts.hypotheses
        if not parts:
            return result_of(self, [])
        whole = _lemmas(" ".join(p.text for p in parts))
        variants = [(whole, "целиком")] + [(_lemmas(p.text), f"часть {p.index}") for p in parts]
        out = []
        for m in ctx.facts.hypothesis_mentions:
            lemmas = _lemmas(m.text)
            if len(lemmas) < MIN_LEMMAS:
                continue
            best = max(variants, key=lambda v: jaccard(frozenset(v[0]), frozenset(lemmas)))
            sim = jaccard(frozenset(best[0]), frozenset(lemmas))
            if sim >= ctx.th.HYP_SIM_MIN:
                continue
            where = SCOPE_TITLES.get(m.section_kind, "в тексте")
            out.append(
                new_finding(
                    self,
                    f"Формулировка гипотезы {where} расходится с введением "
                    f"(сходство лексики {sim:.0%}).",
                    fingerprint=f"HYP-01|{m.loc.paragraph_idx}|{m.loc.span[0]}",
                    method="morph",
                    locations=[mention_location(ctx, m.loc)],
                    values={
                        "similarity": round(sim, 2),
                        "status": m.status,
                        **_diff(best[0], lemmas),
                    },
                    hint="Гипотеза должна звучать одинаково во введении, главе 2 и заключении.",
                )  # fmt: skip
            )
        out.extend(self._missing_in_chapter2(ctx))
        out.extend(self._missing_in_conclusion(ctx))
        out.extend(self._status_mismatch(ctx))
        return result_of(self, out)

    def _missing_in_conclusion(self, ctx: CheckContext):
        has_conclusion = any(s.kind == "CONCLUSION" for s in ctx.doc.sections)
        mentions = ctx.facts.hypothesis_mentions
        if not has_conclusion or any(m.section_kind == "CONCLUSION" for m in mentions):
            return []
        return [
            new_finding(
                self,
                "В заключении не сказано, подтвердилась ли гипотеза.",
                fingerprint="HYP-01|conclusion_missing",
                method="morph",
                values={"status": None},
                hint=f"Укажите статус гипотезы: {', '.join(STATUS_TITLES.values())}.",
            )  # fmt: skip
        ]

    @staticmethod
    def _chapter2_mentions(ctx: CheckContext):
        """Тело главы 2 и выводы к главе 2 (SPEC: «в главе 2 - проверка гипотезы, выводы»)."""
        return [
            m
            for m in ctx.facts.hypothesis_mentions
            if m.section_kind in ("CHAPTER", "CHAPTER_CONCLUSIONS")
            and (m.chapter is None or m.chapter >= 2)
        ]

    def _missing_in_chapter2(self, ctx: CheckContext):
        chapters = [s for s in ctx.doc.sections if s.kind == "CHAPTER"]
        if len(chapters) < 2 or self._chapter2_mentions(ctx):
            return []
        return [
            new_finding(
                self,
                "В главе 2 не упомянута гипотеза, заявленная во введении.",
                fingerprint="HYP-01|chapter2_missing",
                method="morph",
                values={"status": None},
                hint="Проверьте в эмпирической главе гипотезу и укажите её статус.",
            )  # fmt: skip
        ]

    def _status_mismatch(self, ctx: CheckContext):
        """Статус гипотезы в главе 2 (включая выводы) и в заключении различается (BUG-Q6)."""
        chapter = [m for m in self._chapter2_mentions(ctx) if m.status]
        conclusion = [
            m for m in ctx.facts.hypothesis_mentions if m.section_kind == "CONCLUSION" and m.status
        ]
        if not chapter or not conclusion:
            return []
        in_chapter = list(dict.fromkeys(m.status for m in chapter))
        in_conclusion = {m.status for m in conclusion}
        if set(in_chapter) & in_conclusion:
            return []
        m = conclusion[0]
        ch_titles = ", ".join(f"«{STATUS_TITLES[x]}»" for x in in_chapter)
        return [
            new_finding(
                self,
                f"Статус гипотезы в заключении («{STATUS_TITLES[m.status]}») расходится "
                f"с главой 2 ({ch_titles}).",
                fingerprint="HYP-01|status_mismatch",
                method="morph",
                locations=[mention_location(ctx, chapter[0].loc), mention_location(ctx, m.loc)],
                values={
                    "status": m.status,
                    "status_chapter2": in_chapter[0],
                    "statuses_chapter2": in_chapter,
                },
                hint="Статус гипотезы должен совпадать в главе 2 и в заключении.",
            )  # fmt: skip
        ]
