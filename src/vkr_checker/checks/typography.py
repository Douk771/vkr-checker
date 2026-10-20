"""TBL-06: запись величины разорвана переносом строки («60⏎%», «n =⏎37»).

Обычный пробел в «n = 17» сам по себе не мешает: проблема возникает, только когда знак или
единица уезжают на следующую строку. Поэтому правило смотрит на реальные переносы в вёрстке
LibreOffice; без вёрстки оно не выполняется. Вёрстка Word может переносить строки иначе.
"""

from __future__ import annotations

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.registry import register
from vkr_checker.model.document import BrokenNotation, Document
from vkr_checker.model.finding import Finding
from vkr_checker.nlp.normalize import normalize_key


def _paragraph_of(doc: Document, bn: BrokenNotation) -> int | None:
    """Абзац (не ячейка) на этой странице или соседней, где встречается текст вокруг разрыва."""
    key = normalize_key(bn.before[-20:] + bn.after[:20])
    if len(key) < 4 or doc.layout is None:
        return None
    pages = doc.layout.paragraph_pages
    for p in doc.paragraphs:
        if p.cell is None and abs(pages.get(p.idx, -10) - bn.page) <= 1:
            if key in normalize_key(p.text):
                return p.idx
    return None


@register
class Tbl06NonBreakingSpace:
    id = "TBL-06"
    title = "Перенос строки внутри записи величины"
    block = "tables"
    source = Source("CH", "Оформление таблиц и записи величин")
    default_level = "suspicion"
    needs = frozenset({Need.LAYOUT})
    priority = "should"

    def run(self, ctx: CheckContext):
        doc = ctx.doc
        assert doc.layout is not None
        out: list[Finding] = []
        for n, bn in enumerate(doc.layout.broken_notations):
            idx = _paragraph_of(doc, bn)
            shown = f"{bn.before[-12:].lstrip()}⏎{bn.after[:12].rstrip()}"
            out.append(
                new_finding(
                    self,
                    f"Стр. {bn.page}: запись «{shown}» разорвана переносом строки.",
                    fingerprint=f"TBL-06|{bn.page}|{n}",
                    locations=[ctx.loc.paragraph(idx)] if idx is not None else [],
                    method="layout",
                    values={"page": bn.page, "line_end": bn.before, "line_start": bn.after},
                    hint="Поставьте неразрывный пробел (Ctrl+Shift+Пробел) между числом и "
                    "знаком: так запись не разорвётся. Word может переносить строки иначе, "
                    "чем LibreOffice.",
                )  # fmt: skip
            )
        return result_of(self, out)
