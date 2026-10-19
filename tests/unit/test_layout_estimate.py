from pathlib import Path

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.layout.estimate import compute_volume, volume_by_estimate, volume_by_layout
from vkr_checker.layout.fonts import font_substitutions
from vkr_checker.layout.outcome import compute_layout, with_layout
from vkr_checker.layout.soffice import LayoutError
from vkr_checker.model.document import RunInfo
from vkr_checker.thresholds import Thresholds


def thesis(with_layout_=False):
    b = DocBuilder()
    b.heading("ТИТУЛ", kind="TITLE", page=1)
    b.heading("ВВЕДЕНИЕ", kind="INTRO", page=3)
    b.para("а" * 3600, page=3)
    b.heading("Теория", kind="CHAPTER", number="1", page=5)
    b.para("б" * 1800, page=5)
    b.table([["x"], ["y"], ["z"], ["w"]], page=6)
    b.heading("ЗАКЛЮЧЕНИЕ", kind="CONCLUSION", page=9)
    b.para("в" * 900, page=9)
    b.heading("СПИСОК ЛИТЕРАТУРЫ", kind="BIBLIOGRAPHY", page=10)
    b.para("1. Источник", page=10)
    return b.build(with_layout=with_layout_)


def with_heading_pages(doc):
    from dataclasses import replace

    pages = {s.id: doc.paragraph(s.heading_paragraph_idx).idx for s in doc.sections}
    # страницы заголовков берём из paragraph_pages макета
    hp = {sid: doc.layout.paragraph_pages[idx] for sid, idx in pages.items()}
    return replace(doc, layout=replace(doc.layout, heading_pages=hp))


def test_volume_by_layout_counts_pages_from_intro_to_bibliography():
    doc = with_heading_pages(thesis(with_layout_=True))
    vol = volume_by_layout(doc)
    assert vol.method == "layout"
    assert vol.pages_main == 7  # страницы 3..9
    assert [p for _, p in vol.by_section] == [2.0, 4.0, 1.0]


def test_volume_estimate_formula_and_shares():
    th = Thresholds(CHARS_PER_PAGE=1800, TABLE_ROW_PAGE_SHARE=0.1)
    vol = volume_by_estimate(thesis(), th)
    assert vol.method == "estimate"
    # введение 2.0, глава 1.0 + 4 строки * 0.1, заключение 0.5
    assert [p for _, p in vol.by_section] == [2.0, 1.4, 0.5]
    assert vol.pages_main == 3.9
    assert "1800" in vol.formula


def test_compute_volume_falls_back_to_estimate_without_layout():
    assert compute_volume(thesis()).method == "estimate"
    assert compute_volume(with_heading_pages(thesis(True))).method == "layout"


def test_estimate_without_intro_is_unavailable():
    b = DocBuilder()
    b.heading("Теория", kind="CHAPTER", number="1")
    vol = volume_by_estimate(b.build())
    assert vol.pages_main is None and vol.unavailable


def test_font_substitutions_ignores_metric_aliases_and_unknown_inventory():
    doc = thesis()
    from dataclasses import replace

    p = doc.paragraphs[2]
    runs = (RunInfo("текст", font="Times New Roman"), RunInfo("ещё", font="Brush Script"))
    doc = replace(doc, paragraphs=(*doc.paragraphs[:2], replace(p, runs=runs), *doc.paragraphs[3:]))
    installed = frozenset({"liberation serif", "dejavu sans"})
    msgs = font_substitutions(doc, installed)
    assert len(msgs) == 1 and msgs[0].startswith("Brush Script")


def test_compute_layout_reports_reason_on_failure_and_attaches_warning():
    doc = thesis()

    def boom() -> Path:
        raise LayoutError("вёрстка не уложилась в 5 с")

    outcome = compute_layout(doc, boom)
    assert outcome.failed and outcome.reason == "вёрстка не уложилась в 5 с"
    result = with_layout(doc, outcome)
    assert result.layout is None
    assert "вёрстка не уложилась" in result.meta.warnings[-1]


def test_compute_layout_unexpected_error_is_not_leaked():
    def bad() -> Path:
        raise ValueError("секретный путь /tmp/abc")

    outcome = compute_layout(thesis(), bad)
    assert outcome.failed and "секретный" not in outcome.reason
