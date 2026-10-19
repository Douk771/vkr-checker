"""Фамилии авторов (MET-02..04, матрица): «И.О. Фамилия», «Фамилия И.О.», «Фамилия (год)»."""

from __future__ import annotations

import re
from dataclasses import dataclass

from vkr_checker.model.document import Document
from vkr_checker.nlp.morph import is_known_common_word, surname_key, surname_normal_form

from .common import Mention, chapter_number, section_kind_of

_CYR = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
_INIT = r"[А-ЯЁ]\.\s?[А-ЯЁ]\.?"
_YEAR = r"(?:19|20)\d{2}[а-яa-z]?"
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("initials_first", re.compile(rf"(?<![А-ЯЁа-яё])(?P<ini>{_INIT})\s*(?P<sn>{_CYR})")),
    ("surname_first", re.compile(rf"(?P<sn>{_CYR})\s+(?P<ini>{_INIT})")),
    ("surname_year", re.compile(rf"(?P<sn>{_CYR})\s*(?:\(|,\s*){_YEAR}")),
    ("latin_year", re.compile(rf"(?P<sn>[A-Z][a-z]{{2,}})\s*(?:\(|,\s*){_YEAR}")),
)


@dataclass(frozen=True, slots=True)
class AuthorMention:
    surname: str  # именительный падеж (для показа)
    key: str  # для сравнения: без падежных окончаний, нижний регистр
    raw: str
    pattern: str
    loc: Mention
    section_kind: str
    chapter: int | None


def _accept(sn: str, pattern: str) -> bool:
    if pattern == "latin_year":
        return True
    return not is_known_common_word(sn.split("-")[0])


def extract_authors(doc: Document) -> list[AuthorMention]:
    result: list[AuthorMention] = []
    for p in doc.paragraphs:
        if p.cell is not None or not p.text:
            continue
        kind = section_kind_of(doc, p.section_id)
        if kind in ("TITLE", "TOC", "BIBLIOGRAPHY"):
            continue
        taken: list[tuple[int, int]] = []
        chapter = chapter_number(doc, p.section_id)
        for name, pattern in PATTERNS:
            for m in pattern.finditer(p.text):
                if any(m.start() < e and s < m.end() for s, e in taken):
                    continue
                sn = m.group("sn")
                if not _accept(sn, name):
                    continue
                taken.append(m.span())
                latin = name == "latin_year"
                result.append(
                    AuthorMention(
                        surname=sn if latin else surname_normal_form(sn),
                        key=sn.lower() if latin else surname_key(sn),
                        raw=m.group(),
                        pattern=name,
                        loc=Mention(p.idx, m.span("sn")),
                        section_kind=kind,
                        chapter=chapter,
                    )
                )
    result.sort(key=lambda a: (a.loc.paragraph_idx or 0, a.loc.span))
    return result


def authors_in(text: str) -> list[tuple[str, str]]:
    """[(фамилия, ключ)] в произвольном фрагменте текста (для методик и введения)."""
    found: list[tuple[str, str]] = []
    taken: list[tuple[int, int]] = []
    for name, pattern in PATTERNS[:2]:
        for m in pattern.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            sn = m.group("sn")
            if _accept(sn, name):
                taken.append(m.span())
                found.append((surname_normal_form(sn), surname_key(sn)))
    return found
