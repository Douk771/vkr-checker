# ruff: noqa: E501
from vkr_checker.docx.numbering import NumberingResolver, format_number
from vkr_checker.docx.styles import StyleSheet
from vkr_checker.docx.xmlutil import NS, parse_xml

NSDECL = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items() if k in ("w", "r"))


def x(inner, tag):
    return parse_xml(f"<{tag} {NSDECL}>{inner}</{tag}>".encode())


def lvl(i, fmt="decimal", text=None, start=1, extra=""):
    text = text if text is not None else f"%{i + 1}."
    return (
        f'<w:lvl w:ilvl="{i}"><w:start w:val="{start}"/><w:numFmt w:val="{fmt}"/>'
        f'{extra}<w:lvlText w:val="{text}"/></w:lvl>'
    )


def abstract(aid, *levels, extra=""):
    return f'<w:abstractNum w:abstractNumId="{aid}">{extra}{"".join(levels)}</w:abstractNum>'


def num(nid, aid, over=""):
    return f'<w:num w:numId="{nid}"><w:abstractNumId w:val="{aid}"/>{over}</w:num>'


def resolver(inner, styles=None):
    return NumberingResolver(x(inner, "w:numbering"), styles)


def ppr(num_id=None, ilvl=None, style=None):
    parts = ""
    if style:
        parts += f'<w:pStyle w:val="{style}"/>'
    if num_id is not None or ilvl is not None:
        n = f'<w:numId w:val="{num_id}"/>' if num_id is not None else ""
        i = f'<w:ilvl w:val="{ilvl}"/>' if ilvl is not None else ""
        parts += f"<w:numPr>{i}{n}</w:numPr>"
    return x(parts, "w:pPr")


def labels(r, *items):
    return [getattr(r.label(p), "label", "NONE") for p in items]


def test_format_number_variants():
    assert format_number(3, "russianLower") == "в"
    assert format_number(29, "russianLower") == "аа"
    assert format_number(27, "lowerLetter") == "aa"
    assert format_number(4, "upperRoman") == "IV"
    assert format_number(1994, "lowerRoman") == "mcmxciv"
    assert format_number(5, "decimalZero") == "05"


def test_simple_decimal_list():
    r = resolver(abstract(0, lvl(0)) + num(1, 0))
    assert labels(r, *[ppr(1, 0)] * 3) == ["1.", "2.", "3."]


def test_multilevel_with_reset_of_deeper_levels():
    r = resolver(abstract(0, lvl(0, text="%1."), lvl(1, text="%1.%2.")) + num(1, 0))
    seq = [ppr(1, 0), ppr(1, 1), ppr(1, 1), ppr(1, 0), ppr(1, 1)]
    assert labels(r, *seq) == ["1.", "1.1.", "1.2.", "2.", "2.1."]


def test_lvl_restart_zero_never_resets():
    r = resolver(
        abstract(0, lvl(0), lvl(1, text="%2)", extra='<w:lvlRestart w:val="0"/>')) + num(1, 0)
    )
    assert labels(r, ppr(1, 0), ppr(1, 1), ppr(1, 0), ppr(1, 1)) == ["1.", "1)", "2.", "2)"]


def test_lvl_restart_after_specific_level():
    levels = (
        lvl(0),
        lvl(1, text="%2."),
        lvl(2, text="%3.", extra='<w:lvlRestart w:val="2"/>'),
    )
    r = resolver(abstract(0, *levels) + num(1, 0))
    # уровень 3 перезапускается только при приросте уровня 2, но не уровня 1
    got = labels(r, ppr(1, 0), ppr(1, 1), ppr(1, 2), ppr(1, 2), ppr(1, 1), ppr(1, 2))
    assert got == ["1.", "1.", "1.", "2.", "2.", "1."]


def test_two_numids_same_abstract_continue_count():
    r = resolver(abstract(0, lvl(0)) + num(1, 0) + num(2, 0))
    assert labels(r, ppr(1, 0), ppr(2, 0), ppr(1, 0)) == ["1.", "2.", "3."]


def test_start_override_restarts_once():
    over = '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>'
    r = resolver(abstract(0, lvl(0)) + num(1, 0) + num(2, 0, over))
    assert labels(r, ppr(1, 0), ppr(1, 0), ppr(2, 0), ppr(2, 0)) == ["1.", "2.", "1.", "2."]


def test_lvl_override_replaces_definition():
    over = '<w:lvlOverride w:ilvl="0">' + lvl(0, "upperRoman", "%1)") + "</w:lvlOverride>"
    r = resolver(abstract(0, lvl(0)) + num(1, 0, over))
    assert labels(r, ppr(1, 0), ppr(1, 0)) == ["I)", "II)"]


def test_start_value_and_russian_letters():
    r = resolver(abstract(0, lvl(0, "russianLower", "%1)", start=2)) + num(1, 0))
    assert labels(r, ppr(1, 0), ppr(1, 0)) == ["б)", "в)"]


def test_bullet_has_no_label_but_is_list_item():
    r = resolver(abstract(0, lvl(0, "bullet", "•")) + num(1, 0))
    res = r.label(ppr(1, 0))
    assert res.label is None and res.is_list_item


def test_numfmt_none_not_list_item():
    r = resolver(abstract(0, lvl(0, "none", "")) + num(1, 0))
    res = r.label(ppr(1, 0))
    assert res.label is None and not res.is_list_item


def test_num_id_zero_and_no_numpr():
    r = resolver(abstract(0, lvl(0)) + num(1, 0))
    assert r.label(ppr(0, 0)) is None
    assert r.label(x("", "w:pPr")) is None
    assert r.label(None) is None


def test_islgl_forces_decimal_for_referenced_levels():
    r = resolver(
        abstract(0, lvl(0, "upperRoman", "%1."), lvl(1, "decimal", "%1.%2", extra="<w:isLgl/>"))
        + num(1, 0)
    )
    assert labels(r, ppr(1, 0), ppr(1, 1)) == ["I.", "1.1"]


def test_unreached_parent_level_uses_start():
    r = resolver(abstract(0, lvl(0, text="%1."), lvl(1, text="%1.%2")) + num(1, 0))
    assert labels(r, ppr(1, 1)) == ["1.1"]


def styles_with_numpr(num_id, ilvl=None, sid="Heading1"):
    lv = f'<w:ilvl w:val="{ilvl}"/>' if ilvl is not None else ""
    return StyleSheet(
        x(
            f'<w:style w:type="paragraph" w:styleId="{sid}"><w:pPr><w:numPr>{lv}'
            f'<w:numId w:val="{num_id}"/></w:numPr></w:pPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="H1b"><w:basedOn w:val="Heading1"/></w:style>',
            "w:styles",
        )
    )


def test_numbering_from_style_and_inherited_style():
    r = resolver(abstract(0, lvl(0, text="Глава %1")) + num(5, 0), styles_with_numpr(5))
    assert labels(r, ppr(style="Heading1"), ppr(style="H1b")) == ["Глава 1", "Глава 2"]


def test_style_numpr_without_ilvl_uses_lvl_pstyle_link():
    levels = (lvl(0), lvl(1, text="%1.%2", extra='<w:pStyle w:val="Heading2"/>'))
    r = resolver(abstract(0, *levels) + num(5, 0), styles_with_numpr(5, None, "Heading2"))
    res = r.label(ppr(style="Heading2"))
    assert res.ilvl == 1 and res.label == "1.1"


def test_direct_numid_zero_cancels_style_numbering():
    r = resolver(abstract(0, lvl(0)) + num(5, 0), styles_with_numpr(5))
    assert r.label(ppr(0, 0, style="Heading1")) is None


def test_direct_ilvl_overrides_style_level():
    levels = (lvl(0), lvl(1, text="%1.%2"))
    r = resolver(abstract(0, *levels) + num(5, 0), styles_with_numpr(5, 0))
    assert r.label(ppr(None, 1, style="Heading1")).label == "1.1"


def test_numstylelink_resolves_to_linked_style_list():
    link = abstract(0, extra='<w:numStyleLink w:val="ListStyle"/>')
    real = abstract(1, lvl(0, "decimal", "%1)"))
    r = resolver(link + real + num(1, 0) + num(2, 1), styles_with_numpr(2, None, "ListStyle"))
    assert labels(r, ppr(1, 0), ppr(1, 0)) == ["1)", "2)"]


def test_missing_definitions_warn_not_crash():
    r = resolver(abstract(0, lvl(0)) + num(1, 0))
    assert r.label(ppr(99, 0)) is None
    assert any("99" in w for w in r.warnings)
    r.label(ppr(1, 4))
    assert any("уровень 4" in w for w in r.warnings)


def test_unknown_format_and_legacy_warn():
    r = resolver(abstract(0, lvl(0, "ordinal", extra="<w:legacy/>")) + num(1, 0))
    assert r.label(ppr(1, 0)).label == "1."
    assert len(r.warnings) == 2


def test_level_ppr_exposed_for_indents():
    levels = '<w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl>'
    r = resolver(abstract(0, levels) + num(1, 0))
    assert r.label(ppr(1, 0)).level_ppr is not None


def test_no_numbering_part():
    assert NumberingResolver(None).label(ppr(1, 0)) is None
