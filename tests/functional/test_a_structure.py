# ruff: noqa: E501
"""SPEC 4.A: STR-01..05, INT-01, VOL-01, PAGE-01 и общий критерий «чистая работа - 0 замечаний»."""

import pytest

from tests.functional.conftest import all_findings, levels, of_rule
from tests.functional.thesis import Thesis, p
from tests.functional.thesis import h1 as H1


def test_clean_work_has_zero_violations_and_suspicions(clean_report):
    """SPEC 4 (общий критерий) и 5 (Точность): на эталонной чистой работе 0 нарушений и подозрений."""
    s = clean_report["summary"]
    assert s["violation"] == 0 and s["suspicion"] == 0, [
        (f["rule_id"], f["message"]) for f in all_findings(clean_report)
    ]


def test_clean_report_lists_passed_rules(clean_report):
    """SPEC 3.1: в сводке показываются проверки без находок («пройдено»)."""
    assert {"STR-01", "STR-03", "NUM-01", "TBL-03", "CON-01", "HYP-01", "TSK-01"} <= set(
        clean_report["summary"]["passed_rules"]
    )


# ---- STR-01 ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "heading, label",
    [
        ("ЗАКЛЮЧЕНИЕ", "заключ"),
        ("ВВЕДЕНИЕ", "введ"),
        ("СПИСОК ИСПОЛЬЗОВАННЫХ", "литератур|источник"),
        ("ПРИЛОЖЕНИЕ А", "приложен"),
    ],
)
def test_str01_missing_required_section_is_violation(api, clean, heading, label):
    import re

    t = clean.copy()
    # удалить заголовок раздела целиком вместе с его содержимым до следующего h1
    i = t._idx(heading)
    j = i + 1
    while j < len(t.blocks) and t.blocks[j]["k"] != "h1":
        j += 1
    del t.blocks[i:j]
    rep = api.report(t)
    fs = [f for f in of_rule(rep, "STR-01") if f["level"] == "violation"]
    assert fs, "нет нарушения STR-01"
    assert any(re.search(label, f["message"], re.I) for f in fs), [f["message"] for f in fs]


@pytest.mark.parametrize(
    "variant", ["Список литературы", "Библиографический список", "СПИСОК ИСПОЛЬЗОВАННОЙ ЛИТЕРАТУРЫ"]
)
def test_str01_bibliography_title_variants_recognized(api, clean, variant):
    t = clean.sub("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", variant, count=2)
    rep = api.report(t)
    assert not [f for f in of_rule(rep, "STR-01") if f["level"] == "violation"]


@pytest.mark.parametrize("variant", ["ОГЛАВЛЕНИЕ", "Содержание"])
def test_str01_toc_title_variants_recognized(api, clean, variant):
    rep = api.report(clean.sub("СОДЕРЖАНИЕ", variant))
    assert not [f for f in of_rule(rep, "STR-01") if f["level"] == "violation"]


def test_str01_wrong_section_order_is_suspicion(api, clean):
    """Приложение перед списком литературы -> подозрение (не нарушение)."""
    t = clean.copy()
    i = (
        t._idx("ПРИЛОЖЕНИЕ А", 1)
        if False
        else [k for k, b in enumerate(t.blocks) if b.get("t") == "ПРИЛОЖЕНИЕ А"][-1]
    )
    app = t.blocks[i:]
    del t.blocks[i:]
    k = t._idx("СПИСОК ИСПОЛЬЗОВАННЫХ")
    t.blocks[k:k] = app
    rep = api.report(t)
    lv = levels(rep, "STR-01")
    assert "suspicion" in lv and "violation" not in lv, lv


def test_str01_three_chapters_is_suspicion_not_violation(api, clean):
    t = clean.insert_before(
        "ЗАКЛЮЧЕНИЕ",
        H1("ГЛАВА 3. Дополнительная глава"),
        p("Текст дополнительной главы."),
        p("Выводы по главе 3", False),
    )
    rep = api.report(t)
    lv = levels(rep, "STR-01")
    assert "suspicion" in lv and "violation" not in lv, lv


def test_str01_no_title_page_is_suspicion(api, clean):
    t = clean.copy()
    del t.blocks[:6]
    rep = api.report(t)
    lv = levels(rep, "STR-01")
    assert "suspicion" in lv and "violation" not in lv, lv


# ---- STR-02 ---------------------------------------------------------------------------
def test_str02_toc_entry_without_heading_is_violation(api, clean):
    t = clean.insert_after(
        "1.2. Академическая адаптация",
        p("1.3. Несуществующий параграф ........ 20", False, tag="x"),
    )
    # вставили абзац в тело, а не в оглавление - делаем правильно: правим запись оглавления
    t = clean.sub(
        "2.2. Результаты исследования ........ 10", "2.3. Призрачный параграф ........ 10"
    )
    rep = api.report(t)
    assert [f for f in of_rule(rep, "STR-02") if f["level"] == "violation"]


def test_str02_heading_without_toc_entry_is_violation(api, clean):
    t = clean.drop("2.1. Организация и методы исследования ........")
    rep = api.report(t)
    fs = [f for f in of_rule(rep, "STR-02") if f["level"] == "violation"]
    assert fs and any("2.1" in f["message"] for f in fs)


def test_str02_page_numbers_are_ignored(api, clean):
    t = clean.sub("ВВЕДЕНИЕ ........ 3", "ВВЕДЕНИЕ ........ 99")
    rep = api.report(t)
    assert not of_rule(rep, "STR-02") or all(
        f["level"] == "not_checked" for f in of_rule(rep, "STR-02")
    )


# ---- STR-03 / STR-04 -----------------------------------------------------------------
def test_str03_missing_chapter_conclusions_is_violation(api, clean):
    t = clean.drop_section("Выводы по главе 2").sub(
        "Выводы по главе 2 ........", "2.2. Результаты исследования ........"
    )
    rep = api.report(t)
    fs = [f for f in of_rule(rep, "STR-03") if f["level"] == "violation"]
    assert fs and any("2" in f["message"] for f in fs)


@pytest.mark.parametrize("title", ["Выводы по первой главе", "Выводы"])
def test_str03_conclusions_title_variants(api, clean, title):
    t = clean.sub("Выводы по главе 1", title)
    rep = api.report(t)
    assert not [f for f in of_rule(rep, "STR-03") if f["level"] == "violation"]


def test_str04_conclusion_duplicates_chapter_conclusions_is_suspicion(api, clean):
    dup = "Данные эмпирического исследования показывают согласованность мотивации и адаптации у 120 студентов."
    t = clean.insert_after("3. Выявлена связь", p(dup, False))
    rep = api.report(t)
    fs = [f for f in of_rule(rep, "STR-04") if f["level"] == "suspicion"]
    assert fs and len(fs[0]["locations"]) >= 2


# ---- STR-05 ---------------------------------------------------------------------------
def test_str05_appendix_without_reference_is_violation(api, clean):
    t = clean.sub("; полные данные даны в приложении А", "").sub(
        ", полные данные в приложении А", ""
    )
    rep = api.report(t)
    assert [f for f in of_rule(rep, "STR-05") if f["level"] == "violation"]


def test_str05_reference_to_missing_appendix_is_violation(api, clean):
    t = clean.sub("полные данные даны в приложении А", "полные данные даны в приложении Б")
    rep = api.report(t)
    assert [f for f in of_rule(rep, "STR-05") if f["level"] == "violation"]


def test_str05_appendix_without_page_break_is_violation(api, clean):
    t = clean.copy()
    for b in t.blocks:
        if b.get("t") == "ПРИЛОЖЕНИЕ А":
            b["np"] = False
    rep = api.report(t)
    assert [f for f in of_rule(rep, "STR-05") if f["level"] == "violation"]


# ---- INT-01 ---------------------------------------------------------------------------
INT_ELEMENTS = [
    ("Актуальность исследования", "актуальн"),
    ("Степень разработанности", "изученн|разработанн"),
    ("Цель исследования", "цел"),
    ("Объект исследования", "объект"),
    ("Предмет исследования", "предмет"),
    ("Гипотеза исследования", "гипотез"),
    ("Теоретико-методологические", "методологическ"),
    ("Методы и методики", "метод"),
    ("Выборка исследования", "выборк"),
    ("Научная новизна", "новизн"),
    ("Теоретическая значимость", "теоретическая значимость"),
    ("Практическая значимость", "практическая значимость"),
    ("Апробация", "апробац"),
]


def clean_report_cache(api, clean):
    return api.report(clean)


@pytest.mark.parametrize("start, pattern", INT_ELEMENTS)
def test_int01_missing_element_is_violation(api, clean, start, pattern):
    import re

    rep = api.report(clean.drop(start))
    # слово элемента может встретиться в теле других абзацев введения: тогда по SPEC это «подозрение»
    fs = [f for f in of_rule(rep, "INT-01") if f["level"] in ("violation", "suspicion")]
    assert fs and any(re.search(pattern, f["message"], re.I) for f in fs), [
        f["message"] for f in fs
    ]
    assert not [
        f for f in of_rule(clean_report_cache(api, clean), "INT-01") if f["level"] != "not_checked"
    ]


def test_int01_implementation_is_optional(api, clean):
    """«Внедрение» - при наличии: отсутствие не находка (в чистой работе его нет)."""
    rep = api.report(clean)
    assert not [f for f in of_rule(rep, "INT-01") if f["level"] != "not_checked"]


def test_int01_report_has_element_table(clean_report):
    """Критерий приёмки INT-01: таблица «элемент -> найден/не найден -> место»."""
    rr = [r for b in clean_report["blocks"] for r in b["rule_results"] if r["rule_id"] == "INT-01"][
        0
    ]
    art = rr["artifacts"]
    assert art, "у INT-01 нет artifacts"
    text = str(art).lower()
    assert "актуальн" in text and "гипотез" in text


def test_int01_element_only_inside_paragraph_is_suspicion(api, clean):
    t = clean.sub(
        "Апробация результатов: доклад на научно-практической конференции.",
        "Результаты обсуждались на кафедре, апробация прошла на конференции.",
    )
    rep = api.report(t)
    lv = {f["level"] for f in of_rule(rep, "INT-01") if "апробац" in f["message"].lower()}
    assert lv == {"suspicion"}, lv


def test_int01_implementation_act_missing_is_suspicion(api, clean):
    t = clean.sub(
        "в работе кураторов.", "в работе кураторов; результаты внедрены в практику центра."
    )
    rep = api.report(t)
    assert [f for f in of_rule(rep, "INT-01") if f["level"] == "suspicion"]


# ---- VOL-01 ---------------------------------------------------------------------------
def test_vol01_in_range_passes_and_reports_method_and_sections(clean_report):
    assert clean_report["volume"]["method"] in ("layout", "estimate")
    assert clean_report["volume"]["by_section"]
    assert clean_report["volume"]["estimate_formula"]  # метод оценки зафиксирован в отчёте
    assert not [f for f in of_rule(clean_report, "VOL-01")]


@pytest.mark.parametrize("pages", [20, 110])
def test_vol01_out_of_range_is_suspicion_not_violation(api, pages):
    rep = api.report(Thesis(pages=pages))
    lv = levels(rep, "VOL-01")
    assert lv == {"suspicion"}, lv


# ---- PAGE-01 --------------------------------------------------------------------------
def _with_margins(t, left, right):
    import io

    from docx import Document
    from docx.shared import Cm

    d = Document(io.BytesIO(t.bytes()))
    s = d.sections[0]
    s.left_margin, s.right_margin = Cm(left), Cm(right)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_page01_wrong_margins_is_violation(api, clean):
    rep = api.report(_with_margins(clean, 2.0, 2.0))
    assert [f for f in of_rule(rep, "PAGE-01") if f["level"] == "violation"]


def test_page01_correct_margins_pass(api, clean):
    rep = api.report(_with_margins(clean, 3.0, 1.5))
    assert not of_rule(rep, "PAGE-01")


def test_page01_top_bottom_margins_not_checked(api, clean):
    import io

    from docx import Document
    from docx.shared import Cm

    d = Document(io.BytesIO(clean.bytes()))
    d.sections[0].top_margin = Cm(5)
    buf = io.BytesIO()
    d.save(buf)
    assert not of_rule(api.report(buf.getvalue()), "PAGE-01")
