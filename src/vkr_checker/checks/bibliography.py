"""BIB-01: ссылки [N] и список литературы (US-25, Could)."""

from __future__ import annotations

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.registry import register
from vkr_checker.checks.rulehelpers import mention_location


@register
class Bib01SourceReferences:
    id = "BIB-01"
    title = "Ссылки на источники и список литературы"
    block = "numbering"
    source = Source("CH", "Ссылки на литературу")
    default_level = "violation"
    needs = frozenset({Need.BIBLIOGRAPHY})
    priority = "could"

    def run(self, ctx: CheckContext):
        entries = ctx.doc.bibliography
        total = len(entries)
        refs = [r for r in ctx.facts.refs if r.kind == "source"]
        if total == 0:
            return result_of(self, [])
        out = []
        cited: set[int] = set()
        reported: set[int] = set()
        for r in refs:
            if not r.target.isdigit():
                continue
            n = int(r.target)
            if 1 <= n <= total:
                cited.add(n)
            elif n not in reported:
                reported.add(n)
                out.append(
                    new_finding(
                        self,
                        f"Ссылка на источник [{n}], а в списке литературы всего {total}.",
                        fingerprint=f"BIB-01|over|{n}",
                        method="regex",
                        locations=[mention_location(ctx, r.loc)],
                        values={"number": n, "total": total},
                    )  # fmt: skip
                )
        if refs and cited:  # без числовых ссылок (стиль «автор, год») непроцитированность не судим
            uncited = [i for i in range(1, total + 1) if i not in cited]
            if uncited:
                shown = ", ".join(str(i) for i in uncited[:15]) + (
                    " и др." if len(uncited) > 15 else ""
                )
                out.append(
                    new_finding(
                        self,
                        f"Источники без ссылок в тексте: {shown} (всего {len(uncited)}).",
                        fingerprint="BIB-01|uncited",
                        level="suspicion",
                        method="regex",
                        locations=[
                            ctx.loc.paragraph(entries[i - 1].paragraph_idx) for i in uncited[:5]
                        ],
                        values={"uncited": uncited},
                        hint="Источник, на который нет ссылок, можно убрать или процитировать.",
                    )  # fmt: skip
                )
        return result_of(self, out)
