"""Упоминания статистических методов по словарю (MET-01, LEX-01, DIF-05.3, матрица)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vkr_checker.model.document import Document
from vkr_checker.nlp.lexicons.methods import METHODS

from .common import Mention, iter_text_units


@dataclass(frozen=True, slots=True)
class MethodMention:
    method_id: str
    kind: Literal["name", "stat"]  # назван словами или обозначением статистики
    loc: Mention
    text: str
    section_kind: str
    in_table: bool = False


def extract_methods(doc: Document) -> list[MethodMention]:
    result: list[MethodMention] = []
    for mention, text, kind in iter_text_units(doc):
        for mdef in METHODS.values():
            for what, patterns in (("name", mdef.names), ("stat", mdef.stats)):
                for pattern in patterns:
                    for m in pattern.finditer(text):
                        loc = Mention(mention.paragraph_idx, m.span(), mention.cell)
                        result.append(
                            MethodMention(
                                mdef.id, what, loc, m.group(), kind, mention.cell is not None
                            )  # type: ignore[arg-type]
                        )
    result.sort(key=lambda x: (x.loc.paragraph_idx or 0, x.loc.span, x.method_id))
    return result
