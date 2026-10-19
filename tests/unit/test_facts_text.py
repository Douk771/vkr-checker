"""Факты: элементы введения, задачи, выводы, гипотеза, методики (B-32)."""

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.checks.facts import Facts
from vkr_checker.checks.facts.hypothesis import status_of


def thesis(intro=(), ch1=(), ch2_methods=(), ch2=(), concl=()):
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    for t in intro:
        if isinstance(t, tuple):
            b.para(t[0], num_label=t[1])
        else:
            b.para(t)
    b.heading("Теоретический анализ", kind="CHAPTER", number="1")
    for t in ch1:
        b.para(t)
    b.heading("Эмпирическое исследование", kind="CHAPTER", number="2")
    b.heading("Методы", kind="SUBSECTION", number="2.1", level=2, parent="s3")
    for t in ch2_methods:
        b.para(t)
    b.heading("Результаты", kind="SUBSECTION", number="2.2", level=2, parent="s3")
    for t in ch2:
        b.para(t)
    b.heading("Заключение", kind="CONCLUSION")
    for t in concl:
        if isinstance(t, tuple):
            b.para(t[0], num_label=t[1])
        else:
            b.para(t)
    return Facts(b.build())


# --- введение ---------------------------------------------------------------------------
def test_positions_para_start_sentence_start_inline():
    f = thesis(
        intro=[
            "Актуальность темы определяется ростом интереса.",
            "Новое предложение. Объект исследования - студенты.",
            "Иногда в тексте упоминается апробация результатов.",
        ]
    )
    el = f.intro_elements
    assert el["actuality"][0].position == "para_start"
    assert el["object"][0].position == "sentence_start"
    assert el["approbation"][0].position == "inline"
    assert el["object"][0].text == "студенты."


def test_heading_position_and_content_paragraphs():
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.heading("Цель исследования", kind="SUBSECTION", level=2, parent="s1")
    b.para("Изучить связь.")
    b.heading("Объект", kind="SUBSECTION", level=2, parent="s1")
    b.para("Студенты.")
    el = Facts(b.build()).intro_elements
    assert el["goal"][0].position == "heading"
    assert el["goal"][0].content_paragraphs == (2, 3)
    assert el["object"][0].content_paragraphs == (4, 5)


def test_missing_elements_absent_from_result():
    f = thesis(intro=["Просто текст без структуры."])
    assert f.intro_elements == {}


def test_best_position_wins_over_inline_mention():
    f = thesis(
        intro=["Практическая значимость состоит в рекомендациях.", "Цель, как и задачи, ясна."]
    )
    assert f.intro_elements["practice_value"][0].position == "para_start"
    assert f.intro_elements["tasks"][0].position == "inline"


def test_implementation_element_detected_separately():
    f = thesis(intro=["Внедрение результатов в школе №5."])
    assert "implementation" in f.intro_elements


# --- задачи, выводы -------------------------------------------------------------------------
def test_tasks_from_numbered_paragraphs():
    f = thesis(
        intro=["Задачи исследования:", ("изучить литературу;", "1."), ("выявить связь.", "2.")]
    )
    assert [t.text for t in f.tasks] == ["изучить литературу;", "выявить связь."]
    assert [t.index for t in f.tasks] == [1, 2]


def test_tasks_inline_enumeration():
    f = thesis(intro=["Задачи: 1) изучить литературу; 2) выявить связь; 3) сравнить группы."])
    assert [t.text for t in f.tasks] == ["изучить литературу", "выявить связь", "сравнить группы"]


def test_tasks_inline_semicolons_without_numbers():
    f = thesis(intro=["Задачи: изучить литературу; выявить связь."])
    assert len(f.tasks) == 2


def test_task_list_stops_at_next_element():
    f = thesis(intro=["Задачи:", ("изучить;", "1."), "Гипотеза: связь есть."])
    assert len(f.tasks) == 1
    assert [h.text for h in f.hypotheses] == ["связь есть."]


def test_defense_positions():
    f = thesis(
        intro=[
            "Положения, выносимые на защиту:",
            ("Связь значима.", "1."),
            ("Группы различаются.", "2."),
        ]
    )
    assert [p.text for p in f.defense_positions] == ["Связь значима.", "Группы различаются."]


def test_conclusions_numbered_and_unnumbered():
    f = thesis(
        concl=[
            ("Показана связь A и B в выборке.", "1."),
            ("Выявлены различия между группами.", "2."),
        ]
    )
    assert len(f.conclusions) == 2
    g = thesis(concl=["Короткий.", "Это достаточно длинный абзац заключения, содержащий вывод."])
    assert len(g.conclusions) == 1


def test_chapter_conclusions():
    b = DocBuilder()
    b.heading("Глава", kind="CHAPTER", number="1")
    b.heading("Выводы по главе 1", kind="CHAPTER_CONCLUSIONS", level=2, parent="s1")
    b.para("Теоретический анализ показал значимость связи между переменными.")
    f = Facts(b.build())
    assert [len(v) for v in f.chapter_conclusions.values()] == [1]


# --- гипотеза --------------------------------------------------------------------------
def test_hypothesis_parts_numbered_and_single():
    f = thesis(
        intro=["Гипотеза исследования:", ("Связь положительна.", "1."), ("Различия есть.", "2.")]
    )
    assert [p.text for p in f.hypotheses] == ["Связь положительна.", "Различия есть."]
    g = thesis(intro=["Гипотеза исследования: чем выше A, тем выше B."])
    assert [p.text for p in g.hypotheses] == ["чем выше A, тем выше B."]


def test_hypothesis_mentions_with_statuses_in_scope_only():
    f = thesis(
        intro=["Гипотеза: связь есть."],
        ch1=["Гипотеза обсуждается в литературе."],
        ch2=["Гипотеза частично подтвердилась. Прочее."],
        concl=["Гипотеза не подтверждена."],
    )
    got = [(m.section_kind, m.chapter, m.status) for m in f.hypothesis_mentions]
    assert got == [("CHAPTER", 2, "partially_confirmed"), ("CONCLUSION", None, "not_confirmed")]


def test_status_of_order():
    assert status_of("в основном подтверждена") == "mostly_confirmed"
    assert status_of("не подтвердилась") == "not_confirmed"
    assert status_of("подтвердилась") == "confirmed"
    assert status_of("обсуждается") is None


# --- методики -------------------------------------------------------------------------
def test_instruments_name_abbr_authors_adaptation():
    f = thesis(
        ch2_methods=[
            "Использована методика «Смысложизненные ориентации» (СЖО) Д.А. Леонтьева в адаптации "
            "Д.А. Леонтьева. Применялся также опросник «Шкала тревоги» Спилбергера Ч.Д.",
            "В тексте есть «просто цитата» без признака методики.",
        ]
    )
    names = [i.name for i in f.instruments]
    assert names == ["Смысложизненные ориентации", "Шкала тревоги"]
    first = f.instruments[0]
    assert first.abbr == "СЖО" and "леонтьев" in {k for _, k in first.authors}
    assert first.adaptation and first.adaptation.startswith("Д.А. Леонтьева")


def test_no_section_2_1_means_no_instruments():
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para("Методика «Что-то».")
    assert Facts(b.build()).instruments == []


def test_facts_are_cached():
    f = thesis(intro=["Задачи: изучить; выявить."])
    assert f.tasks is f.tasks and f.quantities is f.quantities


def test_hypothesis_status_from_next_sentence_only_when_missing():
    f = thesis(
        intro=["Гипотеза: связь есть."],
        ch2=[
            "Гипотеза 1 о связи тревожности и дохода. Она подтвердилась.",
            "Гипотеза 2 о различиях групп. Гипотеза 3 не подтвердилась.",
            "Гипотеза 4 подтвердилась. Это не подтвердилось для группы Б.",
        ],
    )
    got = [m.status for m in f.hypothesis_mentions]
    # 1: статус из следующего предложения; 2: следующее — о другой гипотезе, не берём;
    # 3: свой статус; 4: свой статус не перетирается следующим предложением.
    assert got == ["confirmed", None, "not_confirmed", "confirmed"]
