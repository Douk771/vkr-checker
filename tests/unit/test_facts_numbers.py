"""Факты: величины, методы, авторы, ссылки (B-32), на DocBuilder без .docx."""

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.checks.facts import Facts


def intro_doc(*paras: str):
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    for t in paras:
        b.para(t)
    return b.build()


def facts_for(*paras: str) -> Facts:
    return Facts(intro_doc(*paras))


def by_kind(facts: Facts, kind: str):
    return [q for q in facts.quantities if q.kind == kind]


# --- величины ----------------------------------------------------------------------------
def test_sample_n_from_n_equals_and_people_phrase_not_duplicated():
    f = facts_for("Выборку составили n = 124 респондента.")
    qs = by_kind(f, "sample_n")
    assert [q.value for q in qs] == ["124"] and qs[0].qualifier == ""


def test_people_word_needs_anchor():
    assert by_kind(facts_for("Мы опросили 124 человека."), "sample_n") == []
    anchored = facts_for("Выборка исследования. В неё вошли 124 человека.")
    assert [q.value for q in by_kind(anchored, "sample_n")] == ["124"]


def test_group_marker_gives_qualifier_and_group_n():
    f = facts_for("В экспериментальной группе (n = 30) выборка снижена.")
    (q,) = by_kind(f, "sample_n")
    assert "групп" in q.qualifier and "экспериментальн" in q.qualifier
    (g,) = [q for q in f.quantities if q.kind.startswith("group_n:")]
    assert g.kind == "group_n:экспериментальный" and g.value == "30"


def test_table_cells_have_table_qualifier():
    b = DocBuilder()
    b.heading("Результаты", kind="CHAPTER", number="2")
    b.table([["Группа", "n"], ["A", "n = 12"]])
    (q,) = by_kind(Facts(b.build()), "sample_n")
    assert q.qualifier == "table" and q.loc.cell is not None


def test_age_range_mean_sd_and_percent():
    f = facts_for(
        "Возраст от 18 до 35 лет. Средний возраст составил 24,5 года, SD = 3,2.",
        "Женщины составили 62% женщин.",
    )
    assert by_kind(f, "age_min_max")[0].value == "18-35"
    assert by_kind(f, "age_mean")[0].value == "24.5"
    assert by_kind(f, "age_sd")[0].value == "3.2"
    assert by_kind(f, "percent_of:женщина")[0].value == "62"


def test_headings_bibliography_and_toc_are_skipped():
    b = DocBuilder()
    b.heading("Выборка n = 5", kind="INTRO")
    b.heading("Список литературы", kind="BIBLIOGRAPHY")
    b.para("Иванов И.И. Тест. 124 респондента.")
    assert Facts(b.build()).quantities == []


def test_quantity_location_points_into_text():
    f = facts_for("Первое. Выборка n = 124 респондента.")
    q = by_kind(f, "sample_n")[0]
    text = f.doc.paragraph(q.loc.paragraph_idx).text
    assert text[q.loc.span[0] : q.loc.span[1]].startswith("n = 124")


# --- методы ------------------------------------------------------------------------------
def test_methods_by_name_and_by_statistic():
    f = facts_for(
        "Применялись критерий Манна-Уитни и коэффициент Спирмена.",
        "Получено rs = 0,45 и U = 120, p < 0,05. Также H = 4,2.",
    )
    pairs = {(m.method_id, m.kind) for m in f.methods}
    assert {("mann_whitney", "name"), ("spearman", "name"), ("spearman", "stat")} <= pairs
    assert ("mann_whitney", "stat") in pairs and ("kruskal_wallis", "stat") in pairs


def test_pearson_r_not_confused_with_spearman_rs():
    f = facts_for("Связь: rs = 0,45.")
    assert {m.method_id for m in f.methods if m.kind == "stat"} == {"spearman"}
    g = facts_for("Связь: r = 0,45.")
    assert {m.method_id for m in g.methods if m.kind == "stat"} == {"pearson"}


def test_method_name_variants_and_table_mentions():
    b = DocBuilder()
    b.heading("Методы", kind="CHAPTER", number="2")
    b.para("Использован дисперсионный анализ, критерий Краскела — Уоллиса и χ².")
    b.table([["Показатель", "F"], ["x", "F(2, 40) = 3,1"]])
    ms = Facts(b.build()).methods
    ids = {m.method_id for m in ms}
    assert {"anova", "kruskal_wallis", "chi_square"} <= ids
    assert any(m.in_table and m.method_id == "anova" for m in ms)


# --- авторы ------------------------------------------------------------------------------
def test_author_patterns_and_case_normalization():
    f = facts_for(
        "Подход Л.С. Выготского развит. Как писал Леонтьев А.Н., это важно. Иванов (2015) показал.",
    )
    names = {a.surname: a.pattern for a in f.authors}
    assert names["Выготский"] == "initials_first"
    assert names["Леонтьев"] == "surname_first"
    assert names["Иванов"] == "surname_year"


def test_author_keys_match_across_cases():
    f = facts_for("Работы Л.С. Выготского. Теория Л.С. Выготский.")
    assert len({a.key for a in f.authors}) == 1


def test_common_words_not_authors():
    f = facts_for("Исследование (2020) показало. Выготский Л.С. Мышление и речь.")
    assert [a.surname for a in f.authors] == ["Выготский"]


def test_latin_author_with_year():
    f = facts_for("Это показал Smith (2005).")
    assert f.authors[0].surname == "Smith"


# --- ссылки ------------------------------------------------------------------------------
def test_table_figure_appendix_refs_with_cases():
    f = facts_for(
        "Как видно из таблицы 2 и на рис. 3, см. приложение Б. (см. табл. 4)",
    )
    got = {(r.kind, r.target) for r in f.refs}
    assert {("table", "2"), ("figure", "3"), ("appendix", "Б"), ("table", "4")} <= got
    assert next(r for r in f.refs if r.target == "4").see


def test_range_and_list_refs_expand():
    f = facts_for("Данные в табл. 2–4 и рисунках 1, 2 и 5.")
    assert [r.target for r in f.refs if r.kind == "table"] == ["2", "3", "4"]
    assert [r.target for r in f.refs if r.kind == "figure"] == ["1", "2", "5"]
    assert [r.in_range for r in f.refs if r.kind == "table"] == [False, True, True]


def test_source_refs_with_pages_and_ranges():
    f = facts_for("См. [3], [4, с. 15] и [7–9].")
    assert [r.target for r in f.refs if r.kind == "source"] == ["3", "4", "7", "8", "9"]


def test_word_приложение_without_letter_is_not_ref():
    f = facts_for("Приложение показало результаты.")
    assert not [r for r in f.refs if r.kind == "appendix"]


def test_caption_paragraph_is_not_a_reference():
    b = DocBuilder()
    b.heading("Результаты", kind="CHAPTER", number="2")
    b.para("Таблица 1 - Данные")
    b.table([["a"]], caption="Таблица 1 - Данные")
    d = b.build()
    from dataclasses import replace

    cap = replace(d.captions[0], paragraph_idx=2)
    d = replace(d, captions=(cap,))
    assert Facts(d).refs == []
