from tests.unit.test_structure import H, doc_of
from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.engine import run_rule
from vkr_checker.checks.lexical import (
    Lex01CausalWording,
    Lex02EstablishedFindings,
    Lex03Speculation,
)
from vkr_checker.checks.tasks import Tsk01TasksVsConclusions
from vkr_checker.structure import analyze_structure


def run(rule, items):
    return run_rule(CheckContext.build(analyze_structure(doc_of(items))), rule)


def ch2(*paras):
    return [H("ГЛАВА 1. Т"), "Теория.", H("ГЛАВА 2. Э"), *paras]


def test_lex01_causal_verb_with_correlation_marker():
    res = run(Lex01CausalWording(), ch2("Мотивация влияет на адаптацию (r = 0,45)."))
    assert len(res.findings) == 1 and res.findings[0].level == "suspicion"


def test_lex01_causal_verb_without_link_marker_and_link_without_verb_pass():
    assert not run(Lex01CausalWording(), ch2("Погода влияет на настроение людей.")).findings
    assert not run(Lex01CausalWording(), ch2("Выявлена корреляция мотивации и адаптации.")).findings


def test_lex01_privodit_requires_preposition_k():
    items = ch2("Регрессионный анализ приводит данные к единой шкале.")
    assert run(Lex01CausalWording(), items).findings  # «приводит ... к» присутствует
    items = ch2("Регрессионная модель приводит нас сюда.")
    assert not run(Lex01CausalWording(), items).findings


def test_lex01_chapter_one_is_out_of_scope():
    items = [
        H("ГЛАВА 1. Т"),
        "По данным автора, мотивация влияет на адаптацию (корреляция).",
        H("ГЛАВА 2. Э"),
        "э",
    ]
    assert not run(Lex01CausalWording(), items).findings


def test_lex02_established_with_attribution_and_chapter_one_conclusions():
    items = [
        H("ГЛАВА 1. Т"), "Теория.", H("Выводы по главе 1", 2), "Установлено, что мотивация важна.",
        H("ЗАКЛЮЧЕНИЕ"), "По данным Иванова А.А. установлено, что мотивация важна.",
        "В нашей выборке выявлена связь.",
    ]  # fmt: skip
    res = run(Lex02EstablishedFindings(), items)
    assert sorted(f.fingerprint for f in res.findings) == ["LEX-02|4", "LEX-02|6"]


def test_lex03_guess_outside_limitations():
    items = ch2(
        "Вероятно, различия связаны с возрастом.",
        "Ограничения исследования.",
        "Возможно, выборка мала.",
    )
    res = run(Lex03Speculation(), items)
    assert [f.fingerprint for f in res.findings] == ["LEX-03|4"]


TASKS = [
    H("ВВЕДЕНИЕ"), "Задачи исследования:",
    "1. Изучить теоретические подходы к учебной мотивации студентов.",
    "2. Подобрать методики диагностики социальной адаптации.",
    "3. Выявить связь мотивации и адаптации.",
]  # fmt: skip


def test_tsk01_matching_conclusions_have_no_findings_and_map():
    items = [
        *TASKS, H("ЗАКЛЮЧЕНИЕ"),
        "1. Рассмотрены теоретические подходы к учебной мотивации студентов.",
        "2. Подобраны методики диагностики социальной адаптации студентов.",
        "3. Выявлена связь мотивации и адаптации студентов.",
    ]  # fmt: skip
    res = run(Tsk01TasksVsConclusions(), items)
    assert not res.findings
    assert [m["conclusion_index"] for m in res.artifacts["task_map"]] == [1, 2, 3]


def test_tsk01_unmatched_task_and_extra_conclusion():
    items = [
        *TASKS, H("ЗАКЛЮЧЕНИЕ"),
        "1. Рассмотрены теоретические подходы к учебной мотивации студентов.",
        "2. Подобраны методики диагностики социальной адаптации студентов.",
        "3. Разработаны рекомендации по организации спортивных соревнований школьников.",
    ]  # fmt: skip
    res = run(Tsk01TasksVsConclusions(), items)
    fps = sorted(f.fingerprint for f in res.findings)
    assert fps == ["TSK-01|conclusion|3", "TSK-01|task|3"]
    assert res.artifacts["task_map"][2]["conclusion_index"] is None


def test_tsk01_count_difference():
    items = [
        *TASKS,
        H("ЗАКЛЮЧЕНИЕ"),
        "1. Рассмотрены теоретические подходы к учебной мотивации студентов.",
    ]
    res = run(Tsk01TasksVsConclusions(), items)
    assert "TSK-01|count" not in [
        f.fingerprint for f in res.findings
    ]  # разница 2: не больше порога
    more = [*TASKS, "4. Оценить динамику показателей.", "5. Разработать рекомендации."]
    items = [*more, H("ЗАКЛЮЧЕНИЕ"), "Рассмотрены теоретические подходы к учебной мотивации."]
    fps = [f.fingerprint for f in run(Tsk01TasksVsConclusions(), items).findings]
    assert "TSK-01|count" in fps
