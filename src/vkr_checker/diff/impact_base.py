"""Общие части анализа последствий правок (DIF-05): правило-заглушка и помощники."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from vkr_checker.checks.base import Need, Source, new_finding
from vkr_checker.model.finding import Finding, Location

from .model import DiffState, Side


@dataclass(frozen=True)
class DifRule:
    """Минимальный объект с атрибутами правила: нужен new_finding."""

    id: str
    title: str
    block: str = "diff_impact"
    source: Source = Source("CH", "Сравнение версий")
    default_level: str = "suspicion"
    needs: frozenset[Need] = frozenset()
    priority: str = "must"


RULES = {
    "DIF-05.1": DifRule("DIF-05.1", "Число изменено, старое значение осталось"),
    "DIF-05.2": DifRule("DIF-05.2", "Введение и его отражения в тексте разошлись"),
    "DIF-05.3": DifRule("DIF-05.3", "Метод убран из описания, но упоминается дальше"),
    "DIF-05.4": DifRule("DIF-05.4", "Ссылка на старый номер таблицы или рисунка"),
    "DIF-05.5": DifRule("DIF-05.5", "Число объектов изменилось, фраза о числе нет"),
    "DIF-05.6": DifRule("DIF-05.6", "Расчёты изменены, выводы нет"),
}


@dataclass(frozen=True)
class ImpactInput:
    old: Side
    new: Side
    state: DiffState
    th: object


def finding(rule_id: str, message: str, key: str, locations: list[Location], **extra) -> Finding:
    return new_finding(
        RULES[rule_id],  # type: ignore[arg-type]
        message,
        fingerprint=f"{rule_id}|{key}",
        method=extra.pop("method", "fuzzy"),
        locations=locations,
        **extra,
    )


def assign_ids(findings: list[Finding]) -> list[Finding]:
    """id = sha1(rule_id | fingerprint | порядковый номер)[:12], как у правил проверки."""
    seen: dict[tuple[str, str], int] = {}
    out = []
    for f in findings:
        k = (f.rule_id, f.fingerprint)
        n = seen.get(k, 0)
        seen[k] = n + 1
        digest = hashlib.sha1(f"{f.rule_id}|{f.fingerprint}|{n}".encode()).hexdigest()[:12]
        out.append(f.model_copy(update={"id": digest}))
    return out
