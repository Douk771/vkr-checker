"""Разбиение на предложения со смещениями и защитой сокращений (ARCHITECTURE_CHECKS.md §3)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Сокращения, после которых точка не заканчивает предложение (нижний регистр, без точки).
ABBREVIATIONS = frozenset(
    {
        "т", "д", "п", "е", "к", "н", "др", "пр", "см", "напр", "рис", "табл", "стр", "с", "г",
        "гг", "им", "ст", "ч", "тыс", "млн", "млрд", "руб", "проф", "доц", "акад", "канд", "докт",
        "ред", "изд", "пер", "вып", "т.д", "т.п", "т.е", "т.к", "т.н", "т.о", "в", "вв", "ок",
        "прим", "разд", "гл", "ср", "англ", "нем", "фр", "лат", "так", "т.ч", "и.о", "прил",
    }
)  # fmt: skip
# Сокращения, которыми обычно заканчивается предложение: перед заглавной буквой делим.
SENTENCE_FINAL = frozenset({"т.д", "т.п", "др", "пр", "т.е", "т.ч"})
_CANDIDATE = re.compile(r"[.!?…]+[\"»”')\]]*(?=\s+\S)")
_WORD_BEFORE = re.compile(r"([\w][\w.\-]*)$", re.UNICODE)
_STARTER = re.compile(r"[A-ZА-ЯЁ0-9«\"“(\[—–-]")
_INITIAL = re.compile(r"^[A-ZА-ЯЁ]$")


@dataclass(frozen=True, slots=True)
class Sentence:
    text: str
    start: int  # смещение в исходном тексте
    end: int


def _is_boundary(text: str, dot_pos: int, after: int) -> bool:
    """Точка в позиции dot_pos заканчивает предложение?"""
    next_char = text[after]
    if not _STARTER.match(next_char):
        return False
    if text[dot_pos] != ".":
        return True  # ! ? …
    word_match = _WORD_BEFORE.search(text[:dot_pos])
    word = word_match.group(1) if word_match else ""
    low = word.lower().strip(".")
    # десятичное число 0.05 сюда не попадает (после точки нет пробела); ссылка «p. 5»
    if _INITIAL.match(word.split(".")[-1] if "." in word else word):
        return False  # инициалы «А.А. Иванов», «И. О. Фамилия»
    if low in SENTENCE_FINAL:
        return next_char.isupper()
    if low in ABBREVIATIONS:
        return False
    if low.isdigit() and next_char.isdigit():
        return False
    if next_char in "—–-" and not text[after : after + 2].strip("—–- "):
        return True
    return next_char.isupper() or next_char in '«"“([' or next_char.isdigit()


def split_sentences(text: str) -> list[Sentence]:
    """Предложения с позициями. Пробелы по краям отрезаются, пустые не возвращаются."""
    result: list[Sentence] = []
    start = 0
    for m in _CANDIDATE.finditer(text):
        term_pos = m.start() + len(m.group().rstrip("\"»”')]")) - 1  # последний знак конца
        after = m.end()
        while after < len(text) and text[after].isspace():
            after += 1
        if after >= len(text):
            break
        if _is_boundary(text, term_pos, after):
            _emit(text, start, m.end(), result)
            start = after
    _emit(text, start, len(text), result)
    return result


def _emit(text: str, start: int, end: int, out: list[Sentence]) -> None:
    chunk = text[start:end]
    stripped = chunk.strip()
    if stripped:
        lead = len(chunk) - len(chunk.lstrip())
        out.append(Sentence(stripped, start + lead, start + lead + len(stripped)))
