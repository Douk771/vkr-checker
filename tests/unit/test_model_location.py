import pytest

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.model.document import CellRef
from vkr_checker.model.location import make_location, make_quote


def sample():
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para("Актуальность исследования " + "x" * 300 + " конец.", page=2)
    b.heading("Теория", kind="CHAPTER", number="1")
    b.heading("Методы", kind="SUBSECTION", number="1.1", level=2, parent="s2")
    b.para("Короткий абзац.", page=5)
    b.table([["a", "b"], ["1", "2"]], caption="Таблица 3 - Данные", page=6)
    b.table([["z"]])
    return b.build(with_layout=True)


def test_indexes_and_sections():
    d = sample()
    assert [p.idx for p in d.paragraphs] == [1, 2, 3, 4, 5]
    assert d.paragraph(5).section_id == "s3"
    assert d.section_by_id("s2").end_idx == 3
    assert d.section_path("s3") == ["1 Теория", "1.1 Методы"]


def test_paragraph_location():
    d = sample()
    loc = make_location(d, paragraph_idx=5, char_span=(0, 7))
    assert loc.section_path == ["1 Теория", "1.1 Методы"]
    assert loc.paragraph_idx == 5 and loc.page == 5
    assert loc.quote[slice(*loc.highlight)] == "Короткий"[:7]


def test_long_paragraph_quote_window():
    d = sample()
    text = d.paragraph(2).text
    start = text.index("конец")
    loc = make_location(d, paragraph_idx=2, char_span=(start, start + 5))
    assert len(loc.quote) == 100
    assert loc.quote[slice(*loc.highlight)] == "конец"


def test_cell_location_and_unlabelled_table():
    d = sample()
    loc = make_location(d, cell_ref=CellRef(1, 2, 1))
    assert loc.table.number_label == "Таблица 3" and loc.table.row == 2
    assert loc.quote == "1" and loc.page == 6
    assert (
        make_location(d, cell_ref=CellRef(2, 1, 1)).table.number_label == "таблица №2 без подписи"
    )


def test_no_layout_means_no_page():
    b = DocBuilder()
    b.para("x")
    assert make_location(b.build(), paragraph_idx=1).page is None


def test_requires_exactly_one_target():
    d = sample()
    with pytest.raises(ValueError):
        make_location(d)
    with pytest.raises(ValueError):
        make_location(d, paragraph_idx=1, cell_ref=CellRef(1, 1, 1))


def test_make_quote_without_span_truncates():
    assert make_quote("a  b\nc", None) == ("a b c", None)
