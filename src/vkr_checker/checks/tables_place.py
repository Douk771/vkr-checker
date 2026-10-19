"""TBL-10..12: место и целостность таблиц (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

import re

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.registry import register
from vkr_checker.checks.rulehelpers import table_in_main_part
from vkr_checker.model.document import Document, Table
from vkr_checker.model.finding import Finding

_STAT_TOKEN = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё])(?:M|SD|p|r|rs|U|t|F|β|χ2|χ²|H)(?![A-Za-zА-Яа-яЁё])"
)
_STAT_WORDS = re.compile(r"результат|диагностик|статистик|корреляц|показател", re.IGNORECASE)
_APPENDIX_WORD = re.compile(r"приложени", re.IGNORECASE)


def _span(ctx: CheckContext, table: Table) -> tuple[int, int] | None:
    layout = ctx.doc.layout
    if layout is None or table.idx not in layout.table_pages:
        return None
    first = layout.table_pages[table.idx]
    return first, layout.table_last_pages.get(table.idx, first)


class _PlaceRule:
    block = "numbering"  # TBL-12 переопределяет: он относится к блоку «Таблицы»
    source = Source("M", "Таблицы в основном тексте и в приложениях")
    default_level = "suspicion"
    priority = "should"


@register
class Tbl10LongTable(_PlaceRule):
    id = "TBL-10"
    title = "Длинная таблица в основном тексте"
    needs = frozenset({Need.TABLES, Need.LAYOUT_OR_ESTIMATE})

    def run(self, ctx: CheckContext):
        th, out = ctx.th, []
        for table in ctx.doc.tables:
            if not table_in_main_part(ctx, table):
                continue
            span = _span(ctx, table)
            rows = len(table.rows)
            if span is not None:
                first, last = span
                pages = last - first + 1
                # короткая таблица, разорванная страницей, - это TBL-12, а не повод для приложения
                long_enough = pages >= 3 or (pages == 2 and rows > th.SHORT_TABLE_ROWS)
                if not long_enough:
                    continue
                text = f"занимает {pages} стр. (с {first} по {last})"
                method = "layout"
            elif rows > th.TBL10_ROWS_EST:
                text = f"содержит {rows} строк, вероятно, длиннее страницы"
                method = "estimate"
            else:
                continue
            label = table.number_label(ctx.doc)
            out.append(
                new_finding(
                    self,
                    f"{label} {text}; длинные таблицы по методичке выносят в приложение.",
                    fingerprint=f"TBL-10|{table.idx}",
                    method=method,
                    locations=[ctx.loc.cell(table.idx, 1, 1)] if table.rows else [],
                    values={"rows": rows, "first_page": span[0] if span else None},
                    hint="Оставьте в тексте сводку, а полную таблицу перенесите в приложение.",
                )  # fmt: skip
            )
        return result_of(self, out)


def _has_stat_content(ctx: CheckContext, table: Table) -> bool:
    texts: list[str] = []
    if table.caption_idx is not None and table.caption_idx < len(ctx.doc.captions):
        texts.append(ctx.doc.captions[table.caption_idx].title)
    if table.rows:
        texts.extend(c.text for c in table.rows[0].cells)
    joined = " ".join(texts)
    return bool(_STAT_TOKEN.search(joined) or _STAT_WORDS.search(joined))


def _appendix_ref_near(doc: Document, table: Table, near: int) -> bool:
    lo = (table.prev_paragraph_idx or 1) - near
    hi = (table.next_paragraph_idx or table.prev_paragraph_idx or 1) + near
    return any(
        _APPENDIX_WORD.search(p.text)
        for p in doc.paragraphs
        if lo <= p.idx <= hi and p.cell is None
    )


@register
class Tbl11StatsWithoutAppendix(_PlaceRule):
    id = "TBL-11"
    title = "Таблица результатов без ссылки на приложение"
    needs = frozenset({Need.TABLES})

    def run(self, ctx: CheckContext):
        out: list[Finding] = []
        for table in ctx.doc.tables:
            if not table_in_main_part(ctx, table) or not _has_stat_content(ctx, table):
                continue
            if _appendix_ref_near(ctx.doc, table, ctx.th.NEAR_PARAS):
                continue
            out.append(
                new_finding(
                    self,
                    f"{table.number_label(ctx.doc)}: статистика или результаты диагностики "
                    "в основном тексте без ссылки на приложение с полной таблицей.",
                    fingerprint=f"TBL-11|{table.idx}",
                    method="regex",
                    locations=[ctx.loc.cell(table.idx, 1, 1)] if table.rows else [],
                    hint="Полные данные обычно выносят в приложение и дают на него ссылку.",
                )  # fmt: skip
            )
        return result_of(self, out)


@register
class Tbl12ShortTableSplit(_PlaceRule):
    id = "TBL-12"
    block = "tables"
    title = "Короткая таблица разорвана страницей"
    needs = frozenset({Need.TABLES, Need.LAYOUT})

    def run(self, ctx: CheckContext):
        out: list[Finding] = []
        for table in ctx.doc.tables:
            if table.parent_table_idx is not None:
                continue
            span = _span(ctx, table)
            if span is None or span[0] == span[1] or len(table.rows) > ctx.th.SHORT_TABLE_ROWS:
                continue
            out.append(
                new_finding(
                    self,
                    f"{table.number_label(ctx.doc)}: таблица из {len(table.rows)} строк "
                    f"начинается на стр. {span[0]} и заканчивается на стр. {span[1]}.",
                    fingerprint=f"TBL-12|{table.idx}",
                    method="layout",
                    locations=[ctx.loc.cell(table.idx, 1, 1)],
                    values={"first_page": span[0], "last_page": span[1]},
                    hint="Расхождение возможно из-за разной вёрстки LibreOffice и Word: "
                    "проверьте в Word.",
                )  # fmt: skip
            )
        return result_of(self, out)
