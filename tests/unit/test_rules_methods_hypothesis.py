from tests.unit.test_structure import H, doc_of
from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.engine import run_rule
from vkr_checker.checks.hypothesis import Hyp01HypothesisConsistency
from vkr_checker.checks.methods import (
    Met01MethodsConsistency,
    Met02InstrumentsInTheory,
    Met03TheoryBasis,
    Met04DiscussionAuthors,
)
from vkr_checker.structure import analyze_structure


def run(rule, items):
    return run_rule(CheckContext.build(analyze_structure(doc_of(items))), rule)


def frame(intro, ch1=("Теория.",), sub21=("Организация.",), results=("Результаты.",)):
    return [
        H("ВВЕДЕНИЕ"), *intro,
        H("ГЛАВА 1. Теоретические основы"), *ch1,
        H("ГЛАВА 2. Эмпирическое исследование"), H("2.1. Методы", 2), *sub21,
        H("2.2. Результаты", 2), *results,
        H("ЗАКЛЮЧЕНИЕ"), "Итоги.",
    ]  # fmt: skip


def test_met01_all_consistent():
    items = frame(
        ["Методы: корреляционный анализ Спирмена."],
        sub21=["Применялся коэффициент корреляции Спирмена."],
        results=["Связь значима (rs = 0,45)."],
    )
    assert not run(Met01MethodsConsistency(), items).findings


def test_met01_mismatch_is_violation_unused_and_undeclared_are_suspicions():
    items = frame(
        ["Методы: критерий Манна-Уитни."],
        sub21=["Использовался критерий Стьюдента."],
        results=["Корреляция по Пирсону значима (r = 0,5)."],
    )
    res = run(Met01MethodsConsistency(), items)
    levels = {f.fingerprint: f.level for f in res.findings}
    assert levels["MET-01|mismatch|mann_whitney"] == "violation"
    assert levels["MET-01|mismatch|student_t"] == "violation"
    assert levels["MET-01|undeclared|pearson"] == "suspicion"
    assert levels["MET-01|unused|student_t"] == "suspicion"


def test_met01_not_run_without_section_2_1():
    items = [H("ВВЕДЕНИЕ"), "Текст.", H("ГЛАВА 1. Т"), "т", H("ГЛАВА 2. Э"), "э"]
    assert run(Met01MethodsConsistency(), items).outcome == "not_run"


def test_met02_instrument_must_appear_in_chapter_one():
    sub = ["Использовалась методика «Шкала академической мотивации» (ШАМ) Иванова А.А."]
    items = frame(["Цель."], ch1=["Мотивация изучалась разными авторами."], sub21=sub)
    res = run(Met02InstrumentsInTheory(), items)
    assert len(res.findings) == 1 and "Шкала академической мотивации" in res.findings[0].message
    ch1 = ["В главе описана шкала академической мотивации и её структура."]
    assert not run(Met02InstrumentsInTheory(), frame(["Цель."], ch1=ch1, sub21=sub)).findings


def test_met03_authors_of_intro_must_be_in_chapter_one():
    intro = ["Теоретико-методологические основания: работы Иванова А.А. и Петрова Б.Б."]
    ch1 = ["Подход Иванова А.А. подробно рассмотрен."]
    res = run(Met03TheoryBasis(), frame(intro, ch1=ch1))
    assert [f.values["author"] for f in res.findings] == ["Петров"]


def test_met04_discussion_authors_missing_in_chapter_one():
    items = frame(
        ["Цель."],
        ch1=["Подход Иванова А.А. рассмотрен."],
        results=["Это согласуется с данными Сидорова В.В. и Иванова А.А."],
    )
    res = run(Met04DiscussionAuthors(), items)
    assert [f.values["author"] for f in res.findings] == ["Сидоров"]


HYP = "Гипотеза: высокая учебная мотивация связана с успешной социальной адаптацией студентов."


def test_hyp01_same_wording_passes_and_status_mentions_are_ignored():
    items = frame(
        [HYP],
        results=[
            "Высокая учебная мотивация связана с успешной социальной адаптацией студентов.",
            "Гипотеза подтвердилась.",
        ],
    )
    items[-1] = "Гипотеза подтвердилась."
    assert not run(Hyp01HypothesisConsistency(), items).findings


def test_hyp01_diverging_wording_gets_diff_and_status():
    items = frame(
        [HYP],
        results=["Гипотеза о влиянии тревожности педагогов на выгорание не подтвердилась."],
    )
    res = run(Hyp01HypothesisConsistency(), items)
    texts = [f for f in res.findings if f.fingerprint.count("|") == 2]
    assert len(texts) == 1
    assert texts[0].values["status"] == "not_confirmed"
    assert "тревожность" in texts[0].values["only_in_text"]
    assert "мотивация" in texts[0].values["only_in_intro"]


def test_hyp01_conclusion_without_status():
    res = run(Hyp01HypothesisConsistency(), frame([HYP]))
    assert {f.fingerprint for f in res.findings} == {
        "HYP-01|chapter2_missing",
        "HYP-01|conclusion_missing",
    }


def test_hyp01_status_differs_between_chapter2_and_conclusion():
    items = frame([HYP], results=["Гипотеза частично подтвердилась."])
    items[-1] = "Гипотеза подтвердилась."
    res = run(Hyp01HypothesisConsistency(), items)
    assert [f.fingerprint for f in res.findings] == ["HYP-01|status_mismatch"]
    assert res.findings[0].values["status_chapter2"] == "partially_confirmed"


def test_met02_name_words_spread_over_chapter_are_not_a_match():
    sub = ["Использовалась методика «Шкала учебной мотивации» (ШУМ) Иванова А.А."]
    ch1 = ["Учебная мотивация студентов изучалась давно. Шкалы бывают разные."]
    res = run(Met02InstrumentsInTheory(), frame(["Цель."], ch1=ch1, sub21=sub))
    assert len(res.findings) == 1


def test_met02_authors_differ_between_chapters():
    sub = ["Использовалась методика «Шкала учебной мотивации» (ШУМ) Иванова А.А."]
    ch1 = ["Шкала учебной мотивации создана Петровым Б.Б."]
    res = run(Met02InstrumentsInTheory(), frame(["Цель."], ch1=ch1, sub21=sub))
    assert [f.fingerprint for f in res.findings] == ["MET-02|authors|шкала учебной мотивации"]
    ch1_same = ["Шкала учебной мотивации создана Ивановым А.А."]
    assert not run(Met02InstrumentsInTheory(), frame(["Цель."], ch1=ch1_same, sub21=sub)).findings
