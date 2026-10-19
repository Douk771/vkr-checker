import pytest

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.layout.align import align, align_or_fail
from vkr_checker.layout.pdftext import PdfPages, normalize_page
from vkr_checker.layout.soffice import LayoutError
from vkr_checker.nlp.normalize import normalize_key


def pdf_of(*pages: str) -> PdfPages:
    return PdfPages.from_pages([normalize_page(p) for p in pages])


def test_normalize_page_drops_number_lines_hyphens_and_case():
    raw = "Учебная мотива-\nция студен­тов\n12\nЁжик, 3 группы"
    assert normalize_page(raw) == "учебнаямотивациястудентовежик3группы"


def test_page_at_uses_offsets():
    pdf = pdf_of("первая страница", "вторая страница")
    assert pdf.page_count == 2
    assert pdf.page_at(0) == 1
    assert pdf.page_at(len(pdf.pages[0])) == 2


def build_doc():
    b = DocBuilder()
    b.heading("ВВЕДЕНИЕ", kind="INTRO")
    b.para("Актуальность исследования определяется ростом интереса к теме.")
    b.para("Цель работы заключается в проверке связи мотивации и адаптации.")
    b.table(
        [["Показатель общий", "Значение"], ["Среднее значение балла", "Стандартное отклонение"]],
        caption="Таблица 1 - Данные",
    )
    b.para("Выводы по первой главе подводят итоги теоретического анализа.")
    return b.build()


PAGES = (
    "ВВЕДЕНИЕ\nАктуальность исследования определяется ростом интереса к теме.\n1",
    "Цель работы заключается в проверке связи мотивации и адаптации.\n"
    "Таблица 1 - Данные\nПоказатель общий Значение\n2",
    "Среднее значение балла Стандартное отклонение\n"
    "Выводы по первой главе подводят итоги теоретического анализа.\n3",
)


def test_monotone_alignment_pages_and_table_span():
    doc = build_doc()
    res = align(doc, pdf_of(*PAGES))
    lay = res.layout
    assert lay.paragraph_pages[1] == 1 and lay.paragraph_pages[2] == 1
    assert lay.paragraph_pages[3] == 2 and lay.paragraph_pages[4] == 3
    assert lay.table_pages[1] == 2 and lay.table_last_pages[1] == 3
    assert lay.heading_pages == {"s1": 1}
    assert lay.coverage == 1.0 and lay.status == "ok"
    assert lay.page_count == 3


def test_fuzzy_match_tolerates_small_differences():
    doc = build_doc()
    pages = list(PAGES)
    pages[0] = pages[0].replace("определяется", "опредеяется")
    res = align(doc, pdf_of(*pages))
    assert res.layout.paragraph_pages[2] == 1


def test_unmatched_paragraph_inherits_previous_page_and_lowers_coverage():
    doc = build_doc()
    pages = list(PAGES)
    pages[2] = pages[2].replace("Выводы по первой главе подводят итоги теоретического анализа.", "")
    res = align(doc, pdf_of(*pages))
    assert res.layout.paragraph_pages[4] == res.layout.paragraph_pages[3] == 2
    assert 0 < res.layout.coverage < 1


def test_heading_does_not_match_toc_entry_thanks_to_cursor():
    b = DocBuilder()
    b.para("ВВЕДЕНИЕ ........ 3")
    b.para("Текст оглавления второй строки ........ 5")
    b.heading("ВВЕДЕНИЕ", kind="INTRO")
    doc = b.build()
    res = align(
        doc, pdf_of("ВВЕДЕНИЕ ........ 3\nТекст оглавления второй строки ........ 5", "ВВЕДЕНИЕ")
    )
    assert res.layout.paragraph_pages[1] == 1 and res.layout.paragraph_pages[3] == 2


def test_failure_when_coverage_below_threshold():
    doc = build_doc()
    with pytest.raises(LayoutError):
        align_or_fail(doc, pdf_of("совсем другой текст про другое", "и ещё одна страница"))
    assert normalize_key("") == ""


def _tiny_pdf(texts):
    objs = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(texts)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(texts)} >>")
    for i, t in enumerate(texts):
        n = 4 + 2 * i
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents {n} 0 R "
            "/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 "
            "/BaseFont /Helvetica >> >> >> >>"
        )
        stream = f"BT /F1 12 Tf 20 100 Td ({t}) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    out = "%PDF-1.4\n"
    for i, o in enumerate(objs, 1):
        out += f"{i} 0 obj\n{o}\nendobj\n"
    return (out + "trailer\n<< /Root 1 0 R /Size %d >>\n%%%%EOF\n" % (len(objs) + 1)).encode()


def test_extract_pages_reads_real_pdf(tmp_path):
    from vkr_checker.layout.pdftext import extract_pages

    f = tmp_path / "a.pdf"
    f.write_bytes(_tiny_pdf(["Hello World", "Second page"]))
    pdf = extract_pages(f)
    assert pdf.pages == ("helloworld", "secondpage")


def test_extract_pages_rejects_garbage(tmp_path):
    from vkr_checker.layout.pdftext import extract_pages

    f = tmp_path / "bad.pdf"
    f.write_bytes(b"not a pdf")
    with pytest.raises(LayoutError):
        extract_pages(f)
