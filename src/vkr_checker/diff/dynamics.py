"""Динамика находок между версиями (DIF-06, ARCHITECTURE_CHECKS.md §5.7)."""

from __future__ import annotations

from vkr_checker.model.finding import Finding
from vkr_checker.report.schema import CheckReport, Dynamics, DynamicsItem


def _collect(report: CheckReport) -> dict[tuple[str, str], list[Finding]]:
    groups: dict[tuple[str, str], list[Finding]] = {}
    for block in report.blocks:
        for result in block.rule_results:
            for f in result.findings:
                if f.not_run or f.level == "not_checked":
                    continue
                groups.setdefault((f.rule_id, f.fingerprint), []).append(f)
    return groups


def _total(group: list[Finding]) -> int:
    return sum(f.count for f in group)


def _trend(old: int, new: int) -> str:
    return "less" if new < old else "more" if new > old else "same"


def build_dynamics(old: CheckReport, new: CheckReport) -> Dynamics:
    """Сопоставление по fingerprint: fixed (только в старой), new (только в новой), remaining."""
    a, b = _collect(old), _collect(new)
    fixed: list[DynamicsItem] = []
    appeared: list[DynamicsItem] = []
    remaining: list[DynamicsItem] = []
    for key in sorted(set(a) | set(b)):
        rule_id, fingerprint = key
        in_old, in_new = a.get(key), b.get(key)
        sample = (in_new or in_old)[0]  # type: ignore[index]
        base = {
            "fingerprint": fingerprint, "rule_id": rule_id,
            "title": sample.title, "message": sample.message,
        }  # fmt: skip
        if in_old and in_new:
            c_old, c_new = _total(in_old), _total(in_new)
            remaining.append(
                DynamicsItem(**base, count_old=c_old, count_new=c_new, trend=_trend(c_old, c_new))
            )
        elif in_old:
            fixed.append(DynamicsItem(**base, count_old=_total(in_old), count_new=0, trend="less"))
        else:
            appeared.append(
                DynamicsItem(**base, count_old=None, count_new=_total(in_new), trend="more")
            )  # type: ignore[arg-type]
    return Dynamics(fixed=fixed, new=appeared, remaining=remaining)
