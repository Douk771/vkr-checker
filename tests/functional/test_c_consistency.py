# ruff: noqa: E501
"""SPEC 4.B: CON-01..04, MET-01..04, HYP-01, LEX-01..03, TSK-01, NC-01."""

import pytest

from tests.functional.conftest import of_rule
from tests.functional.thesis import NB, p


def susp(rep, rule):
    return [f for f in of_rule(rep, rule) if f["level"] == "suspicion" and not f["not_run"]]


def viol(rep, rule):
    return [f for f in of_rule(rep, rule) if f["level"] == "violation"]


# ---- CON-01 ---------------------------------------------------------------------------
def test_con01_sample_size_mismatch_two_places(api, clean):
    """Критерий приёмки: введение n = 120, §2.2 «выборку составили 124 человека» -> подозрение с 2 местами."""
    t = clean.insert_after(
        "Описательные статистики приведены", p("Выборку составили 124 человека.")
    )
    fs = susp(api.report(t), "CON-01")
    assert fs
    msg = " ".join(f["message"] for f in fs)
    assert "124" in msg and "120" in msg
    assert max(len(f["locations"]) for f in fs) >= 2


def test_con01_intro_sample_vs_conclusion_when_intro_has_gender_split(api, clean):
    t = clean.sub("на выборке из 120 студентов", "на выборке из 118 человек")
    fs = susp(api.report(t), "CON-01")
    assert fs and "118" in " ".join(f["message"] for f in fs)


def test_con01_conclusion_vs_chapter2_mismatch(api, clean):
    t = clean.insert_after(
        "В заключении подведены итоги", p("Результаты получены на выборке из 118 человек.", False)
    )
    fs = susp(api.report(t), "CON-01")
    assert fs and "118" in " ".join(f["message"] for f in fs)


@pytest.mark.parametrize(
    "form", [f"N{NB}={NB}120", "120 респондентов", "120 испытуемых", "120 человек"]
)
def test_con01_forms_of_same_value_are_not_mismatch(api, clean, form):
    t = clean.insert_after(
        "В заключении подведены итоги", p(f"Опрошено: {form}, выборка репрезентативна.", False)
    )
    assert not susp(api.report(t), "CON-01")


def test_con01_age_range_mismatch(api, clean):
    t = clean.insert_after(
        "В исследовании приняли участие", p(f"Возраст участников составил от 19 до 27{NB}лет.")
    )
    assert susp(api.report(t), "CON-01")


# ---- CON-02 ---------------------------------------------------------------------------
def test_con02_mean_outside_range_is_violation(api, clean):
    t = clean.insert_after(
        "В исследовании приняли участие",
        p(f"Возраст участников: M{NB}={NB}31,4, диапазон 18–25{NB}лет."),
    )
    assert viol(api.report(t), "CON-02")


def test_con02_range_written_as_from_to_with_mean_in_parentheses(api, clean):
    t = clean.sub(f"(M{NB}={NB}20,4;", f"(M{NB}={NB}31,4;")
    assert viol(api.report(t), "CON-02")


def test_con02_mean_inside_range_passes(api, clean):
    assert not of_rule(api.report(clean), "CON-02")


def test_con02_sd_incompatible_with_range_is_suspicion(api, clean):
    t = clean.insert_after(
        "В исследовании приняли участие",
        p(f"Возраст участников: M{NB}={NB}21,0 (SD{NB}={NB}9,5), диапазон 18–25{NB}лет."),
    )
    rep = api.report(t)
    assert susp(rep, "CON-02") and not viol(rep, "CON-02")


# ---- CON-03 ---------------------------------------------------------------------------
def test_con03_percent_sum_off_is_suspicion(api, clean):
    t = clean.sub("60% женщин и 40% мужчин", "60% женщин и 30% мужчин")
    assert susp(api.report(t), "CON-03")


def test_con03_percent_sum_near_100_hints_rounding(api, clean):
    t = clean.sub("60% женщин и 40% мужчин", "34% женщин, 33% мужчин и 32% других")
    fs = susp(api.report(t), "CON-03")
    assert fs and "округл" in fs[0]["message"].lower() + (fs[0]["hint"] or "").lower()


def test_con03_rounding_note_suppresses(api, clean):
    t = clean.sub(
        "60% женщин и 40% мужчин",
        "34% женщин, 33% мужчин и 32% других (сумма не равна 100% из-за округления)",
    )
    assert not susp(api.report(t), "CON-03")


def test_con03_exact_100_passes(api, clean):
    assert not of_rule(api.report(clean), "CON-03")


# ---- CON-04 ---------------------------------------------------------------------------
def test_con04_different_grouping_methods(api, clean):
    t = clean.insert_after(
        "Описательные статистики приведены",
        p("Группы с высокой и низкой мотивацией выделены по терцилям."),
        p("Для тех же групп с высокой и низкой мотивацией использованы квартили."),
    )
    assert susp(api.report(t), "CON-04")


# ---- MET-01 ---------------------------------------------------------------------------
def test_met01_acceptance_spearman_not_declared(api, clean):
    """Критерий приёмки: во введении Краскела–Уоллиса, Манна–Уитни, регрессия; в главе 2 rs = 0,45."""
    t = clean.sub(
        "коэффициент корреляции Спирмена, U-критерий Манна–Уитни",
        "H-критерий Краскела–Уоллиса, U-критерий Манна–Уитни, регрессионный анализ",
        within="ВВЕДЕНИЕ",
    )
    t = t.sub(
        "коэффициент корреляции Спирмена и U-критерий Манна–Уитни",
        "H-критерий Краскела–Уоллиса, U-критерий Манна–Уитни и регрессионный анализ",
    )
    fs = susp(api.report(t), "MET-01")
    assert any("Спирмен" in f["message"] for f in fs), [f["message"] for f in fs]
    assert any(f["locations"] for f in fs)


def test_met01_declared_but_not_applied_is_suspicion(api, clean):
    t = clean.sub("U-критерий Манна–Уитни", "U-критерий Манна–Уитни, t-критерий Стьюдента").sub(
        "и U-критерий Манна–Уитни", "и U-критерий Манна–Уитни, t-критерий Стьюдента"
    )
    fs = susp(api.report(t), "MET-01")
    assert any("Стьюдент" in f["message"] for f in fs)


def test_met01_applied_but_not_declared_via_notation(api, clean):
    t = clean.insert_after(
        "Описательные статистики приведены",
        p(f"Критерий Вилкоксона показал T{NB}={NB}45,0 (p{NB}<{NB}0,05)."),
    )
    fs = susp(api.report(t), "MET-01")
    assert any("Вилкоксон" in f["message"] for f in fs)


def test_met01_lists_in_intro_and_chapter2_diverge_is_violation(api, clean):
    t = clean.sub(
        "U-критерий Манна–Уитни", "U-критерий Манна–Уитни, t-критерий Стьюдента", within="ВВЕДЕНИЕ"
    )
    assert viol(api.report(t), "MET-01")


# ---- MET-02 ---------------------------------------------------------------------------
NEW_INSTR = "Использована методика «Методика самооценки состояния» (МСС) Ч.Д. Спилбергера, адаптация Ю.Л. Ханина."


def test_met02_instrument_absent_from_chapter1_is_suspicion(api, clean):
    t = clean.insert_after("В исследовании приняли участие", p(NEW_INSTR))
    fs = susp(api.report(t), "MET-02")
    assert fs and any("самооценк" in f["message"].lower() for f in fs)


def test_met02_instrument_name_sharing_topic_words_but_not_described(api, clean):
    S1 = "Шкала учебной мотивации разработана Н.Н. Ивановым и описана в литературе как инструмент диагностики."
    S2 = "Понятие адаптации раскрыто в работах П.П. Петрова, адаптировавшего шкалу для студентов."
    t = clean.sub(S1, "Инструмент диагностики описан в литературе.").sub(
        S2, "Понятие адаптации раскрыто в литературе."
    )
    assert susp(api.report(t), "MET-02")


def test_met02_authors_differ_between_chapters_is_suspicion(api, clean):
    t = clean.sub(
        "(ШУМ) Н.Н. Иванова, адаптация П.П. Петрова",
        "(ШУМ) Е.Е. Кузнецова, адаптация Г.Г. Орловой",
        within="2.1.",
    )
    assert susp(api.report(t), "MET-02")


# ---- MET-03 / MET-04 ----------------------------------------------------------------
def test_met03_theory_author_missing_in_chapter1(api, clean):
    t = clean.sub("подхода А.Н. Леонтьева", "подхода Л.С. Выготского")
    fs = susp(api.report(t), "MET-03")
    assert fs and "Выготск" in fs[0]["message"]


def test_met04_author_in_discussion_not_in_chapter1(api, clean):
    t = clean.insert_after(
        "Гипотеза о том, что учебная", p("Результаты согласуются с данными Тихонова (2019).")
    )
    fs = susp(api.report(t), "MET-04")
    assert fs and "Тихонов" in " ".join(f["message"] for f in fs)


# ---- HYP-01 ---------------------------------------------------------------------------
def test_hyp01_status_differs_chapter2_vs_conclusion(api, clean):
    t = clean.sub(
        "положительно связана с уровнем академической адаптации, подтверждена.",
        "положительно связана с уровнем академической адаптации, частично подтверждена.",
    )
    assert susp(api.report(t), "HYP-01")


def test_hyp01_hypothesis_not_mentioned_in_chapter2(api, clean):
    t = clean.drop("Гипотеза о том, что учебная")
    assert susp(api.report(t), "HYP-01")


def test_hyp01_hypothesis_not_mentioned_in_conclusion(api, clean):
    t = clean.sub(
        "Выявлена связь учебной мотивации с академической адаптацией: гипотеза о том, что учебная "
        "мотивация студентов положительно связана с уровнем академической адаптации, подтверждена "
        "на выборке из 120 студентов.",
        "Выявлена связь на выборке из 120 студентов.",
    )
    assert susp(api.report(t), "HYP-01")


def test_hyp01_formulation_changed_in_chapter2_shows_both(api, clean):
    t = clean.sub(
        "Гипотеза о том, что учебная мотивация студентов положительно связана с уровнем академической адаптации, подтверждена.",
        "Гипотеза о том, что самооценка личности определяет стрессоустойчивость сотрудников организации, подтверждена.",
    )
    fs = susp(api.report(t), "HYP-01")
    assert fs
    txt = " ".join(f["message"] + str(f["values"]) for f in fs)
    assert "самооценк" in txt.lower()


# ---- LEX ------------------------------------------------------------------------------
@pytest.mark.parametrize("word", ["влияет", "определяет", "приводит к", "является причиной"])
def test_lex01_causal_wording_near_correlation(api, clean, word):
    t = clean.insert_after(
        "Гипотеза о том, что учебная",
        p(f"Мотивация {word} адаптацию, о чём говорит корреляция (rs{NB}={NB}0,45)."),
    )
    assert susp(api.report(t), "LEX-01")


def test_lex01_clean_wording_passes(api, clean):
    t = clean.insert_after(
        "Гипотеза о том, что учебная", p("Мотивация связана с адаптацией (rs = 0,45).")
    )
    assert not susp(api.report(t), "LEX-01")


def test_lex02_established_with_citation_in_conclusion(api, clean):
    t = clean.sub(
        "2. Для диагностики подобраны",
        "2. Установлено, что мотивация растёт [3]; для диагностики подобраны",
    )
    assert susp(api.report(t), "LEX-02")


def test_lex02_established_in_chapter1_conclusions(api, clean):
    t = clean.sub("Анализ литературы показал,", "Установлено, что")
    assert susp(api.report(t), "LEX-02")


def test_lex03_guess_in_conclusion_outside_limitations(api, clean):
    t = clean.sub("2. Для диагностики подобраны", "2. Возможно, для диагностики подобраны")
    assert susp(api.report(t), "LEX-03")


def test_lex03_guess_in_limitations_is_ok(api, clean):
    t = clean.insert_after(
        "3. Выявлена связь",
        p(
            "Ограничения исследования и перспективы: возможно, результаты не обобщаются на другие выборки.",
            False,
        ),
    )
    assert not susp(api.report(t), "LEX-03")


# ---- TSK-01 ---------------------------------------------------------------------------
def test_tsk01_has_task_to_conclusion_table_with_autonumbered_tasks(api, clean):
    """Задачи оформлены автонумерацией Word (номера нет в тексте) - всё равно должны извлекаться."""
    rep = api.report(clean)
    rr = [r for b in rep["blocks"] for r in b["rule_results"] if r["rule_id"] == "TSK-01"][0]
    art = str(rr["artifacts"])
    assert "Проанализировать" in art and "Выявить" in art


def test_tsk01_task_without_conclusion_is_suspicion(api, clean):
    t = clean.drop("2. Для диагностики подобраны")
    fs = susp(api.report(t), "TSK-01")
    assert fs and any("Подобрать" in f["message"] for f in fs)


def test_tsk01_extra_conclusion_without_task_is_suspicion(api, clean):
    t = clean.insert_after(
        "3. Выявлена связь",
        p("4. Произведена оценка финансовой отчётности предприятий региона.", False),
    )
    assert susp(api.report(t), "TSK-01")


# ---- NC-01 ----------------------------------------------------------------------------
def test_nc01_always_present_even_on_clean_work(clean_report):
    titles = " ".join(i["title"].lower() for i in clean_report["not_checked"])
    for kw in [
        "числа сверены",
        "производные величины",
        "ключ методики",
        "нормы сверены",
        "номера страниц",
        "короткие таблицы",
        "содержательные критерии",
    ]:
        assert kw in titles, kw


def test_nc01_hints_for_helper_items(clean_report):
    helpers = {i["helper"] for i in clean_report["not_checked"] if i.get("helper")}
    assert any(h == "numbers_index" for h in helpers)
