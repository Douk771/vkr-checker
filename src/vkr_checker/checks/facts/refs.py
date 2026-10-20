"""Ссылки на таблицы, рисунки, приложения и источники (NUM-02, STR-05, DIF-05.4, BIB-01)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from vkr_checker.model.document import Document

from .common import Mention, section_kind_of

RefKind = Literal["table", "figure", "appendix", "source"]
_NUM = r"\d+(?:[.,]\d+)*|(?-i:[А-ЯA-Z])(?![A-Za-zА-Яа-яЁё])"
_NUM_LIST = rf"(?P<n>{_NUM})(?P<rest>(?:\s*(?:[–—-]|,|;|и)\s*(?:{_NUM}))*)"
_PREFIX = {
    "table": r"табл(?:иц\w*|\.)?",
    "figure": r"рис(?:ун\w*|\.)?",
    "appendix": r"приложени\w+",
}
_REF_PATTERNS = {
    kind: re.compile(rf"(?<![А-Яа-яЁё])(?P<word>{p})\s*(?:№|N)?\s*{_NUM_LIST}", re.IGNORECASE)
    for kind, p in _PREFIX.items()
}
_SOURCE = re.compile(
    r"\[(?P<body>\d+(?:\s*[,;–—-]\s*\d+)*)(?:\s*,\s*(?:с|стр|c)\.\s*[\d\s–—,-]+)?\]"
)
_SEE = re.compile(r"\(\s*см\.\s*$", re.IGNORECASE)
_SPLIT = re.compile(r"\s*(?P<sep>[–—-]|,|;|и)\s*")


@dataclass(frozen=True, slots=True)
class Ref:
    kind: RefKind
    target: str  # "3", "2.1", "А"
    loc: Mention
    see: bool = False  # «(см. табл. 3)»
    in_range: bool = False


def _norm_target(value: str, kind: RefKind) -> str:
    value = value.replace(",", ".")
    return value.upper() if kind == "appendix" else value


def _expand(first: str, rest: str, kind: RefKind) -> list[tuple[str, bool]]:
    """Список целей «табл. 2–4», «рис. 1, 2 и 3»: диапазоны целых раскрываются."""
    items = [(first, "")]
    tokens = re.findall(rf"(?P<sep>[–—-]|,|;|и)\s*(?P<v>{_NUM})", rest)
    items += [(v, sep) for sep, v in tokens]
    out: list[tuple[str, bool]] = []
    prev = first
    out.append((_norm_target(first, kind), False))
    for v, sep in items[1:]:
        if sep in "–—-" and prev.isdigit() and v.isdigit() and 0 < int(v) - int(prev) <= 50:
            out.extend((str(n), True) for n in range(int(prev) + 1, int(v) + 1))
        else:
            out.append((_norm_target(v, kind), False))
        prev = v
    return out


def extract_refs(doc: Document) -> list[Ref]:
    captions = {c.paragraph_idx for c in doc.captions if c.paragraph_idx}
    captions |= {c.title_paragraph_idx for c in doc.captions if c.title_paragraph_idx}
    result: list[Ref] = []
    for p in doc.paragraphs:
        if p.cell is not None or not p.text or p.idx in captions:
            continue
        kind_sec = section_kind_of(doc, p.section_id)
        if kind_sec in ("TITLE", "TOC", "BIBLIOGRAPHY"):
            continue
        text = p.text
        for kind, pattern in _REF_PATTERNS.items():
            for m in pattern.finditer(text):
                see = bool(_SEE.search(text[max(0, m.start() - 8) : m.start()]))
                for target, in_range in _expand(m.group("n"), m.group("rest") or "", kind):  # type: ignore[arg-type]
                    result.append(Ref(kind, target, Mention(p.idx, m.span()), see, in_range))  # type: ignore[arg-type]
        for m in _SOURCE.finditer(text):
            if _DECIMALS.search(m.group("body")):
                continue  # «[0,03; 0,50]» — доверительный интервал, а не ссылка
            numbers = _expand_source(m.group("body"))
            result.extend(Ref("source", n, Mention(p.idx, m.span())) for n in numbers)
    result.sort(key=lambda r: (r.loc.paragraph_idx or 0, r.loc.span, r.kind, r.target))
    return result


# Номер источника не бывает 0 и не начинается с 0: «[0,03; 0,50]» — дробные числа.
_DECIMALS = re.compile(r"(?<!\d)0\d*")


def _expand_source(body: str) -> list[str]:
    out: list[str] = []
    tokens = re.split(r"\s*([,;–—-])\s*", body)
    prev: str | None = None
    sep = ","
    for tok in tokens:
        if tok in (",", ";", "–", "—", "-"):
            sep = tok
            continue
        if sep in "–—-" and prev and prev.isdigit() and 0 < int(tok) - int(prev) <= 200:
            out.extend(str(n) for n in range(int(prev) + 1, int(tok) + 1))
        else:
            out.append(tok)
        prev = tok
    return out
