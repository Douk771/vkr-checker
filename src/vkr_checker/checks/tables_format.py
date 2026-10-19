"""TBL-01..09: оформление таблиц по эффективному форматированию (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.registry import register
from vkr_checker.checks.tblutil import (
    CellPara,
    classify_cell,
    column_widths,
    iter_cell_paragraphs,
    number_columns,
    origin_hint,
)
from vkr_checker.checks.textfmt import fmt_num
from vkr_checker.model.document import Document, Table
from vkr_checker.model.finding import Finding

SRC = Source("CH", "Оформление таблиц")
SINGLE_LINE_EPS = 0.01


def _cell_finding(rule, ctx: CheckContext, cp: CellPara, subtype: str, message: str, **kw):
    label = cp.table.number_label(ctx.doc)
    return new_finding(
        rule,
        f"{label}: {message} (ячеек: {{count}})",
        fingerprint=f"{rule.id}|{cp.table.idx}|{subtype}",
        locations=[ctx.loc.cell(cp.table.idx, cp.cell.row, cp.cell.col)],
        method="style",
        **kw,
    )


class _TableRule:
    source = SRC
    default_level = "violation"
    needs = frozenset({Need.TABLES})
    priority = "must"
    block = "tables"


@register
class Tbl01Indents(_TableRule):
    id = "TBL-01"
    title = "Отступы в ячейках"

    def run(self, ctx: CheckContext):
        eps = ctx.th.INDENT_EPS_CM
        checks = (
            ("first_line", "красная строка", "first_line_cm"),
            ("hanging", "выступ", "hanging_cm"),
            ("left", "левый отступ", "left_cm"),
        )
        out: list[Finding] = []
        for cp in iter_cell_paragraphs(ctx.doc):
            for subtype, name, attr in checks:
                v = getattr(cp.para.fmt, attr)
                if v is None or abs(float(v.value)) <= eps:
                    continue
                hint = "Обнулите отступ в абзацах таблицы: Абзац → Отступ."
                origin = origin_hint(v, cp.para.style_name)
                out.append(
                    _cell_finding(
                        self,
                        ctx,
                        cp,
                        subtype,
                        f"{name} {fmt_num(float(v.value))} см",
                        hint=f"{hint} Здесь {origin}." if origin else hint,
                        values={"actual_cm": float(v.value), "origin": v.origin},
                    )  # fmt: skip
                )
        return result_of(self, out)


@register
class Tbl02Spacing(_TableRule):
    id = "TBL-02"
    title = "Интервалы в ячейках"

    def run(self, ctx: CheckContext):
        out: list[Finding] = []
        for cp in iter_cell_paragraphs(ctx.doc):
            fmt = cp.para.fmt
            rule, line = fmt.line_rule, fmt.line_spacing
            if rule is not None and rule.value != "auto":
                out.append(
                    _cell_finding(
                        self,
                        ctx,
                        cp,
                        "line",
                        f"межстрочный интервал «{rule.value}»",
                        hint="Поставьте одинарный интервал. " + origin_hint(line or rule),
                        values={"line_rule": str(rule.value), "origin": rule.origin},
                    )  # fmt: skip
                )
            elif line is not None and abs(float(line.value) - 1.0) > SINGLE_LINE_EPS:
                out.append(
                    _cell_finding(
                        self,
                        ctx,
                        cp,
                        "line",
                        f"межстрочный интервал {fmt_num(float(line.value))}",
                        hint="Поставьте одинарный интервал. " + origin_hint(line),
                        values={"line_spacing": float(line.value), "origin": line.origin},
                    )  # fmt: skip
                )
            after = fmt.space_after_pt
            if after is not None and (after.value == "auto" or float(after.value) > 0):
                shown = "авто" if after.value == "auto" else f"{fmt_num(float(after.value))} пт"
                out.append(
                    _cell_finding(
                        self,
                        ctx,
                        cp,
                        "space_after",
                        f"интервал после абзаца {shown}",
                        hint="Установите интервал после абзаца 0. " + origin_hint(after),
                        values={"space_after": str(after.value), "origin": after.origin},
                    )  # fmt: skip
                )
        return result_of(self, out)


def _text_widths(doc: Document) -> list[float]:
    return [p.text_width_cm for p in doc.page_setup if p.text_width_cm]


@register
class Tbl03Width(_TableRule):
    id = "TBL-03"
    title = "Ширина таблицы"

    def run(self, ctx: CheckContext):
        doc, tol = ctx.doc, ctx.th.TBL_WIDTH_TOL_CM
        widths = _text_widths(doc)
        out: list[Finding] = []
        for t in doc.tables:
            label = t.number_label(doc)
            locs = [ctx.loc.cell(t.idx, 1, 1)] if t.rows and t.rows[0].cells else []
            if t.layout_type != "fixed":
                out.append(
                    new_finding(
                        self,
                        f"{label}: ширина «по содержимому», нужна фиксированная.",
                        fingerprint=f"TBL-03|{t.idx}|layout",
                        locations=locs,
                        method="style",
                        hint="Свойства таблицы → Автоподбор → Фиксированная ширина столбцов.",
                    )  # fmt: skip
                )
            if not t.grid_cols_cm or not widths:
                continue
            total = sum(t.grid_cols_cm)
            if any(abs(total - w) <= tol for w in widths):
                continue
            out.append(
                new_finding(
                    self,
                    f"{label}: сумма ширин столбцов {fmt_num(total)} см, ширина текста "
                    f"{fmt_num(widths[0])} см (допуск ±{fmt_num(tol)} см).",
                    fingerprint=f"TBL-03|{t.idx}|width",
                    locations=locs,
                    method="style",
                    values={"sum_cm": round(total, 2), "text_width_cm": widths[0]},
                    hint="Растяните таблицу на всю ширину текста.",
                )  # fmt: skip
            )
        return result_of(self, out)


@register
class Tbl04ColumnProportions(_TableRule):
    id = "TBL-04"
    title = "Столбец «№» и текстовый столбец"
    default_level = "suspicion"
    priority = "should"

    def run(self, ctx: CheckContext):
        doc = ctx.doc
        out: list[Finding] = []
        for t in doc.tables:
            widths = column_widths(t)
            if not widths:
                continue
            label = t.number_label(doc)
            num_cols = number_columns(t)
            for col in sorted(num_cols):
                w = widths.get(col)
                if w is not None and w > ctx.th.NUM_COL_MAX_CM:
                    out.append(
                        new_finding(
                            self,
                            f"{label}: столбец «№» шириной {fmt_num(w)} см, нужен узкий.",
                            fingerprint=f"TBL-04|{t.idx}|num_width",
                            locations=[ctx.loc.cell(t.idx, 1, col)],
                            method="regex",
                            values={"width_cm": w},
                            hint="Сделайте столбец «№» около 1 см.",
                        )  # fmt: skip
                    )
            widest = max(widths, key=lambda c: widths[c])
            lengths = self._mean_lengths(t)
            if len(lengths) >= 2 and widest not in num_cols:
                longest = max(lengths, key=lambda c: lengths[c])
                if longest != widest and lengths[longest] > 1.5 * lengths.get(widest, 0):
                    out.append(
                        new_finding(
                            self,
                            f"{label}: самый широкий столбец не содержит самый длинный текст.",
                            fingerprint=f"TBL-04|{t.idx}|widest",
                            locations=[ctx.loc.cell(t.idx, 1, widest)],
                            method="count",
                            hint="Самым широким должен быть текстовый столбец.",
                        )  # fmt: skip
                    )
        return result_of(self, out)

    @staticmethod
    def _mean_lengths(t: Table) -> dict[int, float]:
        sums: dict[int, list[int]] = {}
        for row in t.rows[1:]:
            for c in row.cells:
                if c.grid_span == 1 and c.text.strip():
                    sums.setdefault(c.col, []).append(len(c.text))
        return {col: sum(v) / len(v) for col, v in sums.items()}


@register
class Tbl05Alignment(_TableRule):
    id = "TBL-05"
    title = "Выравнивание в ячейках"

    def run(self, ctx: CheckContext):
        doc = ctx.doc
        gray = ctx.th.CELL_NUMERIC_GRAY
        out: list[Finding] = []
        by_cell: dict[tuple[int, int, int], CellPara] = {}
        for cp in iter_cell_paragraphs(doc):
            by_cell.setdefault((cp.table.idx, cp.cell.row, cp.cell.col), cp)
        for cp in by_cell.values():
            kind = classify_cell(cp.table, cp.cell, gray)
            if kind is None:
                continue
            align = cp.para.fmt.align.value if cp.para.fmt.align else None
            origin = origin_hint(cp.para.fmt.align, cp.para.style_name)
            if kind in ("header", "number", "numeric") and align != "center":
                name = {"header": "шапки", "number": "номера", "numeric": "числа"}[kind]
                out.append(
                    _cell_finding(
                        self,
                        ctx,
                        cp,
                        f"{kind}_align",
                        f"{name} не по центру (сейчас: {align or 'по левому'})",
                        hint="Выровняйте по центру."
                        + (f" {origin.capitalize()}." if origin else ""),
                        values={"align": align or "left", "cell_kind": kind},
                    )  # fmt: skip
                )
            elif kind == "text" and align not in (None, "left"):
                out.append(
                    _cell_finding(
                        self,
                        ctx,
                        cp,
                        "text_align",
                        f"текст выровнен «{align}», нужен левый край",
                        hint="Текстовые ячейки выравниваются по левому краю, не по ширине.",
                        values={"align": align, "cell_kind": kind},
                    )  # fmt: skip
                )
            elif kind == "gray" and align in ("justify", "right"):
                out.append(
                    _cell_finding(
                        self,
                        ctx,
                        cp,
                        "gray_align",
                        f"выравнивание «{align}» в ячейке с цифрами и текстом",
                        level="suspicion",
                        hint="Проверьте: число - по центру, текст - по левому краю.",
                        values={"align": align, "cell_kind": kind},
                    )  # fmt: skip
                )
            v_align = cp.para.fmt.v_align.value if cp.para.fmt.v_align else None
            if v_align != "center":
                out.append(
                    _cell_finding(
                        self,
                        ctx,
                        cp,
                        "v_align",
                        f"по вертикали «{v_align or 'сверху'}», нужно по центру",
                        hint="Выравнивание ячеек по вертикали: по центру.",
                        values={"v_align": v_align or "top"},
                    )  # fmt: skip
                )
        return result_of(self, out)


@register
class Tbl07RowHeight(_TableRule):
    id = "TBL-07"
    title = "Высота строк"
    default_level = "suspicion"
    priority = "should"

    def run(self, ctx: CheckContext):
        limit = ctx.th.ROW_EXACT_MAX_PT
        out: list[Finding] = []
        for t in ctx.doc.tables:
            for r, row in enumerate(t.rows, 1):
                if row.height_rule != "exact" or row.height_twips is None:
                    continue
                pt = row.height_twips / 20
                if pt <= limit:
                    continue
                out.append(
                    new_finding(
                        self,
                        f"{t.number_label(ctx.doc)}: высота строки задана «точно» {fmt_num(pt)} пт "
                        "(строк: {count}).",
                        fingerprint=f"TBL-07|{t.idx}",
                        locations=[ctx.loc.cell(t.idx, r, 1)],
                        method="style",
                        values={"height_pt": pt},
                        hint="Текст может обрезаться: задайте высоту «минимум» или «авто».",
                    )  # fmt: skip
                )
        return result_of(self, out)


@register
class Tbl08KeepNext:
    id = "TBL-08"
    title = "Подпись и строки: «не отрывать от следующего»"
    block = "tables"
    source = SRC
    default_level = "violation"
    needs = frozenset({Need.TABLES})
    priority = "must"
    HEADER_ROWS = 2

    def run(self, ctx: CheckContext):
        doc = ctx.doc
        out: list[Finding] = []
        for t in doc.tables:
            label = t.number_label(doc)
            cap = doc.captions[t.caption_idx] if t.caption_idx is not None else None
            if cap is not None and cap.paragraph_idx is not None:
                keep = doc.paragraph(cap.paragraph_idx).fmt.keep_next
                if keep is None or keep.value is not True:
                    out.append(
                        new_finding(
                            self,
                            f"{label}: у подписи не стоит «не отрывать от следующего».",
                            fingerprint=f"TBL-08|{t.idx}|caption",
                            locations=[ctx.loc.paragraph(cap.paragraph_idx)],
                            method="style",
                            hint="Абзац → Положение на странице → «не отрывать от следующего».",
                        )  # fmt: skip
                    )
            if len(t.rows) > ctx.th.LONG_TABLE_ROWS:
                glued = self._glued_rows(t)
                if glued:
                    out.append(
                        new_finding(
                            self,
                            f"{label}: у строк длинной таблицы «не отрывать от следующего» "
                            f"(строк: {len(glued)}): таблица не разрывается между страницами.",
                            fingerprint=f"TBL-08|{t.idx}|rows",
                            level="suspicion",
                            locations=[ctx.loc.cell(t.idx, glued[0], 1)],
                            method="style",
                            values={"rows": glued[:50]},
                            hint="Снимите флаг со строк, кроме заголовка таблицы.",
                        )  # fmt: skip
                    )
        return result_of(self, out)

    def _glued_rows(self, t: Table) -> list[int]:
        rows = []
        for r, row in enumerate(t.rows, 1):
            if r <= self.HEADER_ROWS:
                continue
            flagged = any(
                p.fmt.keep_next is not None and p.fmt.keep_next.value is True
                for c in row.cells
                for p in c.paragraphs
            )
            if flagged:
                rows.append(r)
        return rows


@register
class Tbl09MissingStyle(_TableRule):
    id = "TBL-09"
    title = "Стиль таблицы существует"

    def run(self, ctx: CheckContext):
        out = []
        for t in ctx.doc.tables:
            if t.style_exists:
                continue
            locs = [ctx.loc.cell(t.idx, 1, 1)] if t.rows and t.rows[0].cells else []
            out.append(
                new_finding(
                    self,
                    f"{t.number_label(ctx.doc)}: стиль «{t.style_id or '?'}» не найден в документе "
                    "(таблица, вероятно, перенесена из другого файла).",
                    fingerprint=f"TBL-09|{t.idx}",
                    locations=locs,
                    method="style",
                    values={"style_id": t.style_id or ""},
                    hint="Примените к таблице стиль этого документа и проверьте её вид.",
                )  # fmt: skip
            )
        return result_of(self, out)
