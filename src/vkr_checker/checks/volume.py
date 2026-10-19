"""VOL-01: объём основной части (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.registry import register
from vkr_checker.checks.textfmt import fmt_num
from vkr_checker.layout.estimate import compute_volume


@register
class Vol01Volume:
    id = "VOL-01"
    title = "Объём работы"
    block = "volume"
    source = Source("M", "Рекомендованный объём")
    default_level = "suspicion"
    needs = frozenset({Need.LAYOUT_OR_ESTIMATE})
    priority = "must"

    def run(self, ctx: CheckContext):
        vol = compute_volume(ctx.doc, ctx.th)
        artifacts = {
            "method": vol.method,
            "by_section": [{"title": t, "pages": p} for t, p in vol.by_section],
            "pages_main": vol.pages_main,
            "estimate_formula": vol.formula,
        }
        if vol.pages_main is None:
            return result_of(self, [], **artifacts)
        lo, hi = ctx.th.VOL_MIN, ctx.th.VOL_MAX
        if lo <= vol.pages_main <= hi:
            return result_of(self, [], **artifacts)
        how = "по вёрстке" if vol.method == "layout" else "по оценке текста"
        relation = "меньше" if vol.pages_main < lo else "больше"
        finding = new_finding(
            self,
            f"Основная часть занимает около {fmt_num(vol.pages_main, 1)} стр. ({how}), "
            f"это {relation} допустимого диапазона {fmt_num(lo, 0)}-{fmt_num(hi, 0)} стр. "
            "(без списка литературы и приложений).",
            fingerprint="VOL-01",
            method="layout" if vol.method == "layout" else "estimate",
            values={"pages": vol.pages_main, "method": vol.method, "min": lo, "max": hi},
            hint="Рекомендованный объём - около 70 страниц; страницы по вёрстке LibreOffice "
            "могут отличаться от Word на 1-2.",
        )  # fmt: skip
        return result_of(self, [finding], **artifacts)
