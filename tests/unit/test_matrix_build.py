"""MAT-01: матрица связности на модели документа."""

from __future__ import annotations

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.checks.base import CheckContext
from vkr_checker.matrix.build import build_matrix, is_theoretical


def full_doc():
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para("Гипотеза исследования: тревожность студентов связана с копинг-стратегиями.")
    b.para("Задачи исследования:")
    b.para("1) проанализировать литературу по проблеме тревожности студентов;")
    b.para("2) выявить связь тревожности студентов с копинг-стратегиями.")
    b.heading("Тревожность студентов", kind="CHAPTER", number="1")
    b.heading("Подходы к тревожности", kind="SUBSECTION", number="1.1", level=2, parent="s2")
    b.para("Тревожность студентов изучали Иванов (2015) и Петров (2018) как личностную черту.")
    b.heading("Копинг-стратегии", kind="SUBSECTION", number="1.2", level=2, parent="s2")
    b.para("Копинг-стратегии описаны в работах Сидоров (2010) как способы совладания со стрессом.")
    b.heading("Эмпирическое исследование", kind="CHAPTER", number="2")
    b.heading("Методики", kind="SUBSECTION", number="2.1", level=2, parent="s5")
    b.para("Использовался опросник «Шкала тревожности студентов» (ШТС) по методике Иванова.")
    b.para(
        "Связь тревожности студентов с копинг-стратегиями проверена по Спирмену, rs = 0,45."
    )
    b.table([["Показатель", "rs"], ["Тревожность и копинг-стратегии", "0,45"]],
            caption="Таблица 1 - Связь тревожности студентов с копинг-стратегиями")  # fmt: skip
    b.heading("Заключение", kind="CONCLUSION")
    b.para("1. Проведён анализ литературы по проблеме тревожности студентов в научных работах.")
    b.para("2. Выявлена связь тревожности студентов с копинг-стратегиями. Гипотеза подтвердилась.")
    return b.build()


def matrix_of(doc):
    return build_matrix(CheckContext.build(doc))


def test_rows_come_from_hypothesis_and_tasks():
    m = matrix_of(full_doc())
    assert [r.kind for r in m.rows] == ["hypothesis_part", "task", "task"]
    assert [r.label for r in m.rows] == ["Гипотеза, ч.1", "Задача 1", "Задача 2"]
    assert m.stats.rows == 3


def test_theoretical_task_has_na_for_instrument_and_calculation():
    task1 = matrix_of(full_doc()).rows[1]
    assert task1.is_theoretical
    assert task1.cells.instrument.status == "n/a"
    assert task1.cells.calculation.status == "n/a"
    assert task1.cells.theory.status == "auto"


def test_empirical_task_is_filled_from_facts():
    task2 = matrix_of(full_doc()).rows[2]
    assert not task2.is_theoretical
    assert task2.cells.calculation.status == "auto"
    assert "Таблица 1" in task2.cells.calculation.text
    assert "rs" in task2.cells.result.text or task2.cells.result.status == "gap"
    assert task2.cells.conclusion.status == "auto" and "вывод 2" in task2.cells.conclusion.text


def test_hypothesis_conclusion_carries_status():
    row = matrix_of(full_doc()).rows[0]
    assert row.cells.conclusion.status == "auto"
    assert "подтверждена" in row.cells.conclusion.text


def test_missing_sources_give_warnings_not_rows():
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para("Актуальность темы очевидна.")
    m = matrix_of(b.build())
    assert m.rows == []
    assert any("Гипотеза" in w for w in m.stats.warnings)
    assert any("Задачи" in w for w in m.stats.warnings)


def test_gaps_are_counted():
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para("Задачи исследования:")
    b.para("1) определить уровень креативности дошкольников.")
    m = matrix_of(b.build())
    assert m.stats.rows == 1 and m.stats.gaps >= 3 and m.stats.auto_cells == 0


def test_is_theoretical_markers():
    assert is_theoretical("Проанализировать научную литературу по проблеме")
    assert is_theoretical("Теоретически обосновать подход")
    assert not is_theoretical("Выявить связь тревожности и копинга")
