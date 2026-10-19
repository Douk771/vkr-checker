"""Предупреждения о шрифтах, которых нет в системе вёрстки (ARCHITECTURE.md §8.5)."""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache

from vkr_checker.model.document import Document

# метрически совместимые замены, которые ставятся в образ (ARCHITECTURE.md §2.3)
METRIC_ALIASES: dict[str, str] = {
    "times new roman": "Liberation Serif",
    "arial": "Liberation Sans",
    "courier new": "Liberation Mono",
    "calibri": "Carlito",
    "cambria": "Caladea",
}


@lru_cache(maxsize=1)
def installed_families() -> frozenset[str] | None:
    """Семейства шрифтов системы (fc-list) в нижнем регистре; None - узнать нельзя."""
    exe = shutil.which("fc-list")
    if exe is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603
            [exe, ":", "family"], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    names = {n.strip().lower() for line in out.splitlines() for n in line.split(",") if n.strip()}
    return frozenset(names) or None


def document_fonts(doc: Document) -> list[str]:
    """Шрифты, которыми набран текст (по числу символов, от частых к редким)."""
    weight: dict[str, int] = {}
    for p in doc.paragraphs:
        for r in p.runs:
            if r.font:
                weight[r.font] = weight.get(r.font, 0) + len(r.text)
    return [f for f, _ in sorted(weight.items(), key=lambda kv: (-kv[1], kv[0]))]


def font_substitutions(doc: Document, installed: frozenset[str] | None = None) -> list[str]:
    """Сообщения о шрифтах без установленной замены. Пусто, если список шрифтов неизвестен."""
    installed = installed if installed is not None else installed_families()
    if installed is None:
        return []
    result: list[str] = []
    for font in document_fonts(doc):
        key = font.lower()
        if key in installed:
            continue
        alias = METRIC_ALIASES.get(key)
        if alias and alias.lower() in installed:
            continue
        result.append(f"{font}: нет в системе вёрстки, страницы могут отличаться от Word")
    return result
