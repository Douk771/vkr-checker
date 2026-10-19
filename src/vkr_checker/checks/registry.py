"""Реестр правил. Модули с правилами импортируются явно (без автосканирования): порядок
регистрации детерминирован, а порядок выполнения всё равно задаётся сортировкой по rule_id.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from vkr_checker.checks.base import Rule

T = TypeVar("T")
_REGISTRY: dict[str, Rule] = {}


def register(cls: Callable[[], T]) -> Callable[[], T]:
    """Декоратор класса правила: создаёт экземпляр и кладёт в реестр по `id`."""
    rule = cls()
    rule_id = rule.id  # type: ignore[attr-defined]
    if rule_id in _REGISTRY:
        raise ValueError(f"правило {rule_id} уже зарегистрировано")
    _REGISTRY[rule_id] = rule  # type: ignore[assignment]
    return cls


def all_rules() -> list[Rule]:
    """Правила в порядке rule_id. Модули-правила импортируются здесь явно."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def clear_for_tests() -> None:
    _REGISTRY.clear()
