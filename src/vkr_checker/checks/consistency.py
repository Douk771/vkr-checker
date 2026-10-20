"""CON-01..04: согласованность цифр (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

import re
from collections import defaultdict

from vkr_checker.checks.base import CheckContext, Source, new_finding, result_of
from vkr_checker.checks.facts.common import chapter_number, chapter_of, iter_text_units
from vkr_checker.checks.facts.quantities import NUM
from vkr_checker.checks.registry import register
from vkr_checker.checks.rulehelpers import mention_location
from vkr_checker.checks.textfmt import fmt_num
from vkr_checker.nlp.normalize import normalize_number
from vkr_checker.nlp.sentences import split_sentences

KIND_TITLES = {
    "sample_n": "объём выборки",
    "age_min_max": "возрастной диапазон",
    "age_mean": "средний возраст",
    "age_sd": "стандартное отклонение возраста",
}
SRC = Source("CH", "Данные и цифры")


_PEOPLE_UNIT = re.compile(r"чел|респондент|испытуем|участник|\bn\s*=", re.IGNORECASE)


def kind_title(kind: str) -> str:
    if kind.startswith("group_n:"):
        return f"численность группы «{kind.split(':', 1)[1]}»"
    return KIND_TITLES.get(kind, kind)


def _num(text: str) -> float:
    return float(normalize_number(text))


@register
class Con01SameQuantities:
    id = "CON-01"
    title = "Одинаковые величины по тексту"
    block = "consistency"
    source = SRC
    default_level = "suspicion"
    needs = frozenset()
    priority = "must"

    def run(self, ctx: CheckContext):
        quantities = ctx.facts.quantities
        index = [
            {
                "kind": q.kind,
                "qualifier": q.qualifier,
                "value": q.value,
                "unit": q.unit,
                "paragraph_idx": q.loc.paragraph_idx,
                "raw": q.raw,
            }
            for q in quantities
        ]
        groups: dict[str, list] = defaultdict(list)
        for q in quantities:
            if q.qualifier != "" or q.kind.startswith("percent_of:"):
                continue
            if q.kind.startswith("group_n:") and not _PEOPLE_UNIT.search(q.raw):
                continue  # «в учебной группе (Иванов, 2015)»: это год, а не численность
            groups[q.kind].append(q)
        out = []
        for kind in sorted(groups):
            items = groups[kind]
            values = sorted({q.value for q in items})
            if len(values) < 2:
                continue
            first_of = {v: next(q for q in items if q.value == v) for v in values}
            listing = "; ".join(f"{v} {first_of[v].unit}".strip() for v in values)
            out.append(
                new_finding(
                    self,
                    f"Величина «{kind_title(kind)}» указана по-разному: {listing}.",
                    fingerprint=f"CON-01|{kind}",
                    method="regex",
                    locations=[mention_location(ctx, first_of[v].loc) for v in values],
                    values={"kind": kind, "values": values},
                    hint="Если значения относятся к разным подвыборкам, поясните это в тексте.",
                )  # fmt: skip
            )
        return result_of(self, out, numbers_index=index)


# --- CON-02 ---------------------------------------------------------------------------------
_M = re.compile(rf"(?<![A-Za-zА-Яа-я])M\s*=\s*({NUM})")
_SD = re.compile(rf"(?:\bSD\b|σ)\s*=\s*({NUM})|M\s*=\s*{NUM}\s*±\s*({NUM})")
_RANGE = re.compile(
    rf"(?:диапазон\w*|размах\w*|варьир\w+)[^.;]{{0,40}}?(?:от\s*)?({NUM})\s*(?:до|[-–—])\s*({NUM})"
    rf"|\bmin\s*=\s*({NUM})\s*[,;]?\s*\bmax\s*=\s*({NUM})"
    rf"|\bот\s+({NUM})\s+до\s+({NUM})",
    re.IGNORECASE,
)
_HEAD = {
    "m": re.compile(r"^(m|mean|среднее|ср\.?)$", re.IGNORECASE),
    "sd": re.compile(r"^(sd|σ|ско|ст\.?\s*откл\.?)$", re.IGNORECASE),
    "min": re.compile(r"^(min|мин\.?|минимум)$", re.IGNORECASE),
    "max": re.compile(r"^(max|макс\.?|максимум)$", re.IGNORECASE),
}


def _first_group(m: re.Match) -> float:
    return _num(next(g for g in m.groups() if g is not None))


def _check_stats(ctx: CheckContext, mean: float, lo: float, hi: float, sd: float | None):
    """Список (подвид, сообщение, уровень) для одной тройки/четвёрки показателей."""
    problems = []
    if not lo <= mean <= hi:
        problems.append((
            "mean_outside", f"Среднее M = {fmt_num(mean)} лежит вне диапазона "
            f"{fmt_num(lo)}-{fmt_num(hi)}.", "violation",
        ))  # fmt: skip
    elif sd is not None and hi > lo:
        rng = hi - lo
        k = ctx.th.SD_RANGE_K
        if sd * 2 > rng * 1.5:
            problems.append((
                "sd_too_big", f"SD = {fmt_num(sd)} слишком велико для диапазона "
                f"{fmt_num(lo)}-{fmt_num(hi)}.", "suspicion",
            ))  # fmt: skip
        elif rng > 4 * k * sd > 0:
            problems.append((
                "range_too_wide", f"Диапазон {fmt_num(lo)}-{fmt_num(hi)} слишком широк для "
                f"SD = {fmt_num(sd)} (более {4 * k} SD).", "suspicion",
            ))  # fmt: skip
    return problems


@register
class Con02MeanInRange:
    id = "CON-02"
    title = "Среднее внутри диапазона"
    block = "consistency"
    source = SRC
    default_level = "violation"
    needs = frozenset()
    priority = "must"

    def run(self, ctx: CheckContext):
        out = []
        for mention, text, _kind in iter_text_units(ctx.doc):
            if mention.cell is not None:
                continue
            for s in split_sentences(text):
                m, r = _M.search(s.text), _RANGE.search(s.text)
                if not m or not r:
                    continue
                sd_m = _SD.search(s.text)
                sd = _first_group(sd_m) if sd_m else None
                nums = [g for g in r.groups() if g is not None]
                lo, hi = _num(nums[0]), _num(nums[1])
                span = (s.start, s.end)
                for sub, msg, level in _check_stats(ctx, _first_group(m), lo, hi, sd):
                    out.append(self._finding(ctx, mention, span, sub, msg, level))
        out.extend(self._tables(ctx))
        return result_of(self, out)

    def _finding(self, ctx, mention, span, sub, msg, level):
        key = mention.paragraph_idx or 0
        return new_finding(
            self, msg, fingerprint=f"CON-02|{sub}|{key}", level=level, method="regex",
            locations=[mention_location(ctx, mention, span)],
        )  # fmt: skip

    def _tables(self, ctx: CheckContext):
        out = []
        for table in ctx.doc.tables:
            if not table.rows:
                continue
            cols = {}
            for cell in table.rows[0].cells:
                label = cell.text.strip()
                for key, pat in _HEAD.items():
                    if pat.match(label):
                        cols[key] = cell.col
            if not {"m", "min", "max"} <= set(cols):
                continue
            for row in table.rows[1:]:
                vals = {}
                for key, col in cols.items():
                    cell = next((c for c in row.cells if c.col == col), None)
                    try:
                        vals[key] = _num(cell.text) if cell else None
                    except ValueError:
                        vals[key] = None
                if None in (vals.get("m"), vals.get("min"), vals.get("max")):
                    continue
                anchor = row.cells[0]
                for sub, msg, level in _check_stats(
                    ctx, vals["m"], vals["min"], vals["max"], vals.get("sd")
                ):
                    out.append(new_finding(
                        self,
                        f"{table.number_label(ctx.doc)}, строка «{anchor.text.strip()}»: {msg}",
                        fingerprint=f"CON-02|{sub}|t{table.idx}|{anchor.row}", level=level,
                        method="regex",
                        locations=[ctx.loc.cell(table.idx, anchor.row, cols["m"])],
                    ))  # fmt: skip
        return out


# --- CON-03 ---------------------------------------------------------------------------------
_PCT = re.compile(rf"({NUM})\s*%")
_PCT_SENTENCE_HINT = re.compile(r"соответственно|распредел|разделил|составил|из них", re.IGNORECASE)
_ROUNDING = re.compile(r"округл", re.IGNORECASE)
_TOTAL_ROW = re.compile(r"^\s*(итого|всего|сумма|total)\b", re.IGNORECASE)
_PCT_HEADER = re.compile(r"%|доля|процент", re.IGNORECASE)
PARTITION_BAND = 10.0  # сумма вне [100 - 10; 100 + 10] - вероятно, не распределение целого


def _rounding_near(ctx: CheckContext, paragraph_idx: int | None) -> bool:
    if paragraph_idx is None:
        return False
    return any(
        _ROUNDING.search(p.text)
        for p in ctx.doc.paragraphs
        if abs(p.idx - paragraph_idx) <= 1 and p.cell is None
    )


_CITATION = re.compile(r"\[\d+(?:[,;\s–—-]+\d+)*(?:,\s*с\.[^\]]*)?\]")


@register
class Con03PercentSums:
    id = "CON-03"
    title = "Суммы процентов"
    block = "consistency"
    source = SRC
    default_level = "suspicion"
    needs = frozenset()
    priority = "should"

    @staticmethod
    def _literature_part(ctx: CheckContext, paragraph_idx: int | None) -> bool:
        """Глава 1 — обзор литературы: проценты там из чужих исследований, а не из своих данных."""
        if paragraph_idx is None:
            return False
        sid = ctx.doc.paragraph(paragraph_idx).section_id
        chapter = chapter_of(ctx.doc, sid)
        if chapter is None:
            return False
        if chapter.number:  # «ГЛАВА 2» — номер из заголовка надёжнее порядкового
            return chapter.number.split(".")[0] == "1"
        return chapter_number(ctx.doc, sid) == 1

    def _verdict(self, ctx: CheckContext, total: float):
        tol = ctx.th.PCT_TOL
        diff = abs(total - 100)
        if diff <= tol or diff > PARTITION_BAND:
            return None
        if diff <= 2:
            return "вероятно, округление"
        return "сумма не равна 100%"

    def run(self, ctx: CheckContext):
        out = []
        for mention, text, _kind in iter_text_units(ctx.doc):
            if mention.cell is not None or self._literature_part(ctx, mention.paragraph_idx):
                continue
            for s in split_sentences(text):
                if _CITATION.search(s.text):
                    continue  # чужие данные (опросы с несколькими ответами дают > 100 %)
                values = [_num(m.group(1)) for m in _PCT.finditer(s.text)]
                needed = 3 if not _PCT_SENTENCE_HINT.search(s.text) else 2
                if len(values) < needed:
                    continue
                verdict = self._verdict(ctx, sum(values))
                if verdict is None or _rounding_near(ctx, mention.paragraph_idx):
                    continue
                out.append(self._finding(ctx, sum(values), verdict, mention, (s.start, s.end),
                                         f"p{mention.paragraph_idx}"))  # fmt: skip
        out.extend(self._tables(ctx))
        return result_of(self, out)

    def _finding(self, ctx, total, verdict, mention, span, key):
        return new_finding(
            self, f"Проценты в перечислении дают {fmt_num(total, 1)}% ({verdict}).",
            fingerprint=f"CON-03|{key}", method="regex",
            locations=[mention_location(ctx, mention, span)], values={"sum": round(total, 2)},
            hint="Если сумма отличается из-за округления, добавьте оговорку об этом.",
        )  # fmt: skip

    def _tables(self, ctx: CheckContext):
        out = []
        for table in ctx.doc.tables:
            if not table.rows or table.parent_table_idx is not None:
                continue
            for header in table.rows[0].cells:
                if not _PCT_HEADER.search(header.text):
                    continue
                values, last = [], None
                for row in table.rows[1:]:
                    cell = next((c for c in row.cells if c.col == header.col), None)
                    label = row.cells[0].text if row.cells else ""
                    if cell is None or _TOTAL_ROW.match(label):
                        continue
                    m = re.match(rf"^\s*({NUM})\s*%?\s*$", cell.text)
                    if m:
                        values.append(_num(m.group(1)))
                        last = cell
                if len(values) < 3 or last is None:
                    continue
                verdict = self._verdict(ctx, sum(values))
                if verdict is None:
                    continue
                out.append(new_finding(
                    self, f"{table.number_label(ctx.doc)}: столбец «{header.text.strip()}» даёт "
                    f"{fmt_num(sum(values), 1)}% ({verdict}).",
                    fingerprint=f"CON-03|t{table.idx}|{header.col}", method="regex",
                    locations=[ctx.loc.cell(table.idx, last.row, last.col)],
                    values={"sum": round(sum(values), 2)},
                ))  # fmt: skip
        return out


# --- CON-04 ---------------------------------------------------------------------------------
_DIVISION: dict[str, tuple[str, re.Pattern[str]]] = {
    "tercile": ("терцили", re.compile(r"терцил", re.IGNORECASE)),
    "quartile": ("квартили", re.compile(r"квартил", re.IGNORECASE)),
    "median": ("медиана", re.compile(r"по\s+медиан|медианн\w+\s+(?:раздел|разбиен|делен)|"
                                      r"относительно\s+медиан", re.IGNORECASE)),
    "mean_sd": ("M ± σ", re.compile(r"M\s*[±]\s*(?:σ|SD)|среднее\s*[±]|"
                                    r"среднего\s+арифметическ\w+\s*[±]", re.IGNORECASE)),
    "norms": ("нормы теста", re.compile(r"по\s+норм\w+|нормативн\w+\s+(?:границ|значени)",
                                        re.IGNORECASE)),
}  # fmt: skip
_GROUP_CONTEXT = re.compile(r"групп|раздел|разбит|делен|выдел|уровн", re.IGNORECASE)


@register
class Con04GroupingMethods:
    id = "CON-04"
    title = "Способ деления на группы"
    block = "consistency"
    source = SRC
    default_level = "suspicion"
    needs = frozenset()
    priority = "should"

    def run(self, ctx: CheckContext):
        first: dict[str, tuple] = {}
        for mention, text, _kind in iter_text_units(ctx.doc):
            if mention.cell is not None:
                continue
            for s in split_sentences(text):
                if not _GROUP_CONTEXT.search(s.text):
                    continue
                for key, (_name, pat) in _DIVISION.items():
                    if pat.search(s.text) and key not in first:
                        first[key] = (mention, (s.start, s.end))
        if len(first) < 2:
            return result_of(self, [])
        names = ", ".join(_DIVISION[k][0] for k in sorted(first))
        finding = new_finding(
            self,
            f"Для деления на группы названо несколько способов: {names}.",
            fingerprint="CON-04", method="morph",
            locations=[mention_location(ctx, m, sp) for m, sp in (first[k] for k in sorted(first))],
            values={"methods": sorted(first)},
            hint="Если речь об одних и тех же группах, оставьте один способ деления.",
        )  # fmt: skip
        return result_of(self, [finding])
