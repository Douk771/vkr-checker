"""DIF-05: анализ последствий правок (по одному сценарию на тест)."""

from __future__ import annotations

from tests.fixtures.model_factory import DocBuilder
from tests.unit.test_diff_core import side
from vkr_checker.diff.compare import build_diff

CONCL = "Исследование проведено на выборке из 50 человек, что достаточно для анализа."


def rule_ids(diff) -> list[str]:
    return [f.rule_id for f in diff.impact]


def sample_doc(n: int):
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para(f"Выборка составила {n} человек в возрасте от 18 до 25 лет.")
    b.heading("Заключение", kind="CONCLUSION")
    b.para(CONCL)
    return b.build()


def test_stale_number_is_reported_with_both_places():
    diff = build_diff(side(sample_doc(50)), side(sample_doc(60)))
    assert rule_ids(diff) == ["DIF-05.1"]
    f = diff.impact[0]
    assert f.block == "diff_impact" and f.level == "suspicion" and f.not_run is False
    assert f.locations[0].paragraph_idx == 2  # место правки
    assert f.locations[1].paragraph_idx == 4  # осталось старое значение
    assert len(f.id) == 12


def test_number_updated_everywhere_gives_no_finding():
    def doc(n):
        b = DocBuilder()
        b.heading("Введение", kind="INTRO")
        b.para(f"Выборка составила {n} человек в возрасте от 18 до 25 лет.")
        b.heading("Заключение", kind="CONCLUSION")
        b.para(f"Исследование проведено на выборке из {n} человек, что достаточно для анализа.")
        return b.build()

    assert build_diff(side(doc(50)), side(doc(60))).impact == []


def tables_doc(with_second: bool, phrase: str, ref: str):
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para(phrase)
    b.heading("Результаты", kind="CHAPTER", number="2")
    b.para(ref)
    b.table([["a", "b"], ["1", "2"]], caption="Таблица 1 - Первая")
    if with_second:
        b.table([["c", "d"], ["3", "4"]], caption="Таблица 2 - Вторая")
    return b.build()


def test_reference_to_removed_table_is_reported():
    ref = "Подробные данные приведены в таблице 2 и обсуждаются далее."
    old = tables_doc(True, "Работа выполнена.", ref)
    new = tables_doc(False, "Работа выполнена.", ref)
    diff = build_diff(side(old), side(new))
    assert "DIF-05.4" in rule_ids(diff)
    f = next(f for f in diff.impact if f.rule_id == "DIF-05.4")
    assert f.locations[0].paragraph_idx == 4


def test_phrase_about_counts_not_updated():
    ref = "Подробные данные приведены в таблице 1 и обсуждаются далее."
    phrase = "Работа содержит 1 таблицу и занимает несколько страниц."
    diff = build_diff(side(tables_doc(False, phrase, ref)), side(tables_doc(True, phrase, ref)))
    assert "DIF-05.5" in rule_ids(diff)


def test_phrase_updated_gives_no_totals_finding():
    ref = "Подробные данные приведены в таблице 1 и обсуждаются далее."
    diff = build_diff(
        side(tables_doc(False, "Работа содержит 1 таблицу.", ref)),
        side(tables_doc(True, "Работа содержит 2 таблицы.", ref)),
    )
    assert "DIF-05.5" not in rule_ids(diff)


def methods_doc(intro_method: bool):
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para(
        "Методы исследования: критерий Манна-Уитни." if intro_method else "Методы: анкетирование."
    )
    b.heading("Результаты", kind="CHAPTER", number="2")
    b.para("Различия проверены с помощью критерия Манна-Уитни и оказались значимыми.")
    return b.build()


def test_removed_method_still_mentioned():
    diff = build_diff(side(methods_doc(True)), side(methods_doc(False)))
    assert "DIF-05.3" in rule_ids(diff)


def chapter2_doc(cell: str):
    b = DocBuilder()
    b.heading("Теория", kind="CHAPTER", number="1")
    b.para("Теоретический обзор подходов к проблеме тревожности у студентов.")
    b.heading("Результаты", kind="CHAPTER", number="2")
    b.para("Результаты сравнения групп приведены в таблице.")
    b.table([["Шкала", "M"], ["Тревога", cell]], caption="Таблица 1 - Средние")
    b.heading("Заключение", kind="CONCLUSION")
    b.para("Выявлены различия между группами по уровню тревожности студентов.")
    return b.build()


def test_changed_chapter2_cells_with_untouched_conclusions():
    diff = build_diff(side(chapter2_doc("3,4")), side(chapter2_doc("3,9")))
    assert "DIF-05.6" in rule_ids(diff)


def hypothesis_doc(intro: str):
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para(f"Гипотеза исследования: {intro}")
    b.heading("Заключение", kind="CONCLUSION")
    b.para("Гипотеза о связи тревожности и копинг-стратегий у студентов подтвердилась полностью.")
    return b.build()


def test_changed_hypothesis_with_stale_conclusion():
    old = hypothesis_doc("тревожность студентов связана с выбором копинг-стратегий.")
    new = hypothesis_doc("уровень самооценки определяет академическую успеваемость школьников.")
    assert "DIF-05.2" in rule_ids(build_diff(side(old), side(new)))


def test_unchanged_hypothesis_gives_no_anchor_finding():
    doc = hypothesis_doc("тревожность студентов связана с выбором копинг-стратегий.")
    assert build_diff(side(doc), side(doc)).impact == []
