from lxml import etree

from vkr_checker.docx.fields import FieldParser, field_kind, parse_paragraph, stale_seq_paragraphs
from vkr_checker.docx.revisions import (
    accepted_text,
    is_paragraph_removed,
    paragraph_mark_deleted,
    row_deleted,
)
from vkr_checker.docx.xmlutil import NS, parse_xml

NSDECL = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items() if k in ("w", "mc", "r"))


def el(inner: str, tag="w:p"):
    return parse_xml(f"<{tag} {NSDECL}>{inner}</{tag}>".encode())


def r(t):
    return f"<w:r><w:t>{t}</w:t></w:r>"


def fld(instr, result):
    return (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f"<w:r><w:instrText> {instr} </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f"{r(result)}"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


def test_insertions_taken_deletions_dropped():
    p = el(
        r("А ")
        + '<w:ins w:id="1"><w:r><w:t>вставка </w:t></w:r></w:ins>'
        + '<w:del w:id="2"><w:r><w:delText>удалено </w:delText></w:r></w:del>'
        + '<w:moveTo w:id="3"><w:r><w:t>перенос</w:t></w:r></w:moveTo>'
        + '<w:moveFrom w:id="4"><w:r><w:t>ушло</w:t></w:r></w:moveFrom>'
    )
    assert accepted_text(p) == "А вставка перенос"


def test_delText_never_leaks_even_outside_del():
    assert accepted_text(el("<w:r><w:delText>x</w:delText><w:t>y</w:t></w:r>")) == "y"


def test_format_change_ignored_and_comments_skipped():
    p = el(
        '<w:pPr><w:pPrChange w:id="1"><w:pPr/></w:pPrChange></w:pPr>'
        '<w:commentRangeStart w:id="0"/>' + r("текст")
        + '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r>'
    )  # fmt: skip
    assert accepted_text(p) == "текст"


def test_hyperlink_sdt_and_alternate_content():
    p = el(
        "<w:hyperlink>" + r("ссылка ") + "</w:hyperlink>"
        "<w:sdt><w:sdtContent>" + r("поле ") + "</w:sdtContent></w:sdt>"
        "<mc:AlternateContent><mc:Choice>" + r("выбор") + "</mc:Choice>"
        "<mc:Fallback>" + r("запасной") + "</mc:Fallback></mc:AlternateContent>"
    )
    assert accepted_text(p) == "ссылка поле выбор"


def test_tab_and_breaks():
    p = el('<w:r><w:t>a</w:t><w:tab/><w:t>b</w:t><w:br/><w:br w:type="page"/></w:r>')
    assert accepted_text(p) == "a\tb\n"


def test_paragraph_removed_when_mark_deleted_and_empty():
    removed = el(
        '<w:pPr><w:rPr><w:del w:id="1"/></w:rPr></w:pPr>'
        '<w:del w:id="2"><w:r><w:delText>x</w:delText></w:r></w:del>'
    )
    merged = el('<w:pPr><w:rPr><w:del w:id="1"/></w:rPr></w:pPr>' + r("остался"))
    assert paragraph_mark_deleted(removed) and is_paragraph_removed(removed)
    assert paragraph_mark_deleted(merged) and not is_paragraph_removed(merged)
    assert not is_paragraph_removed(el(r("обычный")))


def test_row_deleted():
    assert row_deleted(el('<w:trPr><w:del w:id="1"/></w:trPr>', "w:tr"))
    assert not row_deleted(el("<w:trPr/>", "w:tr"))


def test_fldsimple_result_in_text():
    p = el('<w:fldSimple w:instr=" SEQ Таблица \\* ARABIC ">' + r("3") + "</w:fldSimple>")
    c = parse_paragraph(p, 5)
    assert c.text == "3"
    assert [(f.kind, f.result, f.paragraph_idx) for f in c.fields] == [("SEQ", "3", 5)]
    assert c.fields[0].instruction == "SEQ Таблица \\* ARABIC"


def test_complex_field_text_is_result_not_instruction():
    p = el(r("Таблица ") + fld("SEQ Таблица \\* ARABIC", "2") + r(" - Данные"))
    c = parse_paragraph(p, 1)
    assert c.text == "Таблица 2 - Данные"
    assert c.fields[0].kind == "SEQ" and c.fields[0].result == "2"
    assert "SEQ" not in c.text


def test_nested_fields():
    inner = fld("PAGEREF _Toc1 \\h", "7")
    outer = (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> HYPERLINK \\l _Toc1 </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        + r("Введение ") + inner
        + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )  # fmt: skip
    c = parse_paragraph(el(outer), 1)
    assert c.text == "Введение 7"
    assert sorted(f.kind for f in c.fields) == ["HYPERLINK", "PAGEREF"]
    outer_f = next(f for f in c.fields if f.kind == "HYPERLINK")
    assert outer_f.result == "Введение 7"


def test_field_spanning_paragraphs_keeps_state():
    begin = (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText> TOC \\o "1-3" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + r("Введение 3")
    )
    end = r("Глава 1 10") + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    parser = FieldParser()
    c1 = parser.feed_paragraph(el(begin), 10)
    assert c1.text == "Введение 3" and c1.fields == [] and parser.open_fields == 1
    c2 = parser.feed_paragraph(el(end), 11)
    assert c2.text == "Глава 1 10" and parser.open_fields == 0
    toc = c2.fields[0]
    assert toc.kind == "TOC" and toc.paragraph_idx == 10
    assert "Введение 3" in toc.result and "Глава 1 10" in toc.result


def test_deleted_field_run_ignored():
    p = el('<w:del w:id="1">' + fld("SEQ Рисунок", "9") + "</w:del>" + r("x"))
    c = parse_paragraph(p, 1)
    assert c.text == "x" and c.fields == []


def test_field_kind():
    assert field_kind("  REF _Ref123 \\h") == "REF"
    assert field_kind("") == ""


def test_stale_seq_duplicates_detected():
    def mk(idx, res, instr="SEQ Таблица \\* ARABIC"):
        c = parse_paragraph(el(fld(instr, res)), idx)
        return c.fields[0]

    fields = [mk(1, "1"), mk(5, "2"), mk(9, "2"), mk(12, "3")]
    assert stale_seq_paragraphs(fields) == {9}


def test_stale_seq_other_sequences_and_resets_not_flagged():
    def mk(idx, res, instr):
        return parse_paragraph(el(fld(instr, res)), idx).fields[0]

    ok = [
        mk(1, "1", "SEQ Таблица"),
        mk(2, "1", "SEQ Рисунок"),
        mk(3, "1", "SEQ Таблица \\r 1"),
        mk(4, "1", "SEQ Рисунок \\s 1"),
        mk(5, "1", "SEQ Рисунок \\s 1"),
    ]
    assert stale_seq_paragraphs(ok) == set()


def test_xml_is_lxml_element():
    assert isinstance(el(""), etree._Element)
