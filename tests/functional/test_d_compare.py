# ruff: noqa: E501
"""SPEC 4.C: DIF-01..06 (+ полный отчёт новой версии в ответе сравнения)."""

import pytest

from tests.functional.thesis import NB, p, table


def impact(rep, n: int | None = None):
    fs = rep["diff"]["impact"]
    if n is None:
        return fs
    return [
        f for f in fs if f["rule_id"].startswith(f"DIF-05.{n}") or f["rule_id"] == f"DIF-05.{n}"
    ]


def sections(rep):
    return rep["diff"]["sections"]


def para_ops(rep, status):
    return [pp for s in sections(rep) for pp in s["paragraphs"] if pp["status"] == status]


# ---- общее ----------------------------------------------------------------------------
def test_compare_identical_versions_all_sections_unchanged(api, clean):
    rep = api.diff(clean, clean)
    assert all(s["status"] == "unchanged" for s in rep["diff"]["sections"]), [
        (s["status"], s.get("old_title"))
        for s in rep["diff"]["sections"]
        if s["status"] != "unchanged"
    ]


def test_compare_identical_versions_is_empty_diff(api, clean):
    rep = api.diff(clean, clean)
    d = rep["diff"]
    assert not d["moves"] and not d["number_changes"] and not d["impact"]
    assert all(t["status"] == "unchanged" for t in d["tables"])
    assert not d["dynamics"]["fixed"] and not d["dynamics"]["new"]


def test_compare_contains_full_check_report_of_new_version(api, clean):
    rep = api.diff(clean, clean)
    assert rep["new"]["summary"] and rep["new"]["blocks"] and rep["new"]["matrix"]
    assert rep["old"]["file"]["name"] == "old.docx" and rep["new"]["file"]["name"] == "new.docx"


def test_compare_is_deterministic(api, clean):
    new = clean.sub(
        "Объект исследования: учебная мотивация", "Объект исследования: адаптационная мотивация"
    )
    a, b = api.diff(clean, new), api.diff(clean, new)
    for r in (a, b):
        r.pop("checked_at")
        r["new"].pop("checked_at")
    assert a == b


# ---- DIF-01 ---------------------------------------------------------------------------
def test_dif01_modified_paragraph_has_word_level_segments(api, clean):
    new = clean.sub(
        "Объект исследования: учебная мотивация студентов магистратуры.",
        "Объект исследования: учебная мотивация студентов бакалавриата.",
    )
    rep = api.diff(clean, new)
    mod = para_ops(rep, "modified")
    assert len(mod) == 1
    segs = mod[0]["segments"]
    assert any(s["op"] == "del" and "магистратуры" in s["text"] for s in segs)
    assert any(s["op"] == "ins" and "бакалавриата" in s["text"] for s in segs)
    assert any(s["op"] == "equal" for s in segs)


def test_dif01_added_and_deleted_paragraphs(api, clean):
    new = clean.drop("Апробация результатов").insert_after(
        "Объект исследования",
        p("Дополнительное уточнение границ исследуемой совокупности студентов."),
    )
    rep = api.diff(clean, new)
    assert any("Апробация" in (x["text"] or "") for x in para_ops(rep, "deleted"))
    assert any("Дополнительное уточнение" in (x["text"] or "") for x in para_ops(rep, "inserted"))


def test_dif01_unchanged_sections_are_marked_unchanged(api, clean):
    new = clean.sub(
        "Объект исследования: учебная мотивация студентов магистратуры.",
        "Объект исследования: учебная мотивация студентов бакалавриата.",
    )
    rep = api.diff(clean, new)
    st = [s["status"] for s in sections(rep)]
    assert "modified" in st and st.count("unchanged") >= len(st) - 3


def test_dif01_renamed_section_is_one_section_not_add_remove(api, clean):
    new = clean.sub(
        "2.2. Результаты исследования", "2.2. Результаты эмпирического исследования", count=2
    )
    rep = api.diff(clean, new)
    ren = [
        s for s in sections(rep) if s["status"] == "renamed" and s["old_title"] != s["new_title"]
    ]
    assert len(ren) == 1
    assert (
        "Результаты исследования" in ren[0]["old_title"] and "эмпирического" in ren[0]["new_title"]
    )
    assert not [s for s in sections(rep) if s["status"] in ("added", "removed")]


def test_dif01_added_and_removed_section(api, clean):
    new = clean.drop_section("2.1. Организация и методы исследования").sub(
        "2.1. Организация и методы исследования ........", "2.2. Результаты исследования ........"
    )
    rep = api.diff(clean, new)
    assert [s for s in sections(rep) if s["status"] == "removed"]


# ---- DIF-02 ---------------------------------------------------------------------------
MOVED = (
    "Особое место занимает рассмотрение отдельных форм саморегуляции, которые связаны с организацией "
    "учебной деятельности и с готовностью принимать решения в ситуации неопределённости."
)


def test_dif02_moved_paragraph_with_one_word_change(api, clean):
    old = clean.insert_after("Шкала учебной мотивации разработана", p(MOVED))
    new = clean.insert_after(
        "Понятие адаптации раскрыто", p(MOVED.replace("отдельных", "некоторых"))
    )
    rep = api.diff(old, new)
    moves = rep["diff"]["moves"]
    assert len(moves) == 1, moves
    segs = moves[0]["segments"]
    changed = [s for s in segs if s["op"] in ("ins", "del")]
    assert {s["text"].strip() for s in changed} == {"отдельных", "некоторых"}
    assert "1.1" in moves[0]["from_section"] and "1.2" in moves[0]["to_section"]
    # перемещённый абзац не засчитан ещё и как «удалён»/«добавлен»
    assert not [x for x in para_ops(rep, "deleted") if "саморегуляции" in (x["text"] or "")]
    assert not [x for x in para_ops(rep, "inserted") if "саморегуляции" in (x["text"] or "")]


def test_dif02_dissimilar_text_is_not_a_move(api, clean):
    old = clean.insert_after("Шкала учебной мотивации разработана", p(MOVED))
    new = clean.insert_after(
        "Понятие адаптации раскрыто", p("Совершенно другой по смыслу абзац о проведении замеров.")
    )
    assert not api.diff(old, new)["diff"]["moves"]


# ---- DIF-03 ---------------------------------------------------------------------------
def test_dif03_number_changes_list_old_new_context_and_places(api, clean):
    new = clean.sub(f"n{NB}={NB}120", f"n{NB}={NB}118", within="ВВЕДЕНИЕ")
    rep = api.diff(clean, new)
    ch = rep["diff"]["number_changes"]
    hit = [c for c in ch if c["old"].strip() == "120" and c["new"].strip() == "118"]
    assert hit
    assert hit[0]["context"] and (hit[0]["loc_old"] or hit[0]["loc_new"])
    assert hit[0].get("kind")  # типизированная величина (объём выборки) выделена


def test_dif03_p_value_and_statistic_changes(api, clean):
    new = clean.sub(f"rs{NB}={NB}0,45", f"rs{NB}={NB}0,38")
    ch = api.diff(clean, new)["diff"]["number_changes"]
    assert any("0,45" in c["old"] and "0,38" in c["new"] for c in ch)


# ---- DIF-04 ---------------------------------------------------------------------------
def test_dif04_cell_change(api, clean):
    rows = [
        ["Показатель", "Группа 1", "Группа 2"],
        ["Среднее значение (M)", "12,4", "13,9"],
        ["Стандартное отклонение", "2,1", "2,4"],
    ]
    new = clean.copy()
    for b in new.blocks:
        if b["k"] == "table" and b["caption"].startswith("Таблица 1"):
            b["rows"] = rows
    rep = api.diff(clean, new)
    mod = [t for t in rep["diff"]["tables"] if t["status"] == "modified"]
    assert len(mod) == 1
    cells = [c for r in mod[0]["rows"] for c in r.get("cells", [])]
    assert any(c["old"] == "13,1" and c["new"] == "13,9" for c in cells)


def test_dif04_added_table(api, clean):
    new = clean.insert_after(
        "Гипотеза о том, что учебная",
        table(
            "Таблица 3 – Дополнительная таблица",
            [["Показатель", "Значение"], ["Параметр общий", "5,5"]],
        ),
    )
    rep = api.diff(clean, new)
    assert [t for t in rep["diff"]["tables"] if t["status"] == "added"]


def test_dif04_removed_table(api, clean):
    new = clean.drop("Таблица 2 – Сравнение групп")
    rep = api.diff(clean, new)
    assert [t for t in rep["diff"]["tables"] if t["status"] == "removed"]


def test_dif04_renumbered_and_retitled_flags(api, clean):
    new = clean.sub("Таблица 2 – Сравнение групп", "Таблица 3 – Сравнение двух групп")
    rep = api.diff(clean, new)
    flags = {f for t in rep["diff"]["tables"] for f in t["flags"]}
    assert {"renumbered", "retitled"} <= flags


def test_dif04_matching_by_content_when_numbering_shifted(api, clean):
    new = (
        clean.insert_before(
            "Таблица 1 – Описательные",
            table(
                "Таблица 1 – Новая вводная таблица",
                [["Показатель", "Значение"], ["Параметр общий", "5,5"]],
            ),
        )
        .sub("Таблица 1 – Описательные статистики", "Таблица 2 – Описательные статистики")
        .sub("Таблица 2 – Сравнение групп", "Таблица 3 – Сравнение групп")
    )
    rep = api.diff(clean, new)
    t = rep["diff"]["tables"]
    assert len([x for x in t if x["status"] == "added"]) == 1
    assert not [x for x in t if x["status"] == "removed"]


# ---- DIF-05 : шесть сценариев, у каждого указаны место правки и несинхронные места -----
def test_dif05_1_acceptance_with_gender_split_sentence(api, clean):
    new = clean.sub(f"n{NB}={NB}120", f"n{NB}={NB}118", within="ВВЕДЕНИЕ")
    assert impact(api.diff(clean, new), 1)


def test_dif05_1_value_changed_but_old_value_remains(api, clean):
    old = clean.sub(", из них 60% женщин и 40% мужчин", "")
    new = old.sub(f"n{NB}={NB}120", f"n{NB}={NB}118", within="ВВЕДЕНИЕ")
    fs = impact(api.diff(old, new), 1)
    assert fs and all(f["level"] == "suspicion" for f in fs)
    msg = " ".join(f["message"] for f in fs)
    assert "120" in msg and "118" in msg
    assert len(fs[0]["locations"]) >= 2  # место правки + места со старым значением


def test_dif05_2_intro_hypothesis_changed_chapter2_and_conclusion_not(api, clean):
    new = clean.sub(
        "Гипотеза исследования: учебная мотивация студентов положительно связана с уровнем академической адаптации.",
        "Гипотеза исследования: учебная мотивация студентов отрицательно связана со стрессоустойчивостью.",
    )
    fs = impact(api.diff(clean, new), 2)
    assert fs and fs[0]["level"] == "suspicion"
    assert len(fs[0]["locations"]) >= 2


def test_dif05_2_task_changed_in_intro_conclusion_not(api, clean):
    new = clean.sub(
        "Выявить связь учебной мотивации с академической адаптацией студентов.",
        "Описать динамику профессионального самоопределения выпускников.",
    )
    assert impact(api.diff(clean, new), 2)


def test_dif05_3_method_removed_but_terms_remain(api, clean):
    new = clean.sub(
        "коэффициент корреляции Спирмена, U-критерий Манна–Уитни",
        "U-критерий Манна–Уитни",
        within="ВВЕДЕНИЕ",
    ).sub(
        "применялись коэффициент корреляции Спирмена и U-критерий Манна–Уитни",
        "применялся U-критерий Манна–Уитни",
    )
    fs = impact(api.diff(clean, new), 3)
    assert fs and "Спирмен" in " ".join(f["message"] for f in fs)
    assert len(fs[0]["locations"]) >= 1


def test_dif05_4_table_removed_but_references_remain(api, clean):
    new = clean.drop("Таблица 2 – Сравнение групп")
    fs = impact(api.diff(clean, new), 4)
    assert fs and any("2" in f["message"] for f in fs)


def test_dif05_4_table_renumbered_references_stale(api, clean):
    new = clean.sub("Таблица 2 – Сравнение групп", "Таблица 3 – Сравнение групп").sub(
        "1 рисунок и 2 таблицы", "1 рисунок и 2 таблицы"
    )
    fs = impact(api.diff(clean, new), 4)
    assert fs


def test_dif05_5_counts_changed_phrase_unchanged(api, clean):
    new = clean.insert_after(
        "Гипотеза о том, что учебная",
        table(
            "Таблица 3 – Дополнительная таблица",
            [["Показатель", "Значение"], ["Параметр общий", "5,5"]],
        ),
        p("Данные приведены в табл. 3 и приложении А."),
    )
    fs = impact(api.diff(clean, new), 5)
    assert fs and fs[0]["level"] == "suspicion"


def test_dif05_6_results_changed_conclusions_not(api, clean):
    new = clean.copy()
    for b in new.blocks:
        if b["k"] == "table" and b["caption"].startswith("Таблица 2"):
            b["rows"] = [
                ["Показатель", "Группа 1", "Группа 2"],
                ["Мотивация общая", "30,2", "38,5"],
                ["Адаптация общая", "41,0", "44,3"],
            ]
    fs = impact(api.diff(clean, new), 6)
    assert fs and fs[0]["level"] == "suspicion"


def test_dif05_6_no_finding_when_conclusions_updated_together(api, clean):
    new = clean.sub(
        "согласованность мотивации и адаптации у 120 студентов",
        "слабую согласованность мотивации и адаптации у 120 студентов",
    )
    for b in new.blocks:
        if b["k"] == "table" and b["caption"].startswith("Таблица 2"):
            b["rows"] = [
                ["Показатель", "Группа 1", "Группа 2"],
                ["Мотивация общая", "30,2", "38,5"],
                ["Адаптация общая", "41,0", "44,3"],
            ]
    assert not impact(api.diff(clean, new), 6)


# ---- DIF-06 ---------------------------------------------------------------------------
def test_dif06_dynamics_fixed_new_remaining(api, clean):
    old = clean.sub("приведены в табл. 1; ", "приведены ниже; ").drop("Апробация результатов")
    new = clean.drop("Практическая значимость исследования").drop("Апробация результатов")
    rep = api.diff(old, new)
    dyn = rep["diff"]["dynamics"]
    fixed_rules = {x["rule_id"] for x in dyn["fixed"]}
    new_rules = {x["rule_id"] for x in dyn["new"]}
    rem_rules = {x["rule_id"] for x in dyn["remaining"]}
    assert "NUM-02" in fixed_rules  # ссылка на таблицу вернулась
    assert "INT-01" in rem_rules  # «Апробация» отсутствует в обеих
    assert "INT-01" in new_rules or any(
        r.startswith("INT") for r in new_rules
    )  # исчезла практическая значимость


# ---- ошибки входа ---------------------------------------------------------------------
@pytest.mark.parametrize("bad_field", ["old", "new"])
def test_compare_invalid_file_points_to_field(api, clean, bad_field):
    good, bad = clean.bytes(), b"%PDF-1.7 not a docx"
    old, new = (bad, good) if bad_field == "old" else (good, bad)
    r = api.compare(old, new)
    assert r.status_code in (415, 422)
    err = r.json()["error"]
    assert err["field"] == bad_field and "Traceback" not in r.text


def test_compare_missing_second_file(client, clean):
    from tests.functional.conftest import DOCX

    r = client.post("/api/compare", files={"old": ("o.docx", clean.bytes(), DOCX)})
    assert r.status_code in (400, 422)
    assert r.json()["error"]["code"] in ("missing_file", "bad_request", "validation_error")
