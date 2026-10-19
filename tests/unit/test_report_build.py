from dataclasses import replace
from datetime import datetime, timezone

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.checks.base import CheckContext, Source, new_finding, result_of
from vkr_checker.checks.engine import run_rule, run_rules
from vkr_checker.checks.not_checked import NotCheckedRule, nc_items
from vkr_checker.checks.registry import all_rules
from vkr_checker.model.document import Layout
from vkr_checker.report.build import (
    BLOCK_TITLES,
    NOISE_TEXT,
    assemble_check_report,
    build_blocks,
    build_summary,
    structure_tree,
)
from vkr_checker.report.schema import (
    FileInfo,
    LayoutInfo,
    Matrix,
    MatrixStats,
    VolumeInfo,
)
from vkr_checker.thresholds import Thresholds


class Rule:
    source = Source("CH", "тест")
    priority = "must"
    needs = frozenset()

    def __init__(self, rule_id, block="tables", level="violation", n=1, not_run=False):
        self.id, self.block, self.default_level, self.title = rule_id, block, level, rule_id
        self._n, self._not_run = n, not_run

    def run(self, ctx):
        fs = [new_finding(self, f"msg {i}", fingerprint=f"{self.id}|{i}") for i in range(self._n)]
        return result_of(self, fs)


def results_for(*rules):
    doc = DocBuilder().build()
    return run_rules(CheckContext.build(doc), rules)


def test_nc_items_depend_on_layout_and_ids_are_stable():
    with_layout = [i.id for i in nc_items(layout_failed=False)]
    without = [i.id for i in nc_items(layout_failed=True)]
    assert "NC-01.8" not in with_layout and "NC-01.9" not in with_layout
    assert {"NC-01.8", "NC-01.9"} <= set(without)
    assert set(with_layout) < set(without)
    helpers = {i.id: i.helper for i in nc_items(True)}
    assert helpers["NC-01.1"] == "numbers_index" and helpers["NC-01.6"] == "matrix"
    assert helpers["NC-01.7"] == "rule:MET-01" and helpers["NC-01.10"] == "rule:TBL-09"


def test_nc_rule_emits_one_not_checked_finding_per_item():
    doc = DocBuilder().build()
    res = run_rule(CheckContext.build(doc), NotCheckedRule())
    assert res.outcome == "findings"
    assert len(res.findings) == len(nc_items(True))  # вёрстки нет
    assert all(f.level == "not_checked" and f.block == "not_checked" for f in res.findings)
    laid_out = replace(doc, layout=Layout(page_count=1))
    assert len(run_rule(CheckContext.build(laid_out), NotCheckedRule()).findings) == len(
        nc_items(False)
    )


def test_summary_counts_levels_and_passed_rules():
    results = results_for(
        Rule("TBL-01", n=2),
        Rule("TBL-02", level="suspicion", n=3),
        Rule("TBL-03", n=0),
        NotCheckedRule(),
    )
    s = build_summary(results)
    assert (s.violation, s.suspicion) == (2, 3)
    assert s.not_checked == len(nc_items(True)) and s.not_run == 0
    assert s.passed_rules == ["TBL-03"] and s.noise_warning is None


def test_not_run_counted_separately_from_suspicions():
    class Needy(Rule):
        from vkr_checker.checks.base import Need

        needs = frozenset({Need.CH2})

    s = build_summary(results_for(Needy("MET-01", block="methods")))
    assert (s.not_run, s.suspicion, s.violation) == (1, 0, 0)


def test_noise_warning_over_budget():
    th = Thresholds(NOISE_SUSPICION_BUDGET=3)
    results = results_for(Rule("CON-01", block="consistency", level="suspicion", n=4))
    s = build_summary(results, th)
    assert s.noise_warning == NOISE_TEXT.format(n=4, budget=3)
    assert (
        build_summary(results_for(Rule("CON-01", level="suspicion", n=3)), th).noise_warning is None
    )


def test_blocks_follow_report_order_and_skip_empty():
    results = results_for(
        Rule("NUM-01", block="numbering"),
        Rule("STR-01", block="structure"),
        Rule("TBL-01", block="tables"),
        Rule("TBL-02", block="tables"),
    )
    blocks = build_blocks(results)
    assert [b.id for b in blocks] == ["structure", "tables", "numbering"]
    assert blocks[1].title == BLOCK_TITLES["tables"]
    assert [r.rule_id for r in blocks[1].rule_results] == ["TBL-01", "TBL-02"]


def test_structure_tree_nests_by_parent_and_survives_cycles():
    b = DocBuilder()
    b.heading("Глава 1", kind="CHAPTER", number="1")
    b.heading("Параграф", kind="SUBSECTION", number="1.1", level=2, parent="s1")
    doc = b.build()
    tree = structure_tree(doc)
    assert len(tree) == 1 and tree[0].children[0].title == "Параграф"
    cyc = replace(doc, sections=tuple(replace(s, parent_id=s.id) for s in doc.sections))
    assert structure_tree(cyc) == []  # все узлы ссылаются на себя: корней нет, зацикливания нет


def test_assemble_report_is_valid_and_deterministic():
    b = DocBuilder("работа.docx")
    b.heading("Введение", kind="INTRO")
    doc = b.build()
    results = results_for(Rule("TBL-01"), NotCheckedRule())
    kwargs = dict(
        file=FileInfo(name="работа.docx", size_bytes=10, sha256="0" * 64),
        layout=LayoutInfo(status="failed", reason="тест", disclaimer="LO"),
        volume=VolumeInfo(method="estimate", by_section=[]),
        matrix=Matrix(rows=[], stats=MatrixStats(rows=0, gaps=0, auto_cells=0, warnings=[])),
        service_version="0.1.0",
        checked_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    r1 = assemble_check_report(doc, results, **kwargs)
    r2 = assemble_check_report(doc, results, **kwargs)
    assert r1.model_dump_json() == r2.model_dump_json()
    assert r1.schema_version == "1.0" and r1.summary.violation == 1
    assert [i.id for i in r1.not_checked] == [i.id for i in nc_items(True)]


def test_registry_loads_all_rule_modules():
    ids = [r.id for r in all_rules()]
    assert {"NC-01", "STR-01", "STR-06", "PAGE-01"} <= set(ids)
    assert ids == sorted(ids)
