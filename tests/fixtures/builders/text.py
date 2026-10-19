"""Детерминированный нейтральный псевдо-научный текст для синтетических ВКР.

Свой словарь, вымышленные фамилии из фиксированного списка, без фрагментов методички.
"""

from __future__ import annotations

import random

CHARS_PER_PAGE = 1800  # ориентир: 14 pt, интервал 1,5, поля 3/1,5 (ARCHITECTURE.md §8.5)

SURNAMES = [
    "Иванова", "Петров", "Сидорова", "Кузнецов", "Орлова", "Беляев", "Громова", "Лебедев",
    "Фролова", "Тихонов", "Макарова", "Ершов", "Зайцева", "Воробьёв", "Крылова", "Дьячков",
]  # fmt: skip
INITIALS = ["А.А.", "Б.В.", "В.Г.", "Д.Е.", "Е.Ж.", "И.К.", "Л.М.", "Н.О."]

SUBJECTS = [
    "учебная мотивация", "эмоциональная устойчивость", "профессиональная идентичность",
    "коммуникативная компетентность", "самоорганизация деятельности", "стрессоустойчивость",
    "социальная адаптация", "самооценка личности", "познавательная активность",
    "ценностные ориентации",
]  # fmt: skip
VERBS = [
    "рассматривается", "исследуется", "описывается", "соотносится", "определяется",
    "анализируется", "уточняется", "сопоставляется",
]  # fmt: skip
CONTEXTS = [
    "в современной литературе", "в рамках выбранного подхода", "на разных этапах обучения",
    "в условиях образовательной среды", "у студентов старших курсов", "в учебной группе",
    "при взаимодействии участников", "с учётом возрастных особенностей",
]  # fmt: skip
TAILS = [
    "что позволяет выделить устойчивые закономерности",
    "однако единого понимания пока не сложилось",
    "поэтому важно учитывать контекст исследования",
    "и это подтверждается наблюдениями разных авторов",
    "хотя отдельные аспекты остаются дискуссионными",
    "что задаёт логику дальнейшего анализа",
]  # fmt: skip


class TextGen:
    """Генератор текста с управляемым объёмом. Один seed -> один и тот же текст."""

    def __init__(self, seed: int = 1) -> None:
        self._rnd = random.Random(seed)

    def author(self) -> str:
        return f"{self._rnd.choice(SURNAMES)} {self._rnd.choice(INITIALS)}"

    def sentence(self) -> str:
        r = self._rnd
        subject = r.choice(SUBJECTS)
        text = f"{subject.capitalize()} {r.choice(VERBS)} {r.choice(CONTEXTS)}, {r.choice(TAILS)}."
        if r.random() < 0.3:
            text = f"{text[:-1]} ({self.author()[:-4].strip()}, {r.randint(2008, 2023)})."
        return text

    def paragraph(self, min_chars: int = 500, max_chars: int = 900) -> str:
        target = self._rnd.randint(min_chars, max_chars)
        parts: list[str] = []
        while sum(len(p) + 1 for p in parts) < target:
            parts.append(self.sentence())
        return " ".join(parts)

    def paragraphs_for_pages(self, pages: float) -> list[str]:
        """Абзацы суммарным объёмом ~pages страниц (по CHARS_PER_PAGE)."""
        total = int(pages * CHARS_PER_PAGE)
        result: list[str] = []
        used = 0
        while used < total:
            para = self.paragraph()
            result.append(para)
            used += len(para)
        return result

    def bib_entry(self, n: int) -> str:
        r = self._rnd
        title = r.choice(SUBJECTS).capitalize()
        return (
            f"{self.author()} {title} в образовании: теория и практика. "
            f"М.: Учебная книга, {r.randint(2005, 2023)}. {r.randint(120, 480)} с."
        )
