from dataclasses import replace

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.engine import run_rule
from vkr_checker.checks.tables_place import (
    Tbl10LongTable,
    Tbl11StatsWithoutAppendix,
    Tbl12ShortTableSplit,
)
from vkr_checker.checks.volume import Vol01Volume
from vkr_checker.model.document import Layout
from vkr_checker.thresholds import Thresholds


def run(rule, doc, th=None):
    return run_rule(CheckContext.build(doc, th), rule)


def doc_with_table(rows, caption="Таблица 1 - Данные", kind="CHAPTER", page_span=None):
    b = DocBuilder()
    b.heading("ВВЕДЕНИЕ", kind="INTRO")
    b.heading("Глава", kind=kind, number="1")
    b.table([[f"c{r}", "x"] for r in range(rows)], caption=caption)
    doc = b.build(with_layout=page_span is not None)
    if page_span:
        first, last = page_span
        doc = replace(
            doc,
            layout=Layout(
                page_count=last, paragraph_pages={}, table_pages={1: first},
                table_last_pages={1: last},
            ),
        )  # fmt: skip
    return doc


def test_tbl10_layout_long_table_flagged():
    res = run(Tbl10LongTable(), doc_with_table(30, page_span=(5, 7)))
    assert [f.level for f in res.findings] == ["suspicion"]
    assert res.findings[0].method == "layout"


def test_tbl10_short_split_table_belongs_to_tbl12_not_tbl10():
    doc = doc_with_table(6, page_span=(5, 6))
    assert not run(Tbl10LongTable(), doc).findings
    res12 = run(Tbl12ShortTableSplit(), doc)
    assert len(res12.findings) == 1 and res12.findings[0].values["last_page"] == 6


def test_tbl10_estimate_without_layout_and_appendix_excluded():
    th = Thresholds(TBL10_ROWS_EST=25)
    assert run(Tbl10LongTable(), doc_with_table(40), th).findings[0].method == "estimate"
    assert not run(Tbl10LongTable(), doc_with_table(20), th).findings
    assert not run(Tbl10LongTable(), doc_with_table(40, kind="APPENDIX"), th).findings


def test_tbl12_without_layout_is_not_checked():
    res = run(Tbl12ShortTableSplit(), doc_with_table(5))
    assert res.outcome == "not_checked"


def test_tbl11_stats_table_needs_appendix_reference():
    b = DocBuilder()
    b.heading("Глава", kind="CHAPTER", number="2")
    b.para("Результаты приведены ниже.")
    b.table([["Группа", "M", "SD"], ["1", "3", "1"]], caption="Таблица 1 - Описательные статистики")
    doc = b.build()
    assert len(run(Tbl11StatsWithoutAppendix(), doc).findings) == 1

    b = DocBuilder()
    b.heading("Глава", kind="CHAPTER", number="2")
    b.para("Полные данные даны в приложении А.")
    b.table([["Группа", "M", "SD"], ["1", "3", "1"]], caption="Таблица 1 - Описательные статистики")
    assert not run(Tbl11StatsWithoutAppendix(), b.build()).findings


def test_tbl11_plain_table_not_flagged():
    b = DocBuilder()
    b.heading("Глава", kind="CHAPTER", number="2")
    b.table([["Этап", "Срок"], ["1", "май"]], caption="Таблица 1 - План")
    assert not run(Tbl11StatsWithoutAppendix(), b.build()).findings


def thesis(chars):
    b = DocBuilder()
    b.heading("ВВЕДЕНИЕ", kind="INTRO")
    b.para("а" * chars)
    b.heading("Глава", kind="CHAPTER", number="1")
    return b.build()


def test_vol01_out_of_range_is_suspicion_never_violation():
    th = Thresholds(CHARS_PER_PAGE=1000, VOL_MIN=60, VOL_MAX=85)
    res = run(Vol01Volume(), thesis(10_000), th)
    assert [f.level for f in res.findings] == ["suspicion"]
    assert res.findings[0].method == "estimate"
    assert res.artifacts["method"] == "estimate"
    assert res.artifacts["by_section"]


def test_vol01_in_range_no_finding():
    th = Thresholds(CHARS_PER_PAGE=1000, VOL_MIN=60, VOL_MAX=85)
    assert not run(Vol01Volume(), thesis(70_000), th).findings
