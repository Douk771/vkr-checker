from dataclasses import replace

import pytest

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.engine import BLOCK_ORDER, run_rule, run_rules
from vkr_checker.checks.registry import all_rules, clear_for_tests, register
from vkr_checker.model.document import Layout
from vkr_checker.model.finding import Finding


class FakeRule:
    """Правило-болванка: возвращает заранее заданные находки."""

    id = "TST-01"
    title = "Тестовое правило"
    block = "tables"
    source = Source("CH", "Тест")
    default_level = "violation"
    priority = "must"

    def __init__(self, needs=(), findings_fn=None, rule_id="TST-01", block="tables"):
        self.id, self.block = rule_id, block
        self.needs = frozenset(needs)
        self._fn = findings_fn or (lambda rule, ctx: [])
        self.calls = 0

    def run(self, ctx):
        self.calls += 1
        return result_of(self, self._fn(self, ctx))


def make_doc(layout_status=None, confidence=1.0):
    b = DocBuilder()
    b.heading("ВВЕДЕНИЕ", "INTRO")
    b.para("Текст введения.", page=1)
    b.heading("ГЛАВА 1", "CHAPTER", number="1")
    b.para("Текст главы 1.", page=2)
    b.table([["a", "b"], ["1", "2"]], caption="Таблица 1", page=2)
    doc = b.build(with_layout=layout_status is not None)
    if layout_status:
        doc = replace(doc, layout=Layout(page_count=2, paragraph_pages={1: 1, 2: 1, 3: 2, 4: 2},
                                         table_pages={1: 2}, status=layout_status))  # fmt: skip
    if confidence != 1.0:
        doc = replace(doc, sections=tuple(replace(s, confidence=confidence) for s in doc.sections))
    return doc


def ctx_for(doc):
    return CheckContext.build(doc)


def cell_finding(rule, ctx, row, fp="TST-01|Таблица 1|indent", **kw):
    return new_finding(
        rule, "Таблица 1: красная строка в {count} ячейках", fingerprint=fp,
        locations=[ctx.loc.cell(1, row, 1)], **kw,
    )  # fmt: skip


def test_rule_without_findings_is_passed():
    res = run_rule(ctx_for(make_doc()), FakeRule())
    assert (res.outcome, res.findings) == ("passed", [])


def test_missing_need_gives_not_run_with_single_suspicion_finding():
    rule = FakeRule(needs={Need.CH2})
    res = run_rule(ctx_for(make_doc()), rule)
    assert rule.calls == 0
    assert res.outcome == "not_run"
    assert "вторая глава" in res.skipped_reason
    (f,) = res.findings
    assert (f.not_run, f.level) == (True, "suspicion")
    assert "TST-01" in f.message and "пропущена" in f.message


def test_present_needs_let_rule_run():
    rule = FakeRule(needs={Need.INTRO, Need.CH1, Need.TABLES})
    run_rule(ctx_for(make_doc()), rule)
    assert rule.calls == 1


def test_only_missing_layout_gives_not_checked_not_not_run():
    res = run_rule(ctx_for(make_doc()), FakeRule(needs={Need.LAYOUT}))
    assert res.outcome == "not_checked"
    (f,) = res.findings
    assert (f.level, f.not_run) == ("not_checked", False)


def test_missing_layout_and_other_need_is_not_run():
    res = run_rule(ctx_for(make_doc()), FakeRule(needs={Need.LAYOUT, Need.CH2}))
    assert res.outcome == "not_run"


def test_layout_or_estimate_never_blocks():
    rule = FakeRule(needs={Need.LAYOUT_OR_ESTIMATE})
    run_rule(ctx_for(make_doc()), rule)
    assert rule.calls == 1


def test_rule_exception_becomes_not_run_without_leaking_values(caplog):
    def boom(rule, ctx):
        secret = "ТЕКСТ РАБОТЫ"  # noqa: F841
        raise RuntimeError("секрет в сообщении")

    res = run_rule(ctx_for(make_doc()), FakeRule(findings_fn=boom))
    assert res.outcome == "not_run"
    assert res.skipped_reason == "внутренняя ошибка разбора"
    assert "секрет" not in caplog.text and "ТЕКСТ РАБОТЫ" not in caplog.text
    assert "TST-01" in caplog.text and "RuntimeError" in caplog.text


def test_findings_with_same_fingerprint_collapse():
    def many(rule, ctx):
        return [cell_finding(rule, ctx, r) for r in (1, 2, 1, 2, 1, 2, 1)]

    res = run_rule(ctx_for(make_doc()), FakeRule(findings_fn=many))
    (f,) = res.findings
    assert f.count == 7
    assert f.message == "Таблица 1: красная строка в 7 ячейках"
    assert len(f.locations) == 5  # COLLAPSE_SHOW_LOCATIONS
    assert len(f.values["all_cells"]) == 7
    assert f.values["all_cells"][0] == "Таблица 1, строка 1, столбец 1"
    assert res.outcome == "findings"


def test_different_fingerprints_stay_separate():
    def two(rule, ctx):
        return [
            cell_finding(rule, ctx, 1, fp="TST-01|A"),
            cell_finding(rule, ctx, 2, fp="TST-01|B"),
        ]

    res = run_rule(ctx_for(make_doc()), FakeRule(findings_fn=two))
    assert [f.fingerprint for f in res.findings] == ["TST-01|A", "TST-01|B"]
    assert all(f.count == 1 for f in res.findings)


def test_ids_are_stable_hex12_and_unique_for_same_fingerprint_with_different_level():
    def same_fp(rule, ctx):
        return [
            cell_finding(rule, ctx, 1, level="violation"),
            cell_finding(rule, ctx, 2, level="suspicion"),
        ]

    ctx = ctx_for(make_doc())
    a = run_rule(ctx, FakeRule(findings_fn=same_fp))
    b = run_rule(ctx, FakeRule(findings_fn=same_fp))
    ids = [f.id for f in a.findings]
    assert len(ids) == len(set(ids)) == 2
    assert ids == [f.id for f in b.findings]
    assert all(len(i) == 12 and int(i, 16) >= 0 for i in ids)


def test_sort_order_by_paragraph_then_table_then_fingerprint():
    def unsorted(rule, ctx):
        return [
            new_finding(rule, "c", fingerprint="z", locations=[ctx.loc.paragraph(3)]),
            new_finding(rule, "a", fingerprint="b", locations=[ctx.loc.paragraph(1)]),
            new_finding(rule, "b", fingerprint="a", locations=[ctx.loc.paragraph(1)]),
            new_finding(rule, "g", fingerprint="g"),
        ]

    res = run_rule(ctx_for(make_doc()), FakeRule(findings_fn=unsorted))
    assert [f.fingerprint for f in res.findings] == ["g", "a", "b", "z"]


def test_run_rules_orders_by_rule_id():
    rules = [FakeRule(rule_id="TST-03"), FakeRule(rule_id="TST-01"), FakeRule(rule_id="TST-02")]
    out = run_rules(ctx_for(make_doc()), rules)
    assert [r.rule_id for r in out] == ["TST-01", "TST-02", "TST-03"]


def layout_violation(rule, ctx):
    return [
        new_finding(rule, "m", fingerprint="fp", method="layout", locations=[ctx.loc.paragraph(1)])
    ]


def style_violation(rule, ctx):
    return [
        new_finding(rule, "m", fingerprint="fp", method="style", locations=[ctx.loc.paragraph(1)])
    ]


def test_partial_layout_downgrades_layout_method_violation():
    res = run_rule(ctx_for(make_doc("partial")), FakeRule(findings_fn=layout_violation))
    (f,) = res.findings
    assert f.level == "suspicion"
    assert f.values["downgraded_from"] == "violation"


def test_partial_layout_does_not_touch_style_findings_and_ok_layout_keeps_level():
    res = run_rule(ctx_for(make_doc("partial")), FakeRule(findings_fn=style_violation))
    assert res.findings[0].level == "violation"
    res = run_rule(ctx_for(make_doc("ok")), FakeRule(findings_fn=layout_violation))
    assert res.findings[0].level == "violation"


def test_low_structure_confidence_downgrades_but_never_upgrades():
    def mixed(rule, ctx):
        return [
            new_finding(rule, "v", fingerprint="v", level="violation"),
            new_finding(rule, "s", fingerprint="s", level="suspicion"),
        ]

    rule = FakeRule(needs={Need.INTRO}, findings_fn=mixed)
    res = run_rule(ctx_for(make_doc(confidence=0.3)), rule)
    assert {f.fingerprint: f.level for f in res.findings} == {"v": "suspicion", "s": "suspicion"}
    res = run_rule(ctx_for(make_doc(confidence=0.9)), rule)
    assert {f.fingerprint: f.level for f in res.findings} == {"v": "violation", "s": "suspicion"}


def test_registry_is_sorted_and_rejects_duplicates():
    clear_for_tests()
    try:

        @register
        class B(FakeRule):
            def __init__(self):
                super().__init__(rule_id="TST-02")

        @register
        class A(FakeRule):
            def __init__(self):
                super().__init__(rule_id="TST-01")

        assert [r.id for r in all_rules()] == ["TST-01", "TST-02"]
        with pytest.raises(ValueError):
            register(A)
    finally:
        clear_for_tests()


def test_block_order_matches_contract_blocks():
    assert BLOCK_ORDER[0] == "structure" and BLOCK_ORDER[-2:] == ("not_checked", "diff_impact")
    assert len(BLOCK_ORDER) == len(set(BLOCK_ORDER)) == 12


def test_new_finding_defaults_match_rule():
    rule = FakeRule()
    f = new_finding(rule, "m", fingerprint="fp")
    assert isinstance(f, Finding)
    assert (f.level, f.block, f.origin, f.not_run) == ("violation", "tables", "rules", False)
