"""Движок проверок (ARCHITECTURE_CHECKS.md §2): needs -> run -> понижение -> схлопывание -> порядок.

Ошибка одного правила не роняет сервис: итог not_run, в лог идут только id правила и тип
исключения (без значений переменных и текстов работы).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable

from vkr_checker.checks.base import NEED_TITLES, CheckContext, Need, Rule, new_finding
from vkr_checker.model.document import Document
from vkr_checker.model.finding import BlockId, Finding, RuleResult
from vkr_checker.report.collapse import LEVEL_RANK, collapse_findings

log = logging.getLogger("vkr_checker.checks")

BLOCK_ORDER: tuple[BlockId, ...] = (
    "structure", "intro", "volume", "tables", "numbering", "consistency", "methods",
    "hypothesis", "wording", "tasks", "not_checked", "diff_impact",
)  # fmt: skip
INTERNAL_ERROR_REASON = "внутренняя ошибка разбора"


# --- needs ---------------------------------------------------------------------------------
def _chapters(doc: Document):
    return [s for s in doc.sections if s.kind == "CHAPTER"]


def _first(doc: Document, kind: str):
    return next((s for s in doc.sections if s.kind == kind), None)


def need_section(doc: Document, need: Need):
    """Раздел, подтверждающий need (или None). Для не-секционных needs возвращает None."""
    chapters = _chapters(doc)
    if need == Need.INTRO:
        return _first(doc, "INTRO")
    if need == Need.CH1:
        return chapters[0] if chapters else None
    if need == Need.CH2:
        return chapters[1] if len(chapters) > 1 else None
    if need == Need.SUB_2_1:
        return next((s for s in doc.sections if s.number == "2.1"), None)
    if need == Need.CONCLUSION:
        return _first(doc, "CONCLUSION")
    if need == Need.CH_CONCLUSIONS:
        return _first(doc, "CHAPTER_CONCLUSIONS")
    if need == Need.BIBLIOGRAPHY:
        return _first(doc, "BIBLIOGRAPHY")
    return None


def need_satisfied(doc: Document, need: Need) -> bool:
    if need == Need.TOC:
        return doc.toc is not None
    if need == Need.APPENDICES:
        return bool(doc.appendices)
    if need == Need.TABLES:
        return bool(doc.tables)
    if need == Need.LAYOUT:
        return doc.layout is not None
    if need == Need.LAYOUT_OR_ESTIMATE:
        return True  # без вёрстки работает оценка по тексту
    return need_section(doc, need) is not None


def missing_needs(doc: Document, rule: Rule) -> list[Need]:
    return sorted((n for n in rule.needs if not need_satisfied(doc, n)), key=lambda n: n.value)


def low_confidence_needs(ctx: CheckContext, rule: Rule) -> list[Need]:
    """Needs, чей раздел распознан неуверенно: находки правила не могут быть «нарушением»."""
    low = []
    for need in sorted(rule.needs, key=lambda n: n.value):
        sec = need_section(ctx.doc, need)
        if sec is not None and sec.confidence < ctx.th.STRUCT_LOW_CONFIDENCE:
            low.append(need)
    return low


# --- не выполнено ----------------------------------------------------------------------------
def _not_run_result(rule: Rule, reason: str, message: str) -> RuleResult:
    finding = new_finding(
        rule, message, fingerprint=f"{rule.id}|not_run", level="suspicion", method="count"
    ).model_copy(update={"not_run": True, "values": {"reason": reason}})
    return RuleResult(
        rule_id=rule.id, title=rule.title, block=rule.block, outcome="not_run",
        findings=[finding], artifacts={}, skipped_reason=reason,
    )  # fmt: skip


def _not_checked_result(rule: Rule, reason: str) -> RuleResult:
    finding = new_finding(
        rule,
        f"Не проверяется кодом: {reason}. Проверка {rule.id} пропущена.",
        fingerprint=f"{rule.id}|not_checked",
        level="not_checked",
    )
    return RuleResult(
        rule_id=rule.id, title=rule.title, block=rule.block, outcome="not_checked",
        findings=[finding], artifacts={}, skipped_reason=reason,
    )  # fmt: skip


def _gate(ctx: CheckContext, rule: Rule) -> RuleResult | None:
    missing = missing_needs(ctx.doc, rule)
    if not missing:
        return None
    only_layout = missing == [Need.LAYOUT]
    fragments = ", ".join(NEED_TITLES[n] for n in missing)
    if only_layout:
        return _not_checked_result(rule, "вёрстка LibreOffice недоступна")
    reason = f"не найден: {fragments}"
    return _not_run_result(
        rule, reason, f"Не найден фрагмент ({fragments}), проверка {rule.id} пропущена."
    )


# --- обработка находок ------------------------------------------------------------------------
def _downgrade(ctx: CheckContext, rule: Rule, findings: list[Finding]) -> list[Finding]:
    """violation -> suspicion: частичная вёрстка (method=layout) или неуверенная структура."""
    low = low_confidence_needs(ctx, rule)
    partial = ctx.doc.layout is not None and ctx.doc.layout.status == "partial"
    result: list[Finding] = []
    for f in findings:
        if f.level == "violation" and ((partial and f.method == "layout") or low):
            reason = "частичная вёрстка" if partial and f.method == "layout" else "структура"
            f = f.model_copy(
                update={
                    "level": "suspicion",
                    "values": {
                        **f.values,
                        "downgraded_from": "violation",
                        "downgrade_reason": reason,
                    },
                }
            )
        result.append(f)
    return result


def _sort_key(f: Finding):
    first = f.locations[0] if f.locations else None
    paragraph = (first.paragraph_idx or 0) if first else 0
    table = first.table.table_idx if first and first.table else 0
    return (BLOCK_ORDER.index(f.block), f.rule_id, paragraph, table, f.fingerprint)


def _assign_ids(findings: list[Finding]) -> list[Finding]:
    """id = sha1(rule_id | fingerprint | порядковый номер среди одинаковых)[:12]."""
    seen: dict[tuple[str, str], int] = {}
    out = []
    for f in findings:
        key = (f.rule_id, f.fingerprint)
        ordinal = seen.get(key, 0)
        seen[key] = ordinal + 1
        digest = hashlib.sha1(f"{f.rule_id}|{f.fingerprint}|{ordinal}".encode()).hexdigest()[:12]
        out.append(f.model_copy(update={"id": digest}))
    return out


def _finalize(ctx: CheckContext, rule: Rule, raw: RuleResult) -> RuleResult:
    findings = _downgrade(ctx, rule, list(raw.findings))
    findings = collapse_findings(findings, ctx.th.COLLAPSE_SHOW_LOCATIONS)
    findings.sort(key=_sort_key)
    findings = _assign_ids(findings)
    if raw.outcome in ("not_run", "not_checked"):
        outcome = raw.outcome
    else:
        outcome = "findings" if findings else "passed"
    return raw.model_copy(update={"findings": findings, "outcome": outcome, "rule_id": rule.id})


def run_rule(ctx: CheckContext, rule: Rule) -> RuleResult:
    gated = _gate(ctx, rule)
    if gated is not None:
        return _finalize(ctx, rule, gated)
    try:
        raw = rule.run(ctx)
    except Exception as exc:
        # только id правила и тип исключения: значения переменных и тексты работы в лог не идут
        log.error("правило %s упало: %s", rule.id, type(exc).__name__)
        raw = _not_run_result(
            rule,
            INTERNAL_ERROR_REASON,
            f"Проверка {rule.id} не выполнена: {INTERNAL_ERROR_REASON}.",
        )
    return _finalize(ctx, rule, raw)


def run_rules(ctx: CheckContext, rules: Iterable[Rule]) -> list[RuleResult]:
    """Результаты всех правил в порядке rule_id."""
    return [run_rule(ctx, r) for r in sorted(rules, key=lambda r: r.id)]


def sort_results(results: list[RuleResult]) -> list[RuleResult]:
    return sorted(results, key=lambda r: (BLOCK_ORDER.index(r.block), r.rule_id))


__all__ = [
    "BLOCK_ORDER", "LEVEL_RANK", "need_satisfied", "run_rule", "run_rules", "sort_results",
]  # fmt: skip
