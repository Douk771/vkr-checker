"""Нормализация текста и пословный diff (общие помощники DIF-01..04)."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from vkr_checker.report.schema import Segment

_WORD_TOKEN = re.compile(r"\s+|\w+|[^\w\s]")
_SPACES = re.compile(r"\s+")
_LEADING_NUMBER = re.compile(
    r"^\s*(?:глава\s+\d+|приложение\s+[а-яa-z0-9]+|\d+(?:\.\d+)*\.?)\s*[.:\-–—]?\s*", re.IGNORECASE
)


def squash(text: str) -> str:
    """Пробелы схлопнуты, Unicode приведён к NFC; регистр сохраняется."""
    return _SPACES.sub(" ", unicodedata.normalize("NFC", text)).strip()


def fold(text: str) -> str:
    """Для сопоставления: нижний регистр, ё -> е, пробелы схлопнуты."""
    return squash(text).lower().replace("ё", "е")


def norm_title(title: str) -> str:
    """Заголовок без номера («Глава 2», «2.1», «Приложение А»), для сопоставления разделов."""
    return fold(_LEADING_NUMBER.sub("", squash(title), count=1))


def _merge(segments: list[Segment]) -> list[Segment]:
    merged: list[Segment] = []
    for seg in segments:
        if merged and merged[-1].op == seg.op:
            merged[-1] = Segment(op=seg.op, text=merged[-1].text + seg.text)
        else:
            merged.append(seg)
    return merged


def word_segments(old: str, new: str) -> list[Segment]:
    """Пословный diff: сегменты equal / del / ins в порядке текста."""
    a, b = _WORD_TOKEN.findall(old), _WORD_TOKEN.findall(new)
    out: list[Segment] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.append(Segment(op="equal", text="".join(a[i1:i2])))
            continue
        if i2 > i1:
            out.append(Segment(op="del", text="".join(a[i1:i2])))
        if j2 > j1:
            out.append(Segment(op="ins", text="".join(b[j1:j2])))
    return _merge(out)
