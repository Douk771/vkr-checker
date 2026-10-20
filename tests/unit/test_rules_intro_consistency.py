from tests.unit.test_structure import H, doc_of
from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.consistency import (
    Con01SameQuantities,
    Con02MeanInRange,
    Con03PercentSums,
    Con04GroupingMethods,
)
from vkr_checker.checks.engine import run_rule
from vkr_checker.checks.intro import Int01IntroElements
from vkr_checker.model.document import Cell, Row, Table
from vkr_checker.structure import analyze_structure

FULL_INTRO = [
    H("ВВЕДЕНИЕ"),
    "Актуальность темы определяется ростом интереса.",
    "Степень разработанности проблемы невысока.",
    "Цель работы: выявить связь мотивации и адаптации.",
    "Объект исследования: студенты.",
    "Предмет исследования: связь мотивации и адаптации.",
    "Задачи исследования:",
    "1. Изучить литературу.",
    "2. Подобрать методики.",
    "Гипотеза: мотивация связана с адаптацией.",
    "Теоретико-методологические основания: подход автора А.",
    "Методы исследования: тестирование, корреляционный анализ.",
    "Выборка: 124 студента.",
    "Научная новизна заключается в новом сочетании методик.",
    "Теоретическая значимость состоит в уточнении понятий.",
    "Практическая значимость состоит в рекомендациях.",
    "Положения, выносимые на защиту: связь существует.",
    "Апробация результатов проведена на конференции.",
]


def run(rule, items, **kw):
    return run_rule(CheckContext.build(analyze_structure(doc_of(items, **kw))), rule)


def test_int01_complete_intro_has_no_findings_and_artifact():
    res = run(Int01IntroElements(), FULL_INTRO)
    assert not res.findings
    assert {e["key"] for e in res.artifacts["elements"]} >= {"goal", "tasks", "hypothesis"}


def test_int01_missing_and_inline_elements():
    items = [x for x in FULL_INTRO if isinstance(x, tuple) or not x.startswith("Научная новизна")]
    items[1] = "Важно отметить, что актуальность темы определяется ростом интереса."
    res = run(Int01IntroElements(), items)
    by = {f.fingerprint: f for f in res.findings}
    assert by["INT-01|missing|novelty"].level == "violation"
    assert by["INT-01|inline|actuality"].level == "suspicion"


def test_int01_implementation_without_act():
    res = run(Int01IntroElements(), [*FULL_INTRO, "Внедрение результатов осуществлено в школе."])
    assert any(f.fingerprint == "INT-01|implementation" for f in res.findings)
    res = run(
        Int01IntroElements(),
        [*FULL_INTRO, "Внедрение результатов осуществлено в школе.", H("ПРИЛОЖЕНИЕ А"),
         "Акт внедрения"],
    )  # fmt: skip
    assert not any(f.fingerprint == "INT-01|implementation" for f in res.findings)


def test_con01_same_quantity_with_different_values_and_qualifier_ignored():
    items = [
        H("ВВЕДЕНИЕ"), "Выборка составила n = 124 человека.",
        H("ГЛАВА 1. Т"), "В исследовании приняли участие 120 респондентов.",
        "Экспериментальная группа: n = 60 человек.",
    ]  # fmt: skip
    res = run(Con01SameQuantities(), items)
    assert len(res.findings) == 1
    assert res.findings[0].values["values"] == ["120", "124"]
    assert len(res.findings[0].locations) == 2
    assert res.artifacts["numbers_index"]


def test_con01_participated_n_people_vs_n_equals():
    """«приняли участие 112 человек» (без слов «респондент/выборка») сравнивается с n = 120."""
    items = [
        H("ВВЕДЕНИЕ"), "Выборка исследования: n = 120 студентов магистратуры.",
        H("ГЛАВА 2. Э"), "В исследовании приняли участие 112 человек в возрасте от 18 до 25 лет.",
    ]  # fmt: skip
    res = run(Con01SameQuantities(), items)
    assert [f.values["values"] for f in res.findings] == [["112", "120"]]


def test_con01_same_values_no_finding():
    items = [H("ВВЕДЕНИЕ"), "Выборка n = 124.", H("ГЛАВА 1. Т"), "Приняли участие 124 респондента."]
    assert not run(Con01SameQuantities(), items).findings


def test_con02_mean_outside_range_is_violation():
    items = [H("ГЛАВА 2. Э"), "Диапазон баллов от 10 до 20, M = 25,5, SD = 2."]
    res = run(Con02MeanInRange(), items)
    assert [f.level for f in res.findings] == ["violation"]


def test_con02_sd_incompatible_with_range_is_suspicion():
    items = [H("ГЛАВА 2. Э"), "Диапазон баллов от 10 до 14, M = 12, SD = 5."]
    res = run(Con02MeanInRange(), items)
    assert [f.level for f in res.findings] == ["suspicion"]


def test_con02_consistent_values_pass():
    items = [H("ГЛАВА 2. Э"), "Диапазон баллов от 10 до 50, M = 30, SD = 8."]
    assert not run(Con02MeanInRange(), items).findings


def table(rows):
    return Table(
        idx=1,
        rows=tuple(
            Row(cells=tuple(Cell(row=r, col=c, text=t) for c, t in enumerate(row, 1)))
            for r, row in enumerate(rows, 1)
        ),
    )


def test_con02_and_con03_in_tables():
    doc = analyze_structure(doc_of([H("ГЛАВА 2. Э"), "Текст."]))
    from dataclasses import replace

    t1 = table([["Шкала", "M", "SD", "Min", "Max"], ["А", "40", "3", "10", "20"]])
    t2 = table([["Уровень", "%"], ["Низкий", "20"], ["Средний", "50"], ["Высокий", "20"]])
    doc = replace(doc, tables=(t1, replace(t2, idx=2)))
    ctx = CheckContext.build(doc)
    assert run_rule(ctx, Con02MeanInRange()).findings[0].level == "violation"
    f3 = run_rule(ctx, Con03PercentSums()).findings
    assert len(f3) == 1 and "90" in f3[0].message


def test_con03_sentence_sum_rounding_hint_and_clause():
    items = [H("ГЛАВА 2. Э"), "Уровни распределились так: 33%, 33% и 33%."]
    res = run(Con03PercentSums(), items)
    assert len(res.findings) == 1 and "округление" in res.findings[0].message
    items = [H("ГЛАВА 2. Э"), "Уровни: 33%, 33% и 33%. Значения округлены."]
    assert not run(Con03PercentSums(), items).findings
    items = [H("ГЛАВА 2. Э"), "Уровни распределились: 40%, 35% и 25%."]
    assert not run(Con03PercentSums(), items).findings


def test_con04_different_division_methods():
    items = [
        H("ГЛАВА 2. Э"),
        "Участников разделили на группы по терцилям уровня мотивации.",
        "Группы тревожности выделены по нормам методики.",
    ]
    res = run(Con04GroupingMethods(), items)
    assert len(res.findings) == 1 and res.findings[0].values["methods"] == ["norms", "tercile"]
    assert not run(Con04GroupingMethods(), items[:2]).findings
