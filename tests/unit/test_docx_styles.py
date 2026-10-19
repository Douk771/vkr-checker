"""XML-юнит-тесты каждой ветки каскада форматирования (B-13)."""
# ruff: noqa: E501

import pytest

from vkr_checker.docx.styles import (
    StyleSheet,
    TableContext,
    TableLook,
    parse_cnf,
    parse_tbl_look,
)
from vkr_checker.docx.xmlutil import NS, parse_xml

NSDECL = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items() if k in ("w", "r"))


def x(inner: str, tag: str):
    return parse_xml(f"<{tag} {NSDECL}>{inner}</{tag}>".encode())


def sheet(inner: str, defaults: str = "") -> StyleSheet:
    dd = f"<w:docDefaults>{defaults}</w:docDefaults>" if defaults else ""
    return StyleSheet(x(dd + inner, "w:styles"))


def para(ppr: str = "", style: str | None = None):
    ps = f'<w:pStyle w:val="{style}"/>' if style else ""
    return x(f"<w:pPr>{ps}{ppr}</w:pPr>", "w:p")


NORMAL = '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>{}</w:style>'
TBL_DEFAULT = '<w:style w:type="table" w:default="1" w:styleId="TableNormal"/>'


def table_style(sid: str, body: str, based: str | None = None) -> str:
    b = f'<w:basedOn w:val="{based}"/>' if based else ""
    return f'<w:style w:type="table" w:styleId="{sid}">{b}{body}</w:style>'


def cond(kind: str, ppr: str = "", rpr: str = "", tcpr: str = "") -> str:
    return (
        f'<w:tblStylePr w:type="{kind}"><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr>'
        f"<w:tcPr>{tcpr}</w:tcPr></w:tblStylePr>"
    )


def ctx(style="TS", row=1, col=1, n_rows=4, n_cols=3, look=None, **kw):
    look = look if look is not None else TableLook(first_row=True, first_col=True)
    return TableContext(style, row, col, n_rows, n_cols, look=look, **kw)


# --- слои --------------------------------------------------------------------------------
def test_defaults_then_para_style_then_direct_with_origins():
    s = sheet(
        NORMAL.format('<w:pPr><w:spacing w:after="160" w:line="259" w:lineRule="auto"/></w:pPr>'),
        defaults='<w:pPrDefault><w:pPr><w:spacing w:after="0"/><w:jc w:val="left"/></w:pPr></w:pPrDefault>',
    )
    f = s.resolve_paragraph(para()).fmt
    assert (f.space_after_pt.value, f.space_after_pt.origin) == (8.0, "para_style")
    assert f.align.origin == "defaults" and f.align.value == "left"
    f = s.resolve_paragraph(para('<w:spacing w:after="0"/><w:jc w:val="both"/>')).fmt
    assert (f.space_after_pt.value, f.space_after_pt.origin) == (0.0, "direct")
    assert f.align.value == "justify"
    assert f.line_spacing.origin == "para_style"


def test_unset_property_is_none():
    f = sheet(NORMAL.format("")).resolve_paragraph(para()).fmt
    assert f.first_line_cm is None and f.left_cm is None and f.line_spacing is None


def test_basedon_chain_root_to_leaf():
    s = sheet(
        NORMAL.format('<w:pPr><w:ind w:left="567"/><w:jc w:val="center"/></w:pPr>')
        + '<w:style w:type="paragraph" w:styleId="A"><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:jc w:val="right"/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="B"><w:basedOn w:val="A"/>'
        '<w:pPr><w:ind w:left="1134"/></w:pPr></w:style>'
    )
    f = s.resolve_paragraph(para(style="B")).fmt
    assert f.left_cm.value == pytest.approx(2.0, abs=0.01)
    assert f.align.value == "right"


def test_basedon_cycle_and_missing_do_not_hang():
    s = sheet(
        '<w:style w:type="paragraph" w:styleId="A"><w:basedOn w:val="B"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="B"><w:basedOn w:val="A"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="C"><w:basedOn w:val="Nope"/>'
        '<w:pPr><w:jc w:val="center"/></w:pPr></w:style>'
    )
    s.resolve_paragraph(para(style="A"))
    assert s.resolve_paragraph(para(style="C")).fmt.align.value == "center"


def test_missing_style_falls_back_to_default():
    s = sheet(NORMAL.format('<w:pPr><w:jc w:val="center"/></w:pPr>'))
    assert not s.style_exists("Ghost")
    assert s.resolve_paragraph(para(style="Ghost")).fmt.align.value == "center"


# --- отступы ------------------------------------------------------------------------------
def test_first_line_and_hanging_exclusive_across_layers():
    s = sheet(NORMAL.format('<w:pPr><w:ind w:hanging="567"/></w:pPr>'))
    f = s.resolve_paragraph(para()).fmt
    assert f.hanging_cm.value == pytest.approx(1.0, abs=0.01) and f.first_line_cm.value == 0
    f = s.resolve_paragraph(para('<w:ind w:firstLine="709"/>')).fmt
    assert f.first_line_cm.value == pytest.approx(1.25, abs=0.01)
    assert f.hanging_cm.value == 0 and f.first_line_cm.origin == "direct"


def test_explicit_zero_first_line_overrides_style_hanging():
    s = sheet(NORMAL.format('<w:pPr><w:ind w:hanging="567"/></w:pPr>'))
    f = s.resolve_paragraph(para('<w:ind w:firstLine="0"/>')).fmt
    assert f.first_line_cm.value == 0 and f.hanging_cm.value == 0


def test_hanging_wins_over_first_line_in_same_element():
    f = sheet("").resolve_paragraph(para('<w:ind w:firstLine="100" w:hanging="300"/>')).fmt
    assert f.hanging_cm.value > 0 and f.first_line_cm.value == 0


def test_start_end_synonyms():
    f = sheet("").resolve_paragraph(para('<w:ind w:start="567" w:end="283"/>')).fmt
    assert f.left_cm.value == pytest.approx(1.0, abs=0.01)
    assert f.right_cm.value == pytest.approx(0.5, abs=0.01)


def test_first_line_chars_use_font_size_and_override_twips():
    s = sheet(
        NORMAL.format(""),
        defaults='<w:rPrDefault><w:rPr><w:sz w:val="28"/></w:rPr></w:rPrDefault>',
    )
    f = s.resolve_paragraph(para('<w:ind w:firstLine="1" w:firstLineChars="200"/>'))
    # 2 знака по 14 pt = 28 pt = 0.988 см
    assert f.fmt.first_line_cm.value == pytest.approx(28 * 2.54 / 72, abs=0.01)
    assert f.font_size_pt == 14


def test_numbering_indent_between_style_and_direct():
    s = sheet(NORMAL.format('<w:pPr><w:ind w:left="0"/></w:pPr>'))
    num = x('<w:ind w:left="720" w:hanging="360"/>', "w:pPr")
    f = s.resolve_paragraph(para(), numbering_ppr=num).fmt
    assert f.left_cm.value == pytest.approx(1.27, abs=0.01)
    f = s.resolve_paragraph(para('<w:ind w:left="0"/>'), numbering_ppr=num).fmt
    assert f.left_cm.value == 0


# --- интервалы ----------------------------------------------------------------------------
def test_line_rules():
    s = sheet("")
    f = s.resolve_paragraph(para('<w:spacing w:line="360" w:lineRule="auto"/>')).fmt
    assert f.line_spacing.value == 1.5 and f.line_rule.value == "auto"
    f = s.resolve_paragraph(para('<w:spacing w:line="300" w:lineRule="exact"/>')).fmt
    assert f.line_spacing.value == 15.0 and f.line_rule.value == "exact"
    f = s.resolve_paragraph(para('<w:spacing w:line="240"/>')).fmt
    assert f.line_rule.value == "auto"


def test_rule_only_overrides_rule_keeps_style_line():
    s = sheet(NORMAL.format('<w:pPr><w:spacing w:line="240" w:lineRule="auto"/></w:pPr>'))
    f = s.resolve_paragraph(para('<w:spacing w:after="0"/>')).fmt
    assert f.line_spacing.value == 1.0 and f.space_after_pt.value == 0


def test_autospacing_and_lines():
    f = (
        sheet("")
        .resolve_paragraph(
            para(
                '<w:spacing w:before="100" w:beforeAutospacing="1" w:after="200" w:afterAutospacing="0"/>'
            )
        )
        .fmt
    )
    assert f.space_before_pt.value == "auto" and f.space_after_pt.value == 10.0
    f = sheet("").resolve_paragraph(para('<w:spacing w:afterLines="100"/>')).fmt
    assert f.space_after_pt.value == 10.0  # 1 строка при 10 pt


def test_contextual_spacing_flag():
    s = sheet(NORMAL.format("<w:pPr><w:contextualSpacing/></w:pPr>"))
    assert s.resolve_paragraph(para()).contextual_spacing
    assert not s.resolve_paragraph(para('<w:contextualSpacing w:val="0"/>')).contextual_spacing


def test_toggles_keep_next_off():
    s = sheet(NORMAL.format("<w:pPr><w:keepNext/></w:pPr>"))
    assert s.resolve_paragraph(para()).fmt.keep_next.value is True
    assert s.resolve_paragraph(para('<w:keepNext w:val="false"/>')).fmt.keep_next.value is False


def test_pprchange_ignored():
    p = para(
        '<w:jc w:val="left"/><w:pPrChange w:id="1"><w:pPr><w:jc w:val="right"/></w:pPr></w:pPrChange>'
    )
    assert sheet("").resolve_paragraph(p).fmt.align.value == "left"


# --- стили таблиц -------------------------------------------------------------------------
def test_table_style_base_sits_between_defaults_and_para_style():
    s = sheet(
        NORMAL.format("")
        + table_style("TS", '<w:pPr><w:spacing w:after="0"/><w:ind w:firstLine="709"/></w:pPr>')
    )
    f = s.resolve_paragraph(para(), table=ctx()).fmt
    assert f.space_after_pt.origin == "table_style" and f.first_line_cm.origin == "table_style"
    s2 = sheet(
        NORMAL.format('<w:pPr><w:ind w:firstLine="0"/></w:pPr>')
        + table_style("TS", '<w:pPr><w:ind w:firstLine="709"/></w:pPr>')
    )
    f = s2.resolve_paragraph(para(), table=ctx()).fmt
    assert f.first_line_cm.value == 0 and f.first_line_cm.origin == "para_style"


def test_table_style_basedon_chain():
    s = sheet(
        NORMAL.format("")
        + table_style("Base", '<w:pPr><w:jc w:val="center"/><w:spacing w:after="120"/></w:pPr>')
        + table_style("TS", '<w:pPr><w:spacing w:after="0"/></w:pPr>', based="Base")
    )
    f = s.resolve_paragraph(para(), table=ctx()).fmt
    assert f.align.value == "center" and f.space_after_pt.value == 0


def test_default_table_style_when_none_given():
    s = sheet(
        NORMAL.format("") + '<w:style w:type="table" w:default="1" w:styleId="TableNormal">'
        '<w:pPr><w:spacing w:after="0"/></w:pPr></w:style>'
    )
    f = s.resolve_paragraph(para(), table=ctx(style=None)).fmt
    assert f.space_after_pt.value == 0


def test_whole_table_condition_after_base():
    s = sheet(
        NORMAL.format("")
        + table_style(
            "TS",
            '<w:pPr><w:jc w:val="left"/></w:pPr>' + cond("wholeTable", '<w:jc w:val="right"/>'),
        )
    )
    assert s.resolve_paragraph(para(), table=ctx()).fmt.align.value == "right"


def test_first_row_condition_only_for_header_row_and_with_look():
    body = cond("firstRow", '<w:jc w:val="center"/>')
    s = sheet(NORMAL.format("") + table_style("TS", body))
    assert s.resolve_paragraph(para(), table=ctx(row=0)).fmt.align.value == "center"
    assert s.resolve_paragraph(para(), table=ctx(row=1)).fmt.align is None
    off = ctx(row=0, look=TableLook(first_row=False))
    assert s.resolve_paragraph(para(), table=off).fmt.align is None


def test_last_row_first_col_last_col():
    body = (
        cond("lastRow", '<w:jc w:val="right"/>')
        + cond("firstCol", '<w:spacing w:after="40"/>')
        + cond("lastCol", '<w:spacing w:after="80"/>')
    )
    s = sheet(NORMAL.format("") + table_style("TS", body))
    look = TableLook(first_row=True, last_row=True, first_col=True, last_col=True)
    assert (
        s.resolve_paragraph(para(), table=ctx(row=3, col=1, look=look)).fmt.align.value == "right"
    )
    assert (
        s.resolve_paragraph(para(), table=ctx(row=1, col=0, look=look)).fmt.space_after_pt.value
        == 2
    )
    assert (
        s.resolve_paragraph(para(), table=ctx(row=1, col=2, look=look)).fmt.space_after_pt.value
        == 4
    )


def test_banded_rows_skip_header_and_alternate():
    body = cond("band1Horz", '<w:jc w:val="left"/>') + cond("band2Horz", '<w:jc w:val="right"/>')
    s = sheet(NORMAL.format("") + table_style("TS", body))
    look = TableLook(first_row=True)
    assert s.resolve_paragraph(para(), table=ctx(row=0, look=look)).fmt.align is None
    assert s.resolve_paragraph(para(), table=ctx(row=1, look=look)).fmt.align.value == "left"
    assert s.resolve_paragraph(para(), table=ctx(row=2, look=look)).fmt.align.value == "right"
    no_band = TableLook(first_row=True, no_hband=True)
    assert s.resolve_paragraph(para(), table=ctx(row=1, look=no_band)).fmt.align is None


def test_banded_columns_and_band_size():
    body = cond("band1Vert", '<w:jc w:val="left"/>') + cond("band2Vert", '<w:jc w:val="right"/>')
    s = sheet(NORMAL.format("") + table_style("TS", body))
    look = TableLook(no_hband=True)
    assert s.resolve_paragraph(para(), table=ctx(col=0, look=look)).fmt.align.value == "left"
    assert s.resolve_paragraph(para(), table=ctx(col=1, look=look)).fmt.align.value == "right"
    sized = ctx(col=1, look=look, col_band_size=2)
    assert s.resolve_paragraph(para(), table=sized).fmt.align.value == "left"


def test_corner_overrides_row_and_column_conditions():
    body = (
        cond("firstRow", '<w:jc w:val="center"/>')
        + cond("firstCol", '<w:jc w:val="right"/>')
        + cond("nwCell", '<w:jc w:val="left"/>')
    )
    s = sheet(NORMAL.format("") + table_style("TS", body))
    assert s.resolve_paragraph(para(), table=ctx(row=0, col=0)).fmt.align.value == "left"
    # первая строка в порядке после первого столбца: для не угловой ячейки строки действует firstRow
    assert s.resolve_paragraph(para(), table=ctx(row=0, col=1)).fmt.align.value == "center"


def test_condition_order_first_row_beats_first_col():
    body = cond("firstRow", '<w:jc w:val="center"/>') + cond("firstCol", '<w:jc w:val="right"/>')
    s = sheet(NORMAL.format("") + table_style("TS", body))
    assert s.resolve_paragraph(para(), table=ctx(row=0, col=0)).fmt.align.value == "center"


def test_conditions_from_base_style_chain():
    s = sheet(
        NORMAL.format("")
        + table_style("Base", cond("firstRow", '<w:jc w:val="center"/>'))
        + table_style("TS", cond("firstRow", '<w:spacing w:after="0"/>'), based="Base")
    )
    f = s.resolve_paragraph(para(), table=ctx(row=0)).fmt
    assert f.align.value == "center" and f.space_after_pt.value == 0


def test_para_style_and_direct_beat_conditional_table_style():
    body = cond("firstRow", '<w:jc w:val="center"/>')
    s = sheet(NORMAL.format('<w:pPr><w:jc w:val="left"/></w:pPr>') + table_style("TS", body))
    assert s.resolve_paragraph(para(), table=ctx(row=0)).fmt.align.origin == "para_style"
    assert (
        s.resolve_paragraph(para('<w:jc w:val="right"/>'), table=ctx(row=0)).fmt.align.origin
        == "direct"
    )


def test_cnf_style_used_when_tbl_look_missing():
    body = cond("firstRow", '<w:jc w:val="center"/>')
    s = sheet(NORMAL.format("") + table_style("TS", body))
    cell = x('<w:cnfStyle w:firstRow="1"/>', "w:tcPr")
    cnf = parse_cnf(cell)
    assert cnf == frozenset({"firstRow"})
    c = TableContext("TS", 0, 0, 3, 3, look=None, cnf=cnf)
    assert s.resolve_paragraph(para(), table=c).fmt.align.value == "center"
    c2 = TableContext("TS", 1, 0, 3, 3, look=None, cnf=frozenset())
    assert s.resolve_paragraph(para(), table=c2).fmt.align is None


def test_cnf_bitmask():
    cnf = parse_cnf(x('<w:cnfStyle w:val="100000000000"/>', "w:trPr"))
    assert cnf == frozenset({"firstRow"})
    assert parse_cnf(None, x("", "w:trPr")) is None


def test_tbl_look_bitmask_and_attributes():
    assert parse_tbl_look(x('<w:tblLook w:val="04A0"/>', "w:tblPr")) == TableLook(
        first_row=True, first_col=True, no_vband=True
    )
    look = parse_tbl_look(x('<w:tblLook w:val="0000" w:firstRow="1" w:noHBand="0"/>', "w:tblPr"))
    assert look.first_row and not look.no_hband
    assert parse_tbl_look(x("", "w:tblPr")) is None


def test_cell_valign_from_tcpr_and_conditional_style():
    s = sheet(
        NORMAL.format("") + table_style("TS", cond("firstRow", tcpr='<w:vAlign w:val="center"/>'))
    )
    f = s.resolve_paragraph(para(), table=ctx(row=0)).fmt
    assert f.v_align.value == "center"
    tc = x('<w:vAlign w:val="bottom"/>', "w:tcPr")
    f = s.resolve_paragraph(para(), table=ctx(row=0, tc_pr=tc)).fmt
    assert f.v_align.value == "bottom"


def test_cache_does_not_leak_direct_formatting():
    s = sheet(NORMAL.format("") + table_style("TS", cond("firstRow", '<w:jc w:val="center"/>')))
    s.resolve_paragraph(para('<w:jc w:val="right"/>'), table=ctx(row=0))
    assert s.resolve_paragraph(para(), table=ctx(row=0)).fmt.align.value == "center"


# --- outline, run ---------------------------------------------------------------------------
def test_outline_level():
    s = sheet(
        NORMAL.format("") + '<w:style w:type="paragraph" w:styleId="H1"><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>'
    )
    assert s.resolve_paragraph(para(style="H1")).outline_level == 0
    assert s.resolve_paragraph(para()).outline_level is None


def run(rpr=""):
    return x(f"<w:rPr>{rpr}</w:rPr><w:t>x</w:t>", "w:r")


def test_run_props_size_font_bold_cascade():
    s = sheet(
        NORMAL.format('<w:rPr><w:sz w:val="28"/><w:rFonts w:ascii="Times New Roman"/></w:rPr>')
        + '<w:style w:type="character" w:styleId="Strong"><w:rPr><w:b/></w:rPr></w:style>'
    )
    base = s.resolve_paragraph(para())
    rp = s.resolve_run(run(), base)
    assert (rp.size_pt, rp.font, rp.bold, rp.italic) == (14.0, "Times New Roman", False, False)
    assert s.resolve_run(run('<w:rStyle w:val="Strong"/>'), base).bold
    assert s.resolve_run(run('<w:sz w:val="24"/><w:i/>'), base).size_pt == 12.0
    assert s.resolve_run(run('<w:rStyle w:val="Strong"/><w:b w:val="0"/>'), base).bold is False


def test_toggle_xor_between_para_and_char_style():
    s = sheet(
        NORMAL.format("")
        + '<w:style w:type="paragraph" w:styleId="Bold"><w:rPr><w:b/></w:rPr></w:style>'
        '<w:style w:type="character" w:styleId="Strong"><w:rPr><w:b/></w:rPr></w:style>'
    )
    base = s.resolve_paragraph(para(style="Bold"))
    assert s.resolve_run(run(), base).bold
    assert not s.resolve_run(run('<w:rStyle w:val="Strong"/>'), base).bold
