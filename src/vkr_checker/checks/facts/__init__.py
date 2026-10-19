"""Слой фактов (ARCHITECTURE_CHECKS.md §3): ленивые общие извлечения.

Каждый факт считается один раз (`cached_property`) и общий для правил, diff и матрицы.
Правила не меняют Facts и Document.
"""

from __future__ import annotations

from functools import cached_property

from vkr_checker.model.document import Document
from vkr_checker.nlp.sentences import Sentence, split_sentences

from .authors import AuthorMention, extract_authors
from .hypothesis import (
    HypothesisMention,
    HypothesisPart,
    extract_hypothesis_mentions,
    extract_hypothesis_parts,
)
from .instruments import Instrument, extract_instruments
from .intro import IntroElement, extract_intro_elements
from .methods import MethodMention, extract_methods
from .quantities import Quantity, extract_quantities
from .refs import Ref, extract_refs
from .tasks import ListItem, conclusion_items, items_from_element, section_items

__all__ = [
    "AuthorMention", "Facts", "HypothesisMention", "HypothesisPart", "Instrument",
    "IntroElement", "ListItem", "MethodMention", "Quantity", "Ref",
]  # fmt: skip


class Facts:
    def __init__(self, doc: Document) -> None:
        self.doc = doc
        self._sentences: dict[int, list[Sentence]] = {}

    def sentences(self, paragraph_idx: int) -> list[Sentence]:
        """Предложения абзаца со смещениями (кэш по номеру абзаца)."""
        if paragraph_idx not in self._sentences:
            self._sentences[paragraph_idx] = split_sentences(self.doc.paragraph(paragraph_idx).text)
        return self._sentences[paragraph_idx]

    @cached_property
    def quantities(self) -> list[Quantity]:
        return extract_quantities(self.doc)

    @cached_property
    def methods(self) -> list[MethodMention]:
        return extract_methods(self.doc)

    @cached_property
    def intro_elements(self) -> dict[str, list[IntroElement]]:
        return extract_intro_elements(self.doc)

    @cached_property
    def hypotheses(self) -> list[HypothesisPart]:
        return extract_hypothesis_parts(self.doc, self.intro_elements)

    @cached_property
    def hypothesis_mentions(self) -> list[HypothesisMention]:
        return extract_hypothesis_mentions(self.doc)

    def _items(self, key: str) -> list[ListItem]:
        for element in self.intro_elements.get(key, []):
            if element.position != "inline":
                return items_from_element(self.doc, element)
        return []

    @cached_property
    def tasks(self) -> list[ListItem]:
        return self._items("tasks")

    @cached_property
    def defense_positions(self) -> list[ListItem]:
        return self._items("defense")

    @cached_property
    def conclusions(self) -> list[ListItem]:
        return conclusion_items(self.doc, "CONCLUSION")

    @cached_property
    def chapter_conclusions(self) -> dict[str, list[ListItem]]:
        return {
            s.id: section_items(self.doc, s)
            for s in self.doc.sections
            if s.kind == "CHAPTER_CONCLUSIONS"
        }

    @cached_property
    def instruments(self) -> list[Instrument]:
        return extract_instruments(self.doc)

    @cached_property
    def authors(self) -> list[AuthorMention]:
        return extract_authors(self.doc)

    @cached_property
    def refs(self) -> list[Ref]:
        return extract_refs(self.doc)
