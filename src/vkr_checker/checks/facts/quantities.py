"""Величины с «тождеством» (ARCHITECTURE_CHECKS.md §3, SPEC §6 п.6).

Ключ величины (kind, qualifier): CON-01 сравнивает значения только при одинаковом kind и пустом
qualifier. Подвыборки, группы и ячейки таблиц получают непустой qualifier, поэтому ложных
расхождений они не дают (главный регулятор шума).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vkr_checker.model.document import Document
from vkr_checker.nlp.morph import lemma
from vkr_checker.nlp.normalize import normalize_number
from vkr_checker.nlp.sentences import split_sentences

from .common import Mention, iter_text_units

NUM = r"\d+(?:[  ]\d{3})*(?:[.,]\d+)?"
_N_EQ = re.compile(rf"(?<![A-Za-zА-Яа-я])[nN]\s*=\s*({NUM})")
_N_PEOPLE = re.compile(
    rf"({NUM})\s+(респондент\w*|испытуем\w*|участник\w*|человек\w*|студент\w*|пациент\w*)",
    re.IGNORECASE,
)
_AGE_RANGE = re.compile(
    rf"(?:от\s+({NUM})\s+до\s+({NUM})|({NUM})\s*[-–—]\s*({NUM}))\s+(?:лет|года|г\.)",
    re.IGNORECASE,
)
_AGE_MEAN = re.compile(
    rf"средн\w+\s+возраст\w*[^.;\d]{{0,50}}?({NUM})|возраст\w*[^.;\d]{{0,30}}?\bM\s*=\s*({NUM})",
    re.IGNORECASE,
)
_AGE_SD = re.compile(
    rf"(?:\bSD\b|σ|стандартн\w+\s+отклонени\w+)\s*[=:]?\s*(?:составил\w*\s*)?({NUM})"
)
_PERCENT = re.compile(rf"({NUM})\s*%\s*(?:от\s+)?([А-Яа-яЁё]{{3,}})?")
_GROUP_WORD = re.compile(r"([А-Яа-яЁё]+)\s+групп\w*", re.IGNORECASE)
_PEOPLE_AFTER = re.compile(
    rf"(?:\bn\s*=\s*({NUM})|({NUM})\s+(?:человек|испытуем|респондент|участник|студент))"
)
_SAMPLE_ANCHOR = re.compile(r"выборк|респондент|испытуем|участник|\b[nN]\s*=", re.IGNORECASE)
_AGE_ANCHOR = re.compile(r"возраст", re.IGNORECASE)
QUALIFIER_STEMS = (
    "групп", "подвыборк", "из них", "в том числе", "мужчин", "женщин",
    "экспериментальн", "контрольн",
)  # fmt: skip
TABLE_QUALIFIER = "table"


@dataclass(frozen=True, slots=True)
class Quantity:
    kind: str
    qualifier: str
    value: str  # нормализованное число (normalize_number); для диапазона "18-35"
    unit: str
    loc: Mention
    section_kind: str
    raw: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, self.qualifier)


_CLAUSE_END = re.compile(r"[,;:()—]")


def _qualifier(sentence: str, in_table: bool, start: int = 0, end: int | None = None) -> str:
    """Квалификатор относится к величине, если стоит перед ней в предложении или сразу после
    неё в той же клаузе («n = 120 женщин»). «..., из них 60% женщин» n до запятой не затрагивает."""
    if end is None:
        low = sentence.lower()
    else:
        tail_match = _CLAUSE_END.search(sentence, end)
        tail = sentence[end : tail_match.start() if tail_match else len(sentence)]
        low = (sentence[:start] + " " + tail).lower()
    found = [s for s in QUALIFIER_STEMS if s in low]
    if in_table:
        found.append(TABLE_QUALIFIER)
    return "|".join(found)


def _object_lemma(word: str | None) -> str:
    return lemma(word) if word else ""


def _extract_sentence(
    sentence: str, offset: int, context: str, mention: Mention, kind: str, in_table: bool
) -> list[Quantity]:
    out: list[Quantity] = []

    def add(qk: str, value: str, unit: str, m: re.Match, q: str | None = None) -> None:
        span = (offset + m.start(), offset + m.end())
        loc = Mention(mention.paragraph_idx, span, mention.cell)
        qual = _qualifier(sentence, in_table, m.start(), m.end()) if q is None else q
        out.append(Quantity(qk, qual, value, unit, loc, kind, m.group()))

    for m in _N_EQ.finditer(sentence):
        add("sample_n", normalize_number(m.group(1)), "чел", m)
    anchored = bool(_SAMPLE_ANCHOR.search(context))
    for m in _N_PEOPLE.finditer(sentence):
        if anchored or re.match(r"респондент|испытуем|участник", m.group(2), re.IGNORECASE):
            add("sample_n", normalize_number(m.group(1)), "чел", m)
    for m in _AGE_RANGE.finditer(sentence):
        lo = m.group(1) or m.group(3)
        hi = m.group(2) or m.group(4)
        add("age_min_max", f"{normalize_number(lo)}-{normalize_number(hi)}", "лет", m)
    if _AGE_ANCHOR.search(context):
        for m in _AGE_MEAN.finditer(sentence):
            add("age_mean", normalize_number(m.group(1) or m.group(2)), "лет", m)
        for m in _AGE_SD.finditer(sentence):
            add("age_sd", normalize_number(m.group(1)), "лет", m)
    for m in _PERCENT.finditer(sentence):
        obj = _object_lemma(m.group(2))
        if obj:
            add(f"percent_of:{obj}", normalize_number(m.group(1)), "%", m)
    out.extend(_group_sizes(sentence, offset, mention, kind, in_table))
    return out


def _group_sizes(sentence, offset, mention, kind, in_table) -> list[Quantity]:
    out: list[Quantity] = []
    for g in _GROUP_WORD.finditer(sentence):
        label = lemma(g.group(1))
        m = _PEOPLE_AFTER.search(sentence, g.end(), min(len(sentence), g.end() + 60))
        if m is None:
            continue
        span = (offset + g.start(), offset + m.end())
        loc = Mention(mention.paragraph_idx, span, mention.cell)
        q = TABLE_QUALIFIER if in_table else ""
        raw = sentence[g.start() : m.end()]
        out.append(
            Quantity(f"group_n:{label}", q, normalize_number(m.group(1) or m.group(2)), "чел", loc, kind, raw)
        )
    return out


def extract_quantities(doc: Document) -> list[Quantity]:
    result: list[Quantity] = []
    for mention, text, kind in iter_text_units(doc):
        in_table = mention.cell is not None
        sentences = split_sentences(text)
        for i, s in enumerate(sentences):
            context = " ".join(x.text for x in sentences[max(0, i - 1) : i + 2])
            for q in _extract_sentence(s.text, s.start, context, mention, kind, in_table):
                if not any(_same(q, old) for old in result[-8:]):
                    result.append(q)
    return result


def _same(a: Quantity, b: Quantity) -> bool:
    """Та же величина, найденная двумя шаблонами («n = 124 респондента»)."""
    if (a.kind, a.value, a.loc.paragraph_idx, a.loc.cell) != (
        b.kind,
        b.value,
        b.loc.paragraph_idx,
        b.loc.cell,
    ):
        return False
    return a.loc.span[0] < b.loc.span[1] and b.loc.span[0] < a.loc.span[1]
