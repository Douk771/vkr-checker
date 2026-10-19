"""Слой фактов (ARCHITECTURE_CHECKS.md §3): ленивые общие извлечения.

Факты добавляются в B-32 как `functools.cached_property` класса Facts; правила, diff и
матрица берут их отсюда, а не извлекают заново.
"""

from __future__ import annotations

from vkr_checker.model.document import Document


class Facts:
    def __init__(self, doc: Document) -> None:
        self.doc = doc
