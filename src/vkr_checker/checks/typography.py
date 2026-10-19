"""TBL-06: неразрывный пробел в «n = 17», «p < 0,001», «1,5 ч» (в тексте и ячейках)."""

from __future__ import annotations

import re

from vkr_checker.checks.base import CheckContext, Source, new_finding, result_of
from vkr_checker.checks.facts.common import iter_text_units
from vkr_checker.checks.registry import register
from vkr_checker.model.finding import Finding

# обычный пробел (U+0020) между обозначением, знаком и числом; U+00A0 и U+202F не совпадают
_STAT = re.compile(
    r"(?<![\w.])(?:n|N|p|t|r|rs|U|H|F|M|SD|df|d|R[2²]|χ[2²]|β|α)"
    r"[ \u00a0\u202f]?[=<>≤≥][ \u00a0\u202f]?[-−–]?\d[\d,.]*"
)
_UNITS = (
    "ч|час|часа|часов|мин|сек|лет|года|год|мес|мм|см|км|мг|г\\.|кг|мл|%|балл|балла|баллов|чел\\."
)
_UNIT = re.compile(rf"(?<![\w,.])\d+(?:[,.]\d+)? (?:{_UNITS})(?![\w])")


def _bad_matches(text: str) -> list[re.Match[str]]:
    found = []
    for m in _STAT.finditer(text):
        # ошибка - обычный пробел вокруг знака (внутри совпадения есть пробел U+0020)
        if " " in m.group():
            found.append(m)
    found.extend(_UNIT.finditer(text))
    found.sort(key=lambda m: m.start())
    return found


@register
class Tbl06NonBreakingSpace:
    id = "TBL-06"
    title = "Неразрывный пробел в записи величин"
    block = "tables"
    source = Source("CH", "Оформление таблиц и записи величин")
    default_level = "suspicion"
    needs = frozenset()
    priority = "should"

    def run(self, ctx: CheckContext):
        out: list[Finding] = []
        for mention, text, _kind in iter_text_units(ctx.doc):
            matches = _bad_matches(text)
            if not matches:
                continue
            for m in matches:
                if mention.cell is not None:
                    cell = mention.cell
                    label = ctx.doc.table(cell.table_idx).number_label(ctx.doc)
                    loc = ctx.loc.cell(cell.table_idx, cell.row, cell.col, m.span())
                    where, key = label, f"t{cell.table_idx}"
                else:
                    idx = mention.paragraph_idx
                    loc = ctx.loc.paragraph(idx, m.span())
                    where, key = f"Абзац {idx}", f"p{idx}"
                shown = m.group().replace(" ", "␣")
                out.append(
                    new_finding(
                        self,
                        f"{where}: обычный пробел в записи «{shown}» (мест: {{count}}).",
                        fingerprint=f"TBL-06|{key}",
                        locations=[loc],
                        method="regex",
                        values={"example": m.group()},
                        hint="Замените пробел на неразрывный (Ctrl+Shift+Пробел).",
                    )  # fmt: skip
                )
        return result_of(self, out)
