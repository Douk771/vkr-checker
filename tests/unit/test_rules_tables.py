from dataclasses import replace

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.engine import run_rule
from vkr_checker.checks.tables_format import (
    Tbl01Indents,
    Tbl02Spacing,
    Tbl03Width,
    Tbl04ColumnProportions,
    Tbl05Alignment,
    Tbl07RowHeight,
    Tbl08KeepNext,
    Tbl09MissingStyle,
)
from vkr_checker.model.document import (
    Caption,
    Cell,
    CellRef,
    PageSetup,
    ParaFormat,
    Paragraph,
    Row,
    Table,
    Valued,
)

CLEAN = ParaFormat(
    first_line_cm=Valued(0.0, "para_style"),
    hanging_cm=Valued(0.0, "para_style"),
    left_cm=Valued(0.0, "para_style"),
    line_spacing=Valued(1.0, "para_style"),
    line_rule=Valued("auto", "para_style"),
    space_after_pt=Valued(0.0, "para_style"),
    v_align=Valued("center", "direct"),
)


def V(value, origin="direct"):
    return Valued(value, origin)


def fmt(base=CLEAN, **kw) -> ParaFormat:
    return replace(base, **kw)


def build(rows, formats=None, caption="Таблица 1 - Данные", **table_kw):
    """rows: тексты; formats[(r, c)] -> ParaFormat (по умолчанию CLEAN, шапка по центру)."""
    formats = formats or {}
    b = DocBuilder()
    b.heading("Глава 2", kind="CHAPTER", number="2")
    b.para(caption or "текст")
    doc = b.build()
    out_rows = []
    n = 100
    for r, row in enumerate(rows, 1):
        cells = []
        for c, text in enumerate(row, 1):
            n += 1
            numeric = text.replace(",", "").replace(".", "").isdigit()
            default = fmt(align=V("center" if r == 1 or numeric else "left"))
            p = Paragraph(
                idx=n, text=text, fmt=formats.get((r, c), default), container="table_cell",
                cell=CellRef(1, r, c), style_name="Обычный",
            )  # fmt: skip
            cells.append(Cell(row=r, col=c, text=text, paragraphs=(p,)))
        out_rows.append(Row(cells=tuple(cells)))
    kw = dict(layout_type="fixed", grid_cols_cm=(16.5 / len(rows[0]),) * len(rows[0]))
    kw.update(table_kw)
    table = Table(idx=1, rows=tuple(out_rows), section_id="s1", **kw)
    cap = Caption(kind="table", number="1", title=caption or "", label_text="Таблица",
                  paragraph_idx=1, target=1)  # fmt: skip
    table = replace(table, caption_idx=0 if caption else None)
    return replace(
        doc,
        tables=(table,),
        captions=(cap,) if caption else (),
        page_setup=(PageSetup(0, 3.0, 1.5, 2.0, 2.0, 16.5),),
    )


def run(rule, doc):
    return run_rule(CheckContext.build(doc), rule)


ROWS = [["Показатель", "Значение"], ["Возраст", "24,5"], ["Тревожность", "11,2"]]


# --- TBL-01 -------------------------------------------------------------------------------
def test_tbl01_clean_passes():
    assert run(Tbl01Indents(), build(ROWS)).outcome == "passed"


def test_tbl01_inherited_indent_collapses_with_origin_hint():
    red = fmt(first_line_cm=V(1.25, "para_style"), align=V("left"))
    doc = build(ROWS, {(2, 1): red, (3, 1): red, (2, 2): red})
    res = run(Tbl01Indents(), doc)
    (f,) = res.findings
    assert f.level == "violation" and f.count == 3 and "красная строка" in f.message
    assert "Таблица 1" in f.message and "стиля абзаца «Обычный»" in f.hint
    assert f.values["all_cells"] and len(f.locations) == 3


def test_tbl01_hanging_and_left_are_separate_findings_and_epsilon():
    doc = build(
        ROWS,
        {(2, 1): fmt(hanging_cm=V(0.5), left_cm=V(0.5)), (3, 1): fmt(left_cm=V(0.005))},
    )
    assert sorted(f.fingerprint.split("|")[-1] for f in run(Tbl01Indents(), doc).findings) == [
        "hanging",
        "left",
    ]


# --- TBL-02 -------------------------------------------------------------------------------
def test_tbl02_line_and_after_spacing():
    ok = fmt(line_spacing=V(1.0), space_after_pt=V(0.0))
    assert run(Tbl02Spacing(), build(ROWS, {(2, 1): ok})).outcome == "passed"
    bad_line = fmt(line_spacing=V(1.5, "para_style"))
    bad_after = fmt(space_after_pt=V(8.0, "para_style"))
    auto_after = fmt(space_after_pt=V("auto", "table_style"))
    exact = fmt(line_rule=V("exact"), line_spacing=V(14.0))
    doc = build(ROWS, {(2, 1): bad_line, (2, 2): bad_after, (3, 1): auto_after, (3, 2): exact})
    got = {f.fingerprint.split("|")[-1]: f.count for f in run(Tbl02Spacing(), doc).findings}
    assert got == {"line": 2, "space_after": 2}


def test_tbl02_unset_values_mean_single_and_zero():
    plain = ParaFormat(v_align=V("center"))
    assert run(Tbl02Spacing(), build(ROWS, {(2, 1): plain})).outcome == "passed"


# --- TBL-03 -------------------------------------------------------------------------------
def test_tbl03_clean_and_autofit_and_width():
    assert run(Tbl03Width(), build(ROWS)).outcome == "passed"
    res = run(Tbl03Width(), build(ROWS, layout_type="autofit"))
    assert [f.fingerprint for f in res.findings] == ["TBL-03|1|layout"]
    res = run(Tbl03Width(), build(ROWS, grid_cols_cm=(8.0, 7.0)))
    (f,) = res.findings
    assert f.fingerprint == "TBL-03|1|width" and f.values["sum_cm"] == 15.0
    within = run(Tbl03Width(), build(ROWS, grid_cols_cm=(8.0, 8.4)))
    assert within.outcome == "passed"


def test_tbl03_without_page_setup_skips_width_check():
    doc = replace(build(ROWS, grid_cols_cm=(1.0, 1.0)), page_setup=())
    assert run(Tbl03Width(), doc).outcome == "passed"


# --- TBL-04 -------------------------------------------------------------------------------
def test_tbl04_wide_number_column_and_wrong_widest():
    rows = [["№", "Название показателя"], ["1", "Очень длинное название показателя шкалы"]]
    res = run(Tbl04ColumnProportions(), build(rows, grid_cols_cm=(3.0, 13.5)))
    (f,) = res.findings
    assert f.level == "suspicion" and f.fingerprint == "TBL-04|1|num_width"
    ok = run(Tbl04ColumnProportions(), build(rows, grid_cols_cm=(1.0, 15.5)))
    assert ok.outcome == "passed"
    rows2 = [["Код", "Название"], ["А1", "Очень длинное название показателя шкалы тревоги"]]
    res = run(Tbl04ColumnProportions(), build(rows2, grid_cols_cm=(12.0, 4.5)))
    assert [f.fingerprint for f in res.findings] == ["TBL-04|1|widest"]


# --- TBL-05 -------------------------------------------------------------------------------
def test_tbl05_clean_passes():
    assert run(Tbl05Alignment(), build(ROWS)).outcome == "passed"


def test_tbl05_numeric_left_header_left_text_justified():
    formats = {
        (1, 1): fmt(align=V("left")),
        (2, 1): fmt(align=V("justify")),
        (2, 2): fmt(align=V("left")),  # число «24,5» слева
        (3, 1): fmt(align=V("left")),
    }
    res = run(Tbl05Alignment(), build(ROWS, formats))
    got = {f.fingerprint.split("|")[-1] for f in res.findings}
    assert got == {"header_align", "text_align", "numeric_align"}
    assert all(f.level == "violation" for f in res.findings)


def test_tbl05_number_column_and_vertical_align():
    """Нумерация пунктов («№») — по левому краю или по центру, обе допустимы."""
    rows = [["№", "Показатель"], ["1", "Возраст"]]
    formats = {(2, 1): fmt(align=V("left")), (2, 2): fmt(v_align=None, align=V("left"))}
    got = {
        f.fingerprint.split("|")[-1] for f in run(Tbl05Alignment(), build(rows, formats)).findings
    }
    assert got == {"v_align"}
    formats[(2, 1)] = fmt(align=V("justify"))
    got = {
        f.fingerprint.split("|")[-1] for f in run(Tbl05Alignment(), build(rows, formats)).findings
    }
    assert "index_align" in got


def test_tbl05_mixed_column_aligned_as_text_and_index_column_free():
    rows = [
        ["№ модуля", "Категория", "n"],
        ["1", "мужчины", "37"],
        ["2", "23–29", "9"],
        ["3", "тимлид", "25"],
    ]
    left = {(r, c): fmt(align=V("left")) for r in (2, 3, 4) for c in (1, 2)}
    res = run(Tbl05Alignment(), build(rows, left))
    assert res.outcome == "passed"  # «23–29» среди текста — по левому; № — по левому можно
    numbers_left = {**left, (2, 3): fmt(align=V("left"))}
    got = {
        f.fingerprint.split("|")[-1]
        for f in run(Tbl05Alignment(), build(rows, numbers_left)).findings
    }
    assert got == {"numeric_align"}  # столбец только из чисел — по центру


def test_tbl05_gray_zone_cells_are_suspicion_only_when_clearly_wrong():
    rows = [["Показатель", "Значение"], ["Доза", "12 мг"]]
    centered = run(
        Tbl05Alignment(),
        build(rows, {(2, 2): fmt(align=V("center"))}),
    )
    assert centered.outcome == "passed"
    res = run(Tbl05Alignment(), build(rows, {(2, 2): fmt(align=V("justify"))}))
    (f,) = res.findings
    assert f.level == "suspicion" and f.fingerprint.endswith("gray_align")


# --- TBL-07 -------------------------------------------------------------------------------
def test_tbl07_exact_heights():
    doc = build(ROWS)
    t = doc.tables[0]
    rows = list(t.rows)
    rows[1] = replace(rows[1], height_rule="exact", height_twips=1000)  # 50 pt
    rows[2] = replace(rows[2], height_rule="exact", height_twips=400)  # 20 pt
    doc = replace(doc, tables=(replace(t, rows=tuple(rows)),))
    (f,) = run(Tbl07RowHeight(), doc).findings
    assert f.level == "suspicion" and f.values["height_pt"] == 50
    atleast = replace(rows[1], height_rule="atLeast")
    rows[1] = atleast
    assert (
        run(Tbl07RowHeight(), replace(doc, tables=(replace(t, rows=tuple(rows)),))).outcome
        == "passed"
    )


# --- TBL-08 -------------------------------------------------------------------------------
def with_caption_keep(doc, keep):
    paras = list(doc.paragraphs)
    paras[0] = replace(paras[0], fmt=ParaFormat(keep_next=keep))
    return replace(doc, paragraphs=tuple(paras))


def test_tbl08_caption_keep_next():
    doc = build(ROWS)
    assert run(Tbl08KeepNext(), with_caption_keep(doc, V(True))).outcome == "passed"
    (f,) = run(Tbl08KeepNext(), with_caption_keep(doc, None)).findings
    assert f.level == "violation" and f.fingerprint == "TBL-08|1|caption"
    (f,) = run(Tbl08KeepNext(), with_caption_keep(doc, V(False))).findings
    assert f.level == "violation"


def test_tbl08_long_table_rows_with_keep_next_is_suspicion():
    rows = [["a", "b"]] + [[str(i), "x"] for i in range(20)]
    formats = {(r, 1): fmt(align=V("left"), keep_next=V(True)) for r in range(4, 9)}
    doc = with_caption_keep(build(rows, formats), V(True))
    (f,) = run(Tbl08KeepNext(), doc).findings
    assert f.level == "suspicion" and f.fingerprint == "TBL-08|1|rows"
    assert f.values["rows"] == [4, 5, 6, 7, 8]
    short = with_caption_keep(build(rows[:5], {(4, 1): fmt(keep_next=V(True))}), V(True))
    assert run(Tbl08KeepNext(), short).outcome == "passed"


# --- TBL-09 -------------------------------------------------------------------------------
def test_tbl09_missing_style():
    assert run(Tbl09MissingStyle(), build(ROWS)).outcome == "passed"
    (f,) = run(Tbl09MissingStyle(), build(ROWS, style_id="Ghost", style_exists=False)).findings
    assert f.level == "violation" and "Ghost" in f.message


# --- needs ---------------------------------------------------------------------------------
def test_no_tables_gives_not_run():
    doc = DocBuilder().build()
    assert run(Tbl01Indents(), doc).outcome == "not_run"
