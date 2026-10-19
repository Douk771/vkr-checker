"""INT-01: обязательные элементы введения (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

import re

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.facts.intro import REQUIRED
from vkr_checker.checks.registry import register

ELEMENT_TITLES: dict[str, str] = {
    "actuality": "актуальность",
    "elaboration": "степень изученности (разработанности) проблемы",
    "goal": "цель",
    "object": "объект",
    "subject": "предмет",
    "tasks": "задачи",
    "hypothesis": "гипотеза",
    "theory_basis": "теоретико-методологические основания",
    "methods": "методы (методики)",
    "sample": "выборка",
    "novelty": "научная новизна",
    "theory_value": "теоретическая значимость",
    "practice_value": "практическая значимость",
    "defense": "положения, выносимые на защиту",
    "approbation": "апробация",
    "implementation": "внедрение",
}
_ACT = re.compile(r"акт\w*\s+внедрени", re.IGNORECASE)


@register
class Int01IntroElements:
    id = "INT-01"
    title = "Элементы введения"
    block = "intro"
    source = Source("M", "Обязательные элементы введения")
    default_level = "violation"
    needs = frozenset({Need.INTRO})
    priority = "must"

    def run(self, ctx: CheckContext):
        elements = ctx.facts.intro_elements
        out = []
        for key in REQUIRED:
            name = ELEMENT_TITLES[key]
            found = elements.get(key, [])
            if not found:
                out.append(
                    new_finding(
                        self,
                        f"Во введении не найден элемент: {name}.",
                        fingerprint=f"INT-01|missing|{key}",
                        method="morph",
                        values={"element": key},
                        hint="Элемент ищется по ключевому слову в начале абзаца или предложения.",
                    )  # fmt: skip
                )
            elif all(e.position == "inline" for e in found):
                out.append(
                    new_finding(
                        self,
                        f"Элемент «{name}» упомянут только внутри абзаца и не выделен отдельно.",
                        fingerprint=f"INT-01|inline|{key}",
                        level="suspicion",
                        method="morph",
                        locations=[ctx.loc.paragraph(found[0].paragraph_idx, found[0].span)],
                        values={"element": key},
                        hint="Начните абзац или предложение с названия элемента.",
                    )  # fmt: skip
                )
        out.extend(self._implementation(ctx))
        artifact = [
            {
                "key": key,
                "title": ELEMENT_TITLES.get(key, key),
                "position": e.position,
                "paragraph_idx": e.paragraph_idx,
            }
            for key in ELEMENT_TITLES
            for e in elements.get(key, [])
        ]
        return result_of(self, out, elements=artifact)

    def _implementation(self, ctx: CheckContext):
        found = ctx.facts.intro_elements.get("implementation", [])
        if not found:
            return []
        doc = ctx.doc
        has_act = any(_ACT.search(p.text) for p in doc.paragraphs) or any(
            _ACT.search(a.title) for a in doc.appendices
        )
        if has_act:
            return []
        return [
            new_finding(
                self,
                "Во введении заявлено внедрение, но в работе нет акта внедрения.",
                fingerprint="INT-01|implementation",
                level="suspicion",
                method="regex",
                locations=[ctx.loc.paragraph(found[0].paragraph_idx, found[0].span)],
                hint="Приложите акт внедрения или уберите упоминание внедрения.",
            )  # fmt: skip
        ]
