"""Входные данные и внутренние результаты сравнения (не входят в JSON напрямую)."""

from __future__ import annotations

from dataclasses import dataclass, field

from vkr_checker.checks.base import CheckContext
from vkr_checker.model.document import Document
from vkr_checker.report.schema import CheckReport, NumberChange


@dataclass(frozen=True)
class Side:
    """Одна версия работы после полного конвейера."""

    doc: Document
    ctx: CheckContext
    report: CheckReport


@dataclass(frozen=True)
class TypedNumberChange:
    """NumberChange плюс данные, нужные DIF-05.1 (ключ величины и её старое значение)."""

    api: NumberChange
    new_idx: int
    key: tuple[str, str] | None = None  # (kind, qualifier) из quantities, иначе None
    old_value: str | None = None


@dataclass(frozen=True)
class ObjectMatch:
    """Таблица или рисунок: сопоставление для DIF-04 и DIF-05.4/5.6."""

    kind: str  # table | figure
    old_no: str | None
    new_no: str | None
    old_label: str | None
    new_label: str | None
    changed_cells: tuple[tuple[int, int, int], ...] = ()  # (table_idx новой, строка, столбец)
    new_table_idx: int | None = None

    @property
    def removed(self) -> bool:
        return self.new_label is None and self.old_label is not None

    @property
    def renumbered(self) -> bool:
        return self.old_no is not None and self.new_no is not None and self.old_no != self.new_no


@dataclass
class DiffState:
    """Всё, что DIF-05 нужно знать о результатах DIF-01..04."""

    unchanged_new: set[int] = field(default_factory=set)
    changed_new: set[int] = field(default_factory=set)
    number_changes: list[TypedNumberChange] = field(default_factory=list)
    objects: list[ObjectMatch] = field(default_factory=list)
