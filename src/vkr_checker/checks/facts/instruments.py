"""Методики из параграфа 2.1 (MET-02, матрица): название в кавычках, аббревиатура, авторы."""

from __future__ import annotations

import re
from dataclasses import dataclass

from vkr_checker.model.document import Document
from vkr_checker.nlp.sentences import split_sentences

from .authors import authors_in
from .common import Mention, paragraphs_in

_QUOTED = re.compile(r"[«\"“„]([^»\"”“]{3,120})[»\"”]")
_ABBR = re.compile(r"\(\s*([А-ЯЁA-Z][А-ЯЁA-Z0-9\-]{1,9})\s*\)")
_KIND_WORD = re.compile(
    r"методик|опросник|шкал|тест\b|теста|анкет|инвентар|диагностик|индекс|вопросник",
    re.IGNORECASE,
)
_ADAPT = re.compile(
    r"адаптаци\w+\s+((?:[А-ЯЁ]\.\s?){1,2}[А-ЯЁа-яё-]+|[^.;()]{3,80})", re.IGNORECASE
)
INSTRUMENT_WINDOW = 80


@dataclass(frozen=True, slots=True)
class Instrument:
    name: str
    abbr: str | None
    authors: tuple[tuple[str, str], ...]  # (фамилия, ключ)
    adaptation: str | None
    loc: Mention


def extract_instruments(doc: Document) -> list[Instrument]:
    section = next((s for s in doc.sections if s.number == "2.1"), None)
    result: list[Instrument] = []
    seen: set[str] = set()
    for p in paragraphs_in(doc, section):
        if p.idx == getattr(section, "heading_paragraph_idx", None):
            continue
        for s in split_sentences(p.text):
            for q in _QUOTED.finditer(s.text):
                before = s.text[max(0, q.start() - INSTRUMENT_WINDOW) : q.start()]
                after = s.text[q.end() : q.end() + 30]
                if not (_KIND_WORD.search(before) or _KIND_WORD.search(q.group(1))):
                    continue
                name = " ".join(q.group(1).split())
                if name.lower() in seen:
                    continue
                seen.add(name.lower())
                abbr_m = _ABBR.match(after.lstrip()) or _ABBR.search(s.text)
                adapt = _ADAPT.search(s.text)
                result.append(
                    Instrument(
                        name=name,
                        abbr=abbr_m.group(1) if abbr_m else None,
                        authors=tuple(dict.fromkeys(authors_in(s.text))),
                        adaptation=" ".join(adapt.group(1).split()) if adapt else None,
                        loc=Mention(p.idx, (s.start + q.start(), s.start + q.end())),
                    )
                )
    return result
