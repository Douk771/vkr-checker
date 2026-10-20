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
# «2025 года», «1920 г.» — дата, а не величина с единицей измерения
_YEAR = re.compile(r"^(?:1[89]|20)\d{2} (?:год|года|г\.)$")


def _group_of(text: str) -> tuple[str, str]:
    """Вид записи: статистика («n = 17») или число с единицей («60 %», «1,5 ч»)."""
    if _STAT.match(text):
        return "stat", "статистики («n = 17», «p < 0,05»)"
    unit = text.split(" ", 1)[1]
    if unit == "%":
        return "percent", "процентов («60 %»)"
    return f"unit|{unit}", f"величины с единицей «{unit}»"


def _bad_matches(text: str) -> list[re.Match[str]]:
    found = []
    for m in _STAT.finditer(text):
        # ошибка - обычный пробел вокруг знака (внутри совпадения есть пробел U+0020)
        if " " in m.group():
            found.append(m)
    found.extend(m for m in _UNIT.finditer(text) if not _YEAR.match(m.group()))
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
                    loc = ctx.loc.cell(cell.table_idx, cell.row, cell.col, m.span())
                else:
                    loc = ctx.loc.paragraph(mention.paragraph_idx, m.span())
                # одна находка на вид записи на всю работу: при сквозной привычке писать
                # «60 %» через обычный пробел отчёт не тонет в находке на каждый абзац
                group, title = _group_of(m.group())
                shown = m.group().replace(" ", "␣")
                out.append(
                    new_finding(
                        self,
                        f"Обычный пробел в записи {title}, например «{shown}» (мест: {{count}}).",
                        fingerprint=f"TBL-06|{group}",
                        locations=[loc],
                        method="regex",
                        values={"example": m.group()},
                        hint="Замените пробел на неразрывный (Ctrl+Shift+Пробел).",
                    )  # fmt: skip
                )
        return result_of(self, out)
