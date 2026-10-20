"""NC-01: пункты «не проверяется кодом» (SPEC §4 NC-01, ARCHITECTURE_CHECKS.md §8.3).

Выводятся всегда. Пункты 8 и 9 (номера страниц оглавления, разрывы коротких таблиц) попадают
в список только при неудачной вёрстке: иначе их закрывают STR-06 и TBL-12.
"""

from __future__ import annotations

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.registry import register
from vkr_checker.model.finding import RuleResult
from vkr_checker.report.schema import NcItem

SRC_DATA = "[Ч] Данные и цифры"
LAYOUT_ONLY = frozenset({"NC-01.8", "NC-01.9"})

# (номер, название, источник, подсказка, helper)
_ITEMS: tuple[tuple[int, str, str, str, str | None], ...] = (
    (1, "Числа сверены с файлом данных", SRC_DATA,
     "Сверьте вручную: в отчёте есть список всех найденных чисел с местами.", "numbers_index"),
    (2, "Производные величины посчитаны по точным значениям", SRC_DATA,
     "Пересчитайте проценты, средние и суммы по исходным значениям, а не по округлённым.", None),
    (3, "Ключ методики в приложении совпадает с подсчётом", "[Ч] Данные и цифры",
     "Сравните ключ методики из приложения с тем, как считались баллы.", None),
    (4, "Нормы сверены с первоисточником и снабжены ссылкой со страницей", "[Ч] Данные и цифры",
     "Откройте первоисточник нормативов и проверьте значения и номер страницы.", None),
    (5, "Понятия интерпретации введены в главе 1", "[Ч] Теория и методики",
     "Для каждого понятия из обсуждения найдите его определение в главе 1.", "rule:MET-04"),
    (6, "Каждая часть гипотезы проверяется конкретным расчётом", "[Ч] Анализ",
     "Используйте матрицу связности: разрывы в столбце «Расчёт» требуют внимания.", "matrix"),
    (7, "В главе 2 нет методов сверх согласованного алгоритма", "[Ч] Анализ",
     "Сверьте список методов с планом обработки, согласованным с руководителем.", "rule:MET-01"),
    (8, "Номера страниц в оглавлении", "[Ч] Оформление",
     "Обновите оглавление в Word и сверьте номера страниц.", None),
    (9, "Короткие таблицы не разрываются между страницами", "[Ч] Оформление таблиц",
     "Пролистайте работу в Word и найдите таблицы, перенесённые на следующую страницу.", None),
    (10, "Отображение таблиц в LibreOffice и на другом компьютере", "[Ч] Оформление таблиц",
     "Откройте файл в другой программе или на другом компьютере; см. также TBL-09.", "rule:TBL-09"),
    (11, "Содержательные критерии: актуальность, новизна, значимость, глубина обзора", "[М]",
     "Оценивает руководитель или рецензент; код эти критерии не проверяет.", None),
    # переносы строк зависят от вёрстки Word: LibreOffice переносит иначе (решение 2026-10-20)
    (12, "Записи величин не разрываются переносом строки («n =» / «37»)", "[Ч] Оформление таблиц",
     "Просмотрите текст в Word; в «n = 17», «p < 0,001», «60 %» ставьте неразрывный пробел "
     "(Ctrl+Shift+Пробел).", None),
)  # fmt: skip


def nc_items(layout_failed: bool) -> list[NcItem]:
    """Список пунктов NC-01; идентификаторы постоянны независимо от состава списка."""
    result = []
    for number, title, source, hint, helper in _ITEMS:
        item_id = f"NC-01.{number}"
        if item_id in LAYOUT_ONLY and not layout_failed:
            continue
        result.append(NcItem(id=item_id, title=title, source=source, hint=hint, helper=helper))
    return result


@register
class NotCheckedRule:
    id = "NC-01"
    title = "Не проверяется кодом"
    block = "not_checked"
    source = Source("CH", "Что не проверяется кодом")
    default_level = "not_checked"
    needs: frozenset[Need] = frozenset()
    priority = "must"

    def run(self, ctx: CheckContext) -> RuleResult:
        items = nc_items(layout_failed=ctx.doc.layout is None)
        findings = [
            new_finding(
                self,
                item.title,
                fingerprint=item.id,
                level="not_checked",
                hint=item.hint,
                values={"item_id": item.id, "helper": item.helper or ""},
            )
            for item in items
        ]
        return result_of(self, findings)
