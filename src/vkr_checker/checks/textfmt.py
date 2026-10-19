"""Форматирование чисел для сообщений правил: по-русски, с запятой."""

from __future__ import annotations


def fmt_num(value: float, digits: int = 2) -> str:
    """1.50 -> «1,5», 3.0 -> «3», 0.254 -> «0,25»."""
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return (text or "0").replace(".", ",")
