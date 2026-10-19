import zipfile

import pytest

from vkr_checker.docx.package import DocxPackage
from vkr_checker.docx.reader import read_document

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
EXTRA = (
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'
)
CT = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'


def p(text, ppr=""):
    return f"<w:p><w:pPr>{ppr}</w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>"


def read(tmp_path, body):
    path = tmp_path / "a.docx"
    doc = f"<w:document {W} {EXTRA}><w:body>{body}</w:body></w:document>"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", CT)
        zf.writestr("word/document.xml", doc)
    with DocxPackage.open(path) as pkg:
        return read_document(pkg, "a.docx", "0" * 64)


SECT = (
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:left="1701" w:right="850"/></w:sectPr>'
)


def test_page_setup_text_width(tmp_path):
    doc = read(tmp_path, p("x") + SECT)
    ps = doc.page_setup[0]
    assert ps.margin_left_cm == 3.0
    assert abs(ps.text_width_cm - 16.5) < 0.05


def test_deleted_paragraph_and_ins_text(tmp_path):
    body = (
        "<w:p><w:pPr><w:rPr><w:del/></w:rPr></w:pPr><w:del><w:r><w:delText>a</w:delText></w:r></w:del></w:p>"
        "<w:p><w:ins><w:r><w:t>вставка</w:t></w:r></w:ins><w:del><w:r><w:delText>старое</w:delText></w:r></w:del></w:p>"
    )
    doc = read(tmp_path, body)
    assert [x.text for x in doc.paragraphs] == ["вставка"]


def test_table_grid_merge_and_cell_paragraphs(tmp_path):
    tbl = (
        '<w:tbl><w:tblPr><w:tblW w:w="5668" w:type="dxa"/></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="2834"/><w:gridCol w:w="2834"/></w:tblGrid>'
        '<w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>' + p("шапка") + "</w:tc></w:tr>"
        '<w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr>' + p("а") + "</w:tc>"
        "<w:tc>" + p("б") + "</w:tc></w:tr>"
        "<w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc><w:tc>" + p("в") + "</w:tc></w:tr>"
        "</w:tbl>"
    )
    doc = read(tmp_path, p("до") + tbl + p("после"))
    t = doc.tables[0]
    assert t.grid_cols_cm == pytest.approx((5.0, 5.0), abs=0.01)
    assert t.width_cm == pytest.approx(10.0, abs=0.01)
    assert t.prev_paragraph_idx == 1 and t.next_paragraph_idx == len(doc.paragraphs)
    assert t.rows[0].cells[0].grid_span == 2
    assert t.rows[1].cells[0].v_merge == "restart"
    assert t.rows[2].cells[0].v_merge == "continue"
    assert t.rows[2].cells[1].col == 2
    assert doc.paragraph(2).cell.table_idx == 1
    assert t.rows[0].cells[0].paragraphs[0].text == "шапка"
    assert doc.blocks[1] is not None and doc.blocks[1].idx == 1


def test_nested_table_gets_parent(tmp_path):
    inner = "<w:tbl><w:tr><w:tc>" + p("in") + "</w:tc></w:tr></w:tbl>"
    outer = "<w:tbl><w:tr><w:tc>" + p("out") + inner + "</w:tc></w:tr></w:tbl>"
    doc = read(tmp_path, outer)
    assert [t.parent_table_idx for t in doc.tables] == [None, 1]
    assert len(doc.blocks) == 1


def test_images_and_textbox(tmp_path):
    drawing = (
        "<w:p><w:r><w:drawing><wp:inline><a:graphic><a:graphicData><pic:pic>"
        "<pic:blipFill><a:blip/></pic:blipFill></pic:pic></a:graphicData></a:graphic>"
        "</wp:inline></w:drawing></w:r></w:p>"
    )
    doc = read(tmp_path, drawing + p("Рисунок 1"))
    assert len(doc.images) == 1 and doc.images[0].paragraph_idx == 1
    assert doc.images[0].kind == "picture"


def test_page_break_carries_to_next_paragraph(tmp_path):
    brk = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
    doc = read(tmp_path, p("a") + brk + p("ПРИЛОЖЕНИЕ А"))
    assert [x.page_break_before for x in doc.paragraphs] == [False, False, True]


def test_toc_field_spanning_paragraphs(tmp_path):
    fc = lambda t: f'<w:r><w:fldChar w:fldCharType="{t}"/></w:r>'  # noqa: E731
    body = (
        "<w:p>"
        + fc("begin")
        + '<w:r><w:instrText>TOC \\o "1-3"</w:instrText></w:r>'
        + fc("separate")
        + "<w:r><w:t>Введение 3</w:t></w:r></w:p>"
        + "<w:p><w:r><w:t>Глава 1 5</w:t></w:r>"
        + fc("end")
        + "</w:p>"
    )
    doc = read(tmp_path, body)
    assert [f.kind for f in doc.fields] == ["TOC"]
    assert [x.text for x in doc.paragraphs] == ["Введение 3", "Глава 1 5"]
