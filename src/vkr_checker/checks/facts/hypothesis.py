"""Гипотеза: части из введения, упоминания и статусы в главе 2 и заключении (HYP-01, матрица)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from vkr_checker.model.document import Document
from vkr_checker.nlp.sentences import split_sentences

from .common import Mention, chapter_number, section_kind_of
from .intro import IntroElement
from .tasks import ListItem, items_from_element

_HYP_WORD = re.compile(r"гипотез\w*", re.IGNORECASE)
_HYP_HEAD = re.compile(
    r"^\s*(?:рабоч\w+\s+|общ\w+\s+|частн\w+\s+)?гипотез\w*\s*\d*\s*[:.\-–—]?\s*", re.IGNORECASE
)
# Только глагольные и краткие причастные формы статуса; «для подтверждения гипотезы» не в счёт.
_CONFIRMED = re.compile(
    r"подтверд(?:ил\w*|ит\w*)|подтвержд(?:ен[аоы]?|ён|ается|аются|ала|ало|али|ался|ались)(?!\w)",
    re.IGNORECASE,
)
STATUS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("not_confirmed", re.compile(r"не\s+(?:был\w*\s+)?подтвер\w+", re.IGNORECASE)),
    ("partially_confirmed", re.compile(r"частично\s+(?:был\w*\s+)?подтвер\w+", re.IGNORECASE)),
    ("mostly_confirmed", re.compile(r"в\s+основном\s+(?:был\w*\s+)?подтвер\w+", re.IGNORECASE)),
    ("confirmed", _CONFIRMED),
)
STATUS_TITLES = {
    "not_confirmed": "не подтверждена",
    "partially_confirmed": "частично подтверждена",
    "mostly_confirmed": "в основном подтверждена",
    "confirmed": "подтверждена",
}


@dataclass(frozen=True, slots=True)
class HypothesisPart:
    index: int
    text: str
    loc: Mention


@dataclass(frozen=True, slots=True)
class HypothesisMention:
    section_kind: str  # CHAPTER | CHAPTER_CONCLUSIONS | CONCLUSION
    chapter: int | None
    text: str
    status: str | None
    loc: Mention


def status_of(text: str) -> str | None:
    for name, pattern in STATUS_PATTERNS:
        if pattern.search(text):
            return name
    return None


def extract_hypothesis_parts(
    doc: Document, elements: dict[str, list[IntroElement]]
) -> list[HypothesisPart]:
    items: list[ListItem] = []
    for element in elements.get("hypothesis", []):
        if element.position == "inline":
            continue
        items.extend(items_from_element(doc, element))
    parts: list[HypothesisPart] = []
    for item in items:
        text = _HYP_HEAD.sub("", item.text).strip()
        if text:
            parts.append(
                HypothesisPart(len(parts) + 1, text, Mention(item.paragraph_idx, item.span))
            )
    return parts


def extract_hypothesis_mentions(doc: Document) -> list[HypothesisMention]:
    """Предложения о гипотезе в главе 2 и далее, выводах к главам и заключении."""
    result: list[HypothesisMention] = []
    for p in doc.paragraphs:
        if p.cell is not None:
            continue
        kind = section_kind_of(doc, p.section_id)
        chapter = chapter_number(doc, p.section_id)
        in_scope = kind in ("CHAPTER_CONCLUSIONS", "CONCLUSION") or (
            kind == "CHAPTER" and chapter is not None and chapter >= 2
        )
        if not in_scope:
            continue
        sentences = split_sentences(p.text)
        for i, s in enumerate(sentences):
            if not _HYP_WORD.search(s.text):
                continue
            nxt = sentences[i + 1].text if i + 1 < len(sentences) else ""
            result.append(
                HypothesisMention(
                    section_kind=kind,
                    chapter=chapter,
                    text=s.text,
                    status=status_of(f"{s.text} {nxt}"),
                    loc=Mention(p.idx, (s.start, s.end)),
                )
            )
    return result
