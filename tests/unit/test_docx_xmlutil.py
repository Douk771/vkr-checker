import pytest

from vkr_checker.docx.xmlutil import (
    W_P,
    W_TBL,
    XmlParseError,
    iter_body_blocks,
    iter_descendants,
    parse_xml,
    qn,
    textbox_paragraphs,
)

NSDECL = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml"'
)


def body(inner):
    return parse_xml(f"<w:body {NSDECL}>{inner}</w:body>".encode())


def texts(blocks):
    return [
        "".join(t.text or "" for t in b.iter(qn("w:t"))) if b.tag == W_P else "<tbl>"
        for b in blocks
    ]


def test_body_order_with_tables():
    b = body("<w:p><w:r><w:t>a</w:t></w:r></w:p><w:tbl/><w:p><w:r><w:t>b</w:t></w:r></w:p>")
    assert texts(iter_body_blocks(b)) == ["a", "<tbl>", "b"]


def test_sdt_content_is_expanded_including_nested():
    b = body(
        "<w:p><w:r><w:t>1</w:t></w:r></w:p>"
        "<w:sdt><w:sdtContent><w:p><w:r><w:t>toc</w:t></w:r></w:p>"
        "<w:sdt><w:sdtContent><w:p><w:r><w:t>deep</w:t></w:r></w:p></w:sdtContent></w:sdt>"
        "</w:sdtContent></w:sdt><w:p><w:r><w:t>2</w:t></w:r></w:p>"
    )
    assert texts(iter_body_blocks(b)) == ["1", "toc", "deep", "2"]


def test_block_level_alternate_content_takes_choice_only():
    b = body(
        "<mc:AlternateContent><mc:Choice><w:p><w:r><w:t>new</w:t></w:r></w:p></mc:Choice>"
        "<mc:Fallback><w:p><w:r><w:t>old</w:t></w:r></w:p></mc:Fallback></mc:AlternateContent>"
    )
    assert texts(iter_body_blocks(b)) == ["new"]


def test_run_level_alternate_content_has_no_double_counting():
    p = body(
        "<w:p><w:r><mc:AlternateContent>"
        "<mc:Choice><w:drawing/></mc:Choice><mc:Fallback><w:pict/></mc:Fallback>"
        "</mc:AlternateContent></w:r></w:p>"
    )[0]
    tags = [d.tag for d in iter_descendants(p)]
    assert qn("w:drawing") in tags
    assert qn("w:pict") not in tags


def test_fallback_used_when_no_choice():
    p = body(
        "<w:p><mc:AlternateContent><mc:Fallback><w:pict/></mc:Fallback></mc:AlternateContent></w:p>"
    )[0]
    assert qn("w:pict") in [d.tag for d in iter_descendants(p)]


def test_textbox_paragraphs_from_choice_only():
    p = body(
        "<w:p><w:r><mc:AlternateContent><mc:Choice><w:drawing><wps:txbx><w:txbxContent>"
        "<w:p><w:r><w:t>caption</w:t></w:r></w:p></w:txbxContent></wps:txbx></w:drawing></mc:Choice>"
        "<mc:Fallback><w:pict><v:textbox><w:txbxContent><w:p><w:r><w:t>caption</w:t></w:r></w:p>"
        "</w:txbxContent></v:textbox></w:pict></mc:Fallback></mc:AlternateContent></w:r></w:p>"
    )[0]
    assert len(textbox_paragraphs(p)) == 1


def test_vml_textbox_without_alternate_content():
    p = body(
        "<w:p><w:r><w:pict><v:textbox><w:txbxContent><w:p/><w:p/></w:txbxContent></v:textbox>"
        "</w:pict></w:r></w:p>"
    )[0]
    assert len(textbox_paragraphs(p)) == 2


def test_textbox_text_not_part_of_outer_descendants():
    p = body(
        "<w:p><w:r><w:drawing><wps:txbx><w:txbxContent><w:p><w:r><w:t>in</w:t></w:r></w:p>"
        "</w:txbxContent></wps:txbx></w:drawing></w:r></w:p>"
    )[0]
    assert qn("w:p") not in [d.tag for d in iter_descendants(p)]


def test_tables_keep_nested_structure():
    b = body("<w:tbl><w:tr><w:tc><w:tbl/></w:tc></w:tr></w:tbl>")
    blocks = list(iter_body_blocks(b))
    assert [x.tag for x in blocks] == [W_TBL]


@pytest.mark.parametrize(
    "xml",
    [b"<a", b'<!DOCTYPE a [<!ENTITY e "x">]><a>&e;</a>', b"<!DOCTYPE a><a/>"],
)
def test_parse_rejects_broken_and_dtd(xml):
    with pytest.raises(XmlParseError):
        parse_xml(xml)
