"""Все регулярки и словари распознавания структуры (пересказ, без дословных фрагментов)."""

from __future__ import annotations

import re

from vkr_checker.nlp.normalize import normalize_text

ROMAN = {"I": 1, "V": 5, "X": 10}

# --- имена разделов уровня 1 (после normalize_text: нижний регистр, ё->е) -------------------
KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TOC", re.compile(r"^(оглавление|содержание)\b")),
    ("INTRO", re.compile(r"^введение\b")),
    ("CONCLUSION", re.compile(r"^(заключение|общие\s+выводы|основные\s+выводы)\b")),
    (
        "BIBLIOGRAPHY",
        re.compile(
            r"^(список|перечень)\s+(использованн\w+\s+|используем\w+\s+)?"
            r"(литератур\w*|источник\w*)|^библиографическ\w+\s+список|^литература$"
        ),
    ),
    ("APPENDIX", re.compile(r"^приложени[ея]\b")),
    ("CHAPTER_CONCLUSIONS", re.compile(r"^выводы\b")),
    ("CHAPTER", re.compile(r"^глава\b")),
)
ROOT_KINDS = frozenset({"TOC", "INTRO", "CONCLUSION", "BIBLIOGRAPHY", "APPENDIX", "CHAPTER"})

# --- номера в заголовках -------------------------------------------------------------------
CHAPTER_NUM = re.compile(
    r"^\s*глава\s+(?P<n>\d+|[IVX]+)\s*[.:\-–—)]?\s*(?P<title>.*)$", re.IGNORECASE | re.DOTALL
)
NUMBERED = re.compile(r"^\s*(?P<n>\d+(?:\.\d+){0,3})\s*[.)]?\s+(?P<title>\S.*)$", re.DOTALL)
NUMBER_ONLY = re.compile(r"^\s*(?P<n>\d+(?:\.\d+){0,3})\s*[.)]?\s*$")
APPENDIX_HEAD = re.compile(
    r"^\s*приложени[ея]\s*(?:№\s*)?(?P<key>[А-ЯA-Z]\b|\d+)?[\s.:\-–—)]*(?P<title>.*)$",
    re.IGNORECASE | re.DOTALL,
)
ROLE_THEORY = re.compile(r"теоретич", re.IGNORECASE)
ROLE_EMPIRIC = re.compile(r"эмпирич|экспериментальн|практическ\w+\s+част", re.IGNORECASE)

# --- оглавление ----------------------------------------------------------------------------
TOC_STYLE = re.compile(r"^(toc|оглавлени\w*|содержани\w*)\s*(\d)?$", re.IGNORECASE)
TOC_LINE = re.compile(r"^(?P<text>.*?\S)[\s.·…_\-–—]*[\t.·…_\s]\s*(?P<page>\d{1,4})\s*$")
TOC_LINE_STRICT = re.compile(r"^.*\S(?:[\t]|\s*[.·…]{2,}\s*|\s{2,})(?:\d{1,4})\s*$")

# --- подписи -------------------------------------------------------------------------------
CAPTION = re.compile(
    r"^\s*(?P<label>таблица|табл\.|рисунок|рис\.)\s*(?:№\s*)?"
    r"(?P<num>(?:[А-ЯA-Z]\.)?\d+(?:[.\-]\d+)*)\s*(?P<sep>[.:\-–—]?)\s*(?P<title>.*)$",
    re.IGNORECASE | re.DOTALL,
)
HEADING_STYLE = re.compile(r"^(heading|заголовок)\s*(\d)", re.IGNORECASE)


def classify_name(text: str) -> str | None:
    """Вид раздела по названию (без номера); None - название неизвестно."""
    norm = normalize_text(text)
    for kind, pattern in KIND_PATTERNS:
        if pattern.search(norm):
            return kind
    return None


def roman_to_int(value: str) -> int | None:
    total = 0
    prev = 0
    for ch in reversed(value.upper()):
        n = ROMAN.get(ch)
        if n is None:
            return None
        total += -n if n < prev else n
        prev = max(prev, n)
    return total


def clean_number(raw: str | None) -> str | None:
    """'1.' -> '1', '1.2.' -> '1.2'; римские -> арабские; пусто -> None."""
    if not raw:
        return None
    raw = raw.strip().rstrip(".)").strip()
    if not raw:
        return None
    if raw.isalpha():
        value = roman_to_int(raw)
        return str(value) if value else raw
    return raw


def number_depth(number: str | None) -> int:
    return number.count(".") + 1 if number else 0
