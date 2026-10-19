"""Нормализация текста для сопоставления (ARCHITECTURE.md §8.3-§8.4, checks, diff)."""

from __future__ import annotations

import re
import unicodedata

SOFT_HYPHEN = "­"
_SPACES = re.compile(r"\s+")
_HYPHEN_BREAK = re.compile(r"(\w)[-‐‑]\s*\n\s*(\w)")
_NON_ALNUM = re.compile(r"[^0-9a-zа-я]+")


def collapse_spaces(text: str) -> str:
    """Любые пробельные символы (в т.ч. неразрывные, табы, переводы строк) -> один пробел."""
    return _SPACES.sub(" ", text).strip()


def normalize_text(text: str) -> str:
    """NFKC, ё->е, без мягких переносов, одинарные пробелы, нижний регистр."""
    text = unicodedata.normalize("NFKC", text).replace(SOFT_HYPHEN, "")
    text = text.replace("ё", "е").replace("Ё", "Е")
    return collapse_spaces(text).lower()


def join_hyphenated_lines(text: str) -> str:
    """Склеивает слова, перенесённые дефисом в конце строки (текст из PDF)."""
    return _HYPHEN_BREAK.sub(r"\1\2", text)


def normalize_key(text: str) -> str:
    """Ключ для поиска/выравнивания: только буквы и цифры нижнего регистра, без пробелов."""
    return _NON_ALNUM.sub("", normalize_text(text))


def normalize_number(text: str) -> str:
    """'1 234,5' / '1 234.5' -> '1234.5' (для сравнения чисел в отчёте и diff)."""
    cleaned = re.sub(r"[\s  ]", "", text).replace(",", ".").replace("−", "-")
    return cleaned
