"""DIF-01..04, DIF-06: выравнивание разделов, абзацы, перемещения, числа, таблицы, динамика."""

from __future__ import annotations

from datetime import datetime, timezone

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.checks.base import CheckContext
from vkr_checker.diff.compare import build_diff
from vkr_checker.diff.dynamics import build_dynamics
from vkr_checker.diff.model import Side
from vkr_checker.diff.words import norm_title, word_segments
from vkr_checker.model.finding import Finding, FindingSource, RuleResult
from vkr_checker.report.schema import (
    CheckReport,
    FileInfo,
    LayoutInfo,
    Matrix,
    MatrixStats,
    ReportBlock,
    Summary,
    VolumeInfo,
)

LONG_A = "Исследование проводилось на базе университета в течение учебного года по плану."
LONG_B = "Результаты обработки данных показали значимые различия между сравниваемыми группами."
LONG_C = "Теоретический анализ литературы позволил выделить основные подходы к проблеме."


def make_report(findings: list[Finding] | None = None) -> CheckReport:
    results = []
    if findings:
        results.append(
            RuleResult(
                rule_id="TBL-01",
                title="t",
                block="tables",
                outcome="findings",
                findings=findings,
                artifacts={},
            )  # fmt: skip
        )
    return CheckReport(
        schema_version="1.0", service_version="t",
        checked_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        file=FileInfo(name="a.docx", size_bytes=1, sha256="0" * 64),
        layout=LayoutInfo(status="failed", disclaimer="x"),
        volume=VolumeInfo(method="estimate", by_section=[]),
        structure=[],
        summary=Summary(violation=0, suspicion=0, not_checked=0, not_run=0, passed_rules=[]),
        blocks=[ReportBlock(id="tables", title="t", rule_results=results)] if results else [],
        not_checked=[],
        matrix=Matrix(rows=[], stats=MatrixStats(rows=0, gaps=0, auto_cells=0, warnings=[])),
        warnings=[],
    )  # fmt: skip


def side(doc) -> Side:
    return Side(doc, CheckContext.build(doc), make_report())


def finding(fp: str, count: int = 1, level: str = "violation") -> Finding:
    return Finding(
        id="0" * 12, rule_id="TBL-01", title="Т", block="tables", level=level, not_run=False,
        source=FindingSource(doc="M", section="s"), message=f"m {fp}", values={}, locations=[],
        count=count, method="count", fingerprint=fp, origin="rules",
    )  # fmt: skip


def base_doc(*, chapter_title="Теория", tweak=None):
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para(LONG_A)
    b.heading(chapter_title, kind="CHAPTER", number="1")
    b.para(LONG_C)
    b.para(LONG_B)
    return b.build()


def test_norm_title_drops_number_and_yo():
    assert norm_title("Глава 2. Ёмкость метода") == "емкость метода"
    assert norm_title("2.1 Организация") == "организация"


def test_word_segments_mark_insert_and_delete():
    segs = word_segments("Выборка составила 50 человек.", "Выборка составила 60 человек.")
    assert [(s.op, s.text) for s in segs] == [
        ("equal", "Выборка составила "), ("del", "50"), ("ins", "60"), ("equal", " человек."),
    ]  # fmt: skip


def test_identical_documents_have_no_changes():
    diff = build_diff(side(base_doc()), side(base_doc()))
    assert [s.status for s in diff.sections] == ["unchanged", "unchanged"]
    assert all(s.paragraphs == [] for s in diff.sections)
    assert diff.moves == [] and diff.number_changes == []


def test_renamed_section_by_title_and_added_removed():
    old = DocBuilder()
    old.heading("Введение", kind="INTRO")
    old.para(LONG_A)
    old.heading("Методы и организация исследования", kind="CHAPTER", number="2")
    old.para(LONG_B)
    old.heading("Лишний раздел", kind="CHAPTER", number="3")
    old.para(LONG_C)
    new = DocBuilder()
    new.heading("Введение", kind="INTRO")
    new.para(LONG_A)
    new.heading("Организация и методы исследования", kind="CHAPTER", number="2")
    new.para(LONG_B)
    new.heading("Заключение", kind="CONCLUSION")
    new.para("Совсем другой текст про итоги работы и перспективы дальнейших исследований.")
    diff = build_diff(side(old.build()), side(new.build()))
    by_title = {(s.old_title, s.new_title): s for s in diff.sections}
    renamed = by_title[
        ("2 Методы и организация исследования", "2 Организация и методы исследования")
    ]
    assert renamed.status == "renamed" and renamed.rename_basis == "title"
    assert by_title[("3 Лишний раздел", None)].status == "removed"
    assert by_title[(None, "Заключение")].status == "added"


def test_renamed_by_content_when_titles_differ():
    old = DocBuilder()
    old.heading("Введение", kind="INTRO")
    old.para(LONG_A + " " + LONG_B)
    old.heading("Участники", kind="CHAPTER", number="2")
    old.para(LONG_C + " " + LONG_B + " " + LONG_A)
    new = DocBuilder()
    new.heading("Введение", kind="INTRO")
    new.para(LONG_A + " " + LONG_B)
    new.heading("Эмпирическая база", kind="CHAPTER", number="2")
    new.para(LONG_C + " " + LONG_B + " " + LONG_A)
    diff = build_diff(side(old.build()), side(new.build()))
    assert diff.sections[1].status == "renamed"
    assert diff.sections[1].rename_basis == "content"


def test_modified_paragraph_gets_word_segments_and_number_change():
    old = base_doc()
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para("Выборка составила 50 человек в возрасте от 18 до 25 лет.")
    old = b.build()
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.para("Выборка составила 60 человек в возрасте от 18 до 25 лет.")
    new = b.build()
    diff = build_diff(side(old), side(new))
    para = diff.sections[0].paragraphs[0]
    assert para.status == "modified" and para.old_idx == 2 and para.new_idx == 2
    assert any(s.op == "ins" and s.text == "60" for s in para.segments)
    change = diff.number_changes[0]
    assert (change.old, change.new) == ("50", "60")
    assert change.kind == "sample_n"
    assert change.loc_new is not None and change.loc_new.paragraph_idx == 2


def test_moved_paragraph_between_sections_is_linked():
    old = DocBuilder()
    old.heading("Введение", kind="INTRO")
    old.para(LONG_A)
    old.para(LONG_B)
    old.heading("Теория", kind="CHAPTER", number="1")
    old.para(LONG_C)
    new = DocBuilder()
    new.heading("Введение", kind="INTRO")
    new.para(LONG_A)
    new.heading("Теория", kind="CHAPTER", number="1")
    new.para(LONG_C)
    new.para(LONG_B)
    diff = build_diff(side(old.build()), side(new.build()))
    assert len(diff.moves) == 1
    move = diff.moves[0]
    assert (move.from_section, move.to_section) == ("Введение", "1 Теория")
    statuses = {p.status: p.move_id for s in diff.sections for p in s.paragraphs}
    assert statuses["moved_out"] == statuses["moved_in"] == move.id
    assert [s.status for s in diff.sections] == ["modified", "modified"]


def test_short_deleted_paragraph_is_not_a_move():
    old = DocBuilder()
    old.heading("Введение", kind="INTRO")
    old.para("Коротко.")
    old.heading("Теория", kind="CHAPTER", number="1")
    old.para(LONG_C)
    new = DocBuilder()
    new.heading("Введение", kind="INTRO")
    new.heading("Теория", kind="CHAPTER", number="1")
    new.para(LONG_C)
    new.para("Коротко.")
    assert build_diff(side(old.build()), side(new.build())).moves == []


def table_doc(rows, caption="Таблица 1 - Результаты"):
    b = DocBuilder()
    b.heading("Результаты", kind="CHAPTER", number="2")
    b.para(LONG_B)
    b.table(rows, caption=caption)
    return b.build()


def test_table_cell_change_and_added_row():
    old = table_doc([["Шкала", "M"], ["Тревога", "3,4"], ["Стресс", "2,0"]])
    new = table_doc([["Шкала", "M"], ["Тревога", "3,6"], ["Стресс", "2,0"], ["Гнев", "1,1"]])
    diff = build_diff(side(old), side(new))
    t = diff.tables[0]
    assert t.status == "modified" and t.flags == []
    assert [(r.status, r.new_row) for r in t.rows] == [("modified", 2), ("added", 4)]
    assert (t.rows[0].cells[0].col, t.rows[0].cells[0].old, t.rows[0].cells[0].new) == (
        2,
        "3,4",
        "3,6",
    )


def test_table_renumbered_is_matched_by_title():
    old = table_doc([["a", "b"], ["1", "2"]], caption="Таблица 2 - Результаты")
    new = table_doc([["a", "b"], ["1", "2"]], caption="Таблица 3 - Результаты")
    t = build_diff(side(old), side(new)).tables[0]
    assert t.status == "unchanged"
    assert t.flags == ["renumbered", "retitled"] or t.flags == ["renumbered"]
    assert (t.old_label, t.new_label) == ("Таблица 2", "Таблица 3")


def test_table_removed_and_added():
    old = table_doc([["a", "b"], ["1", "2"]], caption="Таблица 1 - Корреляции показателей")
    new = table_doc([["x", "y"], ["7", "8"]], caption="Таблица 1 - Совсем другое")
    statuses = sorted(t.status for t in build_diff(side(old), side(new)).tables)
    assert statuses == ["added", "removed"]


def test_dynamics_fixed_new_remaining_with_trend():
    old = make_report([finding("a", 3), finding("b"), finding("c", 2)])
    new = make_report([finding("a", 1), finding("c", 2), finding("d")])
    dyn = build_dynamics(old, new)
    assert [i.fingerprint for i in dyn.fixed] == ["b"]
    assert [i.fingerprint for i in dyn.new] == ["d"]
    rem = {i.fingerprint: i for i in dyn.remaining}
    assert rem["a"].trend == "less" and rem["a"].count_old == 3 and rem["a"].count_new == 1
    assert rem["c"].trend == "same"


def test_dynamics_ignores_not_checked_level():
    old = make_report([finding("a", level="not_checked")])
    assert build_dynamics(old, make_report()).fixed == []
