"""Морфология: леммы pymorphy3 с кэшем, содержательные леммы (ARCHITECTURE_CHECKS.md §3)."""

from __future__ import annotations

import re
from functools import lru_cache

import pymorphy3

_WORD = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)*")
FUNCTION_POS = frozenset({"PREP", "CONJ", "PRCL", "NPRO", "INTJ", "PRED"})
MIN_LEMMA_LEN = 3

# Служебные глаголы формулировок задач: сами по себе тему не несут (лемма, ё->е).
TASK_VERBS = frozenset(
    {
        "изучить", "изучать", "выявить", "выявлять", "определить", "определять", "исследовать",
        "проанализировать", "анализировать", "разработать", "описать", "описывать", "обосновать",
        "установить", "устанавливать", "провести", "проводить", "рассмотреть", "рассматривать",
        "сравнить", "сравнивать", "оценить", "оценивать", "выделить", "выделять", "выяснить",
        "изучение", "выявление", "определение", "исследование", "анализ", "сравнение",
        "оценка", "проверить", "проверять", "раскрыть", "раскрывать", "уточнить", "уточнять",
    }
)  # fmt: skip
EXTRA_STOP = frozenset({"быть", "являться", "это", "также", "который", "свой", "весь", "такой"})


@lru_cache(maxsize=1)
def _analyzer() -> pymorphy3.MorphAnalyzer:
    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=200_000)
def _parse(word: str) -> tuple[str, str | None]:
    """(лемма, часть речи) для слова в нижнем регистре; результат кэшируется по слову."""
    best = _analyzer().parse(word)[0]  # parse() детерминирован: порядок по score, затем по словарю
    return best.normal_form.replace("ё", "е"), best.tag.POS


def tokens(text: str) -> list[str]:
    """Слова текста (кириллица/латиница, дефисные составные), нижний регистр."""
    return [m.group().lower() for m in _WORD.finditer(text)]


def lemma(word: str) -> str:
    return _parse(word.lower())[0]


def lemmas(text: str) -> list[str]:
    return [lemma(w) for w in tokens(text)]


def pos_of(word: str) -> str | None:
    return _parse(word.lower())[1]


def content_lemmas(text: str) -> list[str]:
    """Леммы значимых слов: без служебных частей речи, стоп-слов, коротких и глаголов задач."""
    result: list[str] = []
    for word in tokens(text):
        norm, pos = _parse(word)
        if pos in FUNCTION_POS or len(norm) < MIN_LEMMA_LEN:
            continue
        if norm in TASK_VERBS or norm in EXTRA_STOP:
            continue
        result.append(norm)
    return result


def content_lemma_set(text: str) -> frozenset[str]:
    return frozenset(content_lemmas(text))


def jaccard(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    """Коэффициент Жаккара; для двух пустых множеств 1.0 (нечего различать)."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def clear_cache() -> None:
    _parse.cache_clear()


_SURNAME_ENDINGS = (
    "ого", "его", "ому", "ему", "ыми", "ими", "ым", "им", "ом", "ем", "ой", "ую", "ых",
    "а", "у", "е", "ы", "я", "ю",
)  # fmt: skip


def surname_normal_form(word: str) -> str:
    """Фамилия в именительном падеже: pymorphy3 (тег Surn), иначе усечение падежного окончания.

    «Выготского» -> «Выготский», «Леонтьеву» -> «Леонтьев»; неизвестное слово не склоняется.
    """
    for parsed in _analyzer().parse(word):
        if "Surn" in parsed.tag:
            return parsed.normal_form.capitalize()
    return word[:1].upper() + word[1:].lower()


def surname_key(word: str) -> str:
    """Ключ для сравнения фамилий: нормальная форма, нижний регистр; для слов, которые
    pymorphy3 не опознал как фамилию, дополнительно отсекается падежное окончание."""
    for parsed in _analyzer().parse(word):
        if "Surn" in parsed.tag:
            return parsed.normal_form.lower().replace("ё", "е")
    base = word.lower().replace("ё", "е")
    for ending in _SURNAME_ENDINGS:
        if len(base) - len(ending) >= 4 and base.endswith(ending):
            return base[: -len(ending)]
    return base


def is_known_common_word(word: str) -> bool:
    """Слово из словаря, которое не может быть фамилией (нет разбора Surn)."""
    parses = _analyzer().parse(word)
    return parses[0].is_known and not any("Surn" in p.tag for p in parses)
