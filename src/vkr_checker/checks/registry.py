"""Реестр правил. Модули с правилами импортируются явно (без автосканирования): порядок
регистрации детерминирован, а порядок выполнения всё равно задаётся сортировкой по rule_id.
"""

from __future__ import annotations

import importlib
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


RULE_MODULES = (
    "vkr_checker.checks.not_checked",
    "vkr_checker.checks.structure",
    "vkr_checker.checks.tables_format",
    "vkr_checker.checks.typography",
    "vkr_checker.checks.tables_place",
    "vkr_checker.checks.volume",
    "vkr_checker.checks.numbering",
    "vkr_checker.checks.bibliography",
    "vkr_checker.checks.intro",
    "vkr_checker.checks.consistency",
)  # явный список: порядок импорта детерминирован, автосканирования нет
_loaded = False
_stash: dict[str, Rule] | None = None


def load_rule_modules() -> None:
    """Импортирует модули с правилами (идемпотентно); декораторы @register наполняют реестр."""
    global _loaded
    if not _loaded:
        _loaded = True
        for name in RULE_MODULES:
            importlib.import_module(name)


def all_rules() -> list[Rule]:
    """Правила в порядке rule_id."""
    load_rule_modules()
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def clear_for_tests() -> None:
    """Очищает реестр для теста; `restore_for_tests` возвращает прежнее содержимое."""
    global _stash
    load_rule_modules()
    if _stash is None:
        _stash = dict(_REGISTRY)
    _REGISTRY.clear()


def restore_for_tests() -> None:
    global _stash
    if _stash is not None:
        _REGISTRY.clear()
        _REGISTRY.update(_stash)
        _stash = None
