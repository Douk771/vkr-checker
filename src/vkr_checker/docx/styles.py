"""Эффективное форматирование абзаца (ARCHITECTURE.md §6.3, главный технический риск).

Порядок наложения (поздний перекрывает ранний), у каждого значения хранится источник:
  1. w:docDefaults                              -> origin "defaults"
  2. стиль таблицы: база по basedOn, затем условные w:tblStylePr   -> "table_style"
  3. стиль абзаца по цепочке basedOn (или стиль по умолчанию)      -> "para_style"
  3a. уровень нумерации (numbering_ppr, из B-14)                    -> "para_style"
  4. прямое w:pPr абзаца                                           -> "direct"
Порядок условий таблицы: wholeTable, band1/2Vert, band1/2Horz, firstCol, lastCol, firstRow,
lastRow, nwCell, neCell, swCell, seCell. Допущения: toggle-свойства (b, i) внутри одной цепочки
переопределяются, а между стилем таблицы, абзаца и символа складываются по XOR; autospacing
передаётся как "auto"; размер знака для *Chars и *Lines берётся из эффективного w:sz.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lxml import etree

from vkr_checker.model.document import Origin, ParaFormat, Valued

from .styleprops import CM_PER_PT, attr, parse_ppr, parse_rpr, to_cm, to_pt
from .xmlutil import qn

DEFAULT_FONT_PT = 10.0  # Word без явного w:sz рисует 10 pt
COND_ORDER = (
    "wholeTable", "band1Vert", "band2Vert", "band1Horz", "band2Horz", "firstCol", "lastCol",
    "firstRow", "lastRow", "nwCell", "neCell", "swCell", "seCell",
)  # fmt: skip
_CNF_BITS = (
    "firstRow", "lastRow", "firstCol", "lastCol", "band1Vert", "band2Vert", "band1Horz",
    "band2Horz", "neCell", "nwCell", "seCell", "swCell",
)  # fmt: skip
_CNF_ATTRS = {
    "firstRow": "firstRow", "lastRow": "lastRow", "firstColumn": "firstCol",
    "lastColumn": "lastCol", "oddVBand": "band1Vert", "evenVBand": "band2Vert",
    "oddHBand": "band1Horz", "evenHBand": "band2Horz", "firstRowFirstColumn": "nwCell",
    "firstRowLastColumn": "neCell", "lastRowFirstColumn": "swCell", "lastRowLastColumn": "seCell",
}  # fmt: skip
Layer = dict[str, tuple[Any, Origin]]


@dataclass(frozen=True)
class TableLook:
    first_row: bool = False
    last_row: bool = False
    first_col: bool = False
    last_col: bool = False
    no_hband: bool = False
    no_vband: bool = False


def parse_tbl_look(tbl_pr: etree._Element | None) -> TableLook | None:
    """w:tblLook: атрибуты firstRow... или битовая маска w:val (04A0). None - элемента нет."""
    look = None if tbl_pr is None else tbl_pr.find(qn("w:tblLook"))
    if look is None:
        return None

    def flag(name: str, bit: int) -> bool:
        raw = attr(look, name)
        if raw is not None:
            return raw.strip().lower() not in ("0", "false", "off")
        val = attr(look, "val")
        try:
            return bool(int(val, 16) & bit) if val else False
        except ValueError:
            return False

    return TableLook(
        first_row=flag("firstRow", 0x0020), last_row=flag("lastRow", 0x0040),
        first_col=flag("firstColumn", 0x0080), last_col=flag("lastColumn", 0x0100),
        no_hband=flag("noHBand", 0x0200), no_vband=flag("noVBand", 0x0400),
    )  # fmt: skip


def parse_cnf(*holders: etree._Element | None) -> frozenset[str] | None:
    """w:cnfStyle ячейки/строки/абзаца (первый найденный) -> множество условий."""
    for holder in holders:
        cnf = None if holder is None else holder.find(qn("w:cnfStyle"))
        if cnf is None:
            continue
        found = {n for src, n in _CNF_ATTRS.items() if (attr(cnf, src) or "") in ("1", "true")}
        bits = attr(cnf, "val") or ""
        if len(bits) == 12 and set(bits) <= {"0", "1"}:
            found |= {name for name, b in zip(_CNF_BITS, bits, strict=True) if b == "1"}
        return frozenset(found)
    return None


@dataclass(frozen=True)
class TableContext:
    """Положение абзаца в таблице; row/col с 0, по логической сетке."""

    style_id: str | None
    row: int
    col: int
    n_rows: int
    n_cols: int
    look: TableLook | None = None
    cnf: frozenset[str] | None = None
    row_band_size: int = 1
    col_band_size: int = 1
    tc_pr: etree._Element | None = None

    def conditions(self) -> tuple[str, ...]:
        """Применимые условные форматы в порядке наложения."""
        if self.look is None:
            active = {"wholeTable"} | set(self.cnf or ())
            return tuple(c for c in COND_ORDER if c in active)
        lk = self.look
        first_row = lk.first_row and self.row == 0
        last_row = lk.last_row and self.row == self.n_rows - 1
        first_col = lk.first_col and self.col == 0
        last_col = lk.last_col and self.col == self.n_cols - 1
        active = {"wholeTable"}
        if not lk.no_hband and not first_row and not last_row:
            rel = self.row - (1 if lk.first_row else 0)
            active.add("band1Horz" if (rel // max(self.row_band_size, 1)) % 2 == 0 else "band2Horz")
        if not lk.no_vband and not first_col and not last_col:
            rel = self.col - (1 if lk.first_col else 0)
            active.add("band1Vert" if (rel // max(self.col_band_size, 1)) % 2 == 0 else "band2Vert")
        for cond, on in (("firstCol", first_col), ("lastCol", last_col), ("firstRow", first_row),
                         ("lastRow", last_row)):  # fmt: skip
            if on:
                active.add(cond)
        corners = {
            "nwCell": first_row and first_col, "neCell": first_row and last_col,
            "swCell": last_row and first_col, "seCell": last_row and last_col,
        }  # fmt: skip
        active |= {name for name, on in corners.items() if on}
        return tuple(c for c in COND_ORDER if c in active)


@dataclass(frozen=True)
class ParaResolution:
    fmt: ParaFormat
    contextual_spacing: bool
    font_size_pt: float
    outline_level: int | None
    rprops: Layer  # эффективные свойства знака абзаца: основа для resolve_run


@dataclass(frozen=True)
class RunProps:
    bold: bool
    italic: bool
    size_pt: float
    font: str | None


def _overlay(base: Layer, props: dict[str, Any], origin: Origin) -> None:
    for key, value in props.items():
        base[key] = (value, origin)
        if key in ("b", "i"):  # toggle-свойства нужны по категориям для XOR
            base[f"{key}@{origin}"] = (value, origin)


class StyleSheet:
    def __init__(self, styles_root: etree._Element | None = None) -> None:
        self._styles: dict[str, etree._Element] = {}
        self._defaults_ppr: dict[str, Any] = {}
        self._defaults_rpr: dict[str, Any] = {}
        self._default_para: str | None = None
        self._default_table: str | None = None
        self._cache: dict[tuple, tuple[Layer, Layer]] = {}
        if styles_root is None:
            return
        dd = styles_root.find(qn("w:docDefaults"))
        if dd is not None:
            self._defaults_ppr = parse_ppr(dd.find(qn("w:pPrDefault") + "/" + qn("w:pPr")))
            self._defaults_rpr = parse_rpr(dd.find(qn("w:rPrDefault") + "/" + qn("w:rPr")))
        for st in styles_root.findall(qn("w:style")):
            sid = attr(st, "styleId")
            if not sid:
                continue
            self._styles[sid] = st
            if (attr(st, "default") or "") in ("1", "true"):
                if attr(st, "type") == "paragraph":
                    self._default_para = self._default_para or sid
                elif attr(st, "type") == "table":
                    self._default_table = self._default_table or sid

    # --- справочные ---------------------------------------------------------------------
    def style_exists(self, style_id: str | None) -> bool:
        return style_id is not None and style_id in self._styles

    def style_name(self, style_id: str | None) -> str | None:
        st = self._styles.get(style_id or "")
        return attr(st.find(qn("w:name")), "val") if st is not None else None

    @property
    def default_paragraph_style(self) -> str | None:
        return self._default_para

    def chain(self, style_id: str | None) -> list[etree._Element]:
        """Стили от корня basedOn к листу; циклы и битые ссылки обрываются."""
        result: list[etree._Element] = []
        seen: set[str] = set()
        while style_id and style_id in self._styles and style_id not in seen:
            seen.add(style_id)
            st = self._styles[style_id]
            result.append(st)
            style_id = attr(st.find(qn("w:basedOn")), "val")
        return result[::-1]

    def numpr(self, style_id: str | None) -> tuple[int | None, int | None]:
        """(numId, ilvl) из w:numPr стиля по цепочке basedOn; None - не задано."""
        num_id: int | None = None
        ilvl: int | None = None
        sid = style_id if self.style_exists(style_id) else self._default_para
        for st in self.chain(sid):
            numpr = st.find(qn("w:pPr") + "/" + qn("w:numPr"))
            if numpr is None:
                continue
            nid = attr(numpr.find(qn("w:numId")), "val")
            lvl = attr(numpr.find(qn("w:ilvl")), "val")
            if nid is not None and nid.lstrip("-").isdigit():
                num_id = int(nid)
            if lvl is not None and lvl.isdigit():
                ilvl = int(lvl)
        return num_id, ilvl

    # --- слои -----------------------------------------------------------------------------
    def _table_layer(self, table: TableContext) -> tuple[Layer, Layer]:
        key = ("t", table.style_id, table.conditions())
        if key in self._cache:
            return self._cache[key]
        ppr_layer: Layer = {}
        rpr_layer: Layer = {}
        sid = table.style_id if self.style_exists(table.style_id) else self._default_table
        chain = self.chain(sid)
        for st in chain:
            _overlay(ppr_layer, parse_ppr(st.find(qn("w:pPr"))), "table_style")
            _overlay(rpr_layer, parse_rpr(st.find(qn("w:rPr"))), "table_style")
        for cond in table.conditions():
            for st in chain:
                for sp in st.findall(qn("w:tblStylePr")):
                    if attr(sp, "type") != cond:
                        continue
                    _overlay(ppr_layer, parse_ppr(sp.find(qn("w:pPr")), sp.find(qn("w:tcPr"))),
                             "table_style")  # fmt: skip
                    _overlay(rpr_layer, parse_rpr(sp.find(qn("w:rPr"))), "table_style")
        self._cache[key] = (ppr_layer, rpr_layer)
        return ppr_layer, rpr_layer

    def _para_layer(self, style_id: str | None) -> tuple[Layer, Layer]:
        sid = style_id if self.style_exists(style_id) else self._default_para
        key = ("p", sid)
        if key not in self._cache:
            ppr_layer: Layer = {}
            rpr_layer: Layer = {}
            for st in self.chain(sid):
                _overlay(ppr_layer, parse_ppr(st.find(qn("w:pPr"))), "para_style")
                _overlay(rpr_layer, parse_rpr(st.find(qn("w:rPr"))), "para_style")
            self._cache[key] = (ppr_layer, rpr_layer)
        return self._cache[key]

    # --- абзац ----------------------------------------------------------------------------
    def resolve_paragraph(
        self,
        p: etree._Element,
        table: TableContext | None = None,
        numbering_ppr: etree._Element | None = None,
    ) -> ParaResolution:
        ppr = p.find(qn("w:pPr"))
        style_id = attr(ppr.find(qn("w:pStyle")), "val") if ppr is not None else None
        return self.resolve(ppr, style_id, table, numbering_ppr)

    def resolve(
        self,
        ppr: etree._Element | None,
        style_id: str | None,
        table: TableContext | None = None,
        numbering_ppr: etree._Element | None = None,
    ) -> ParaResolution:
        pl: Layer = {}
        rl: Layer = {}
        _overlay(pl, self._defaults_ppr, "defaults")
        _overlay(rl, self._defaults_rpr, "defaults")
        if table is not None:
            tp, tr = self._table_layer(table)
            pl.update(tp)
            rl.update(tr)
            _overlay(pl, parse_ppr(None, table.tc_pr), "direct")  # vAlign ячейки
        sp, sr = self._para_layer(style_id)
        pl.update(sp)
        rl.update(sr)
        if numbering_ppr is not None:
            _overlay(pl, parse_ppr(numbering_ppr), "para_style")
        _overlay(pl, parse_ppr(ppr), "direct")
        size = rl["size_hp"][0] / 2 if "size_hp" in rl else DEFAULT_FONT_PT
        return ParaResolution(
            fmt=self._to_format(pl, size),
            contextual_spacing=bool(pl.get("contextual", (False,))[0]),
            font_size_pt=size,
            outline_level=pl["outline"][0] if pl.get("outline", (9,))[0] < 9 else None,
            rprops=rl,
        )

    @staticmethod
    def _to_format(pl: Layer, size: float) -> ParaFormat:
        def v(key: str, conv=lambda x: x) -> Valued | None:
            if key not in pl:
                return None
            value, origin = pl[key]
            return Valued(conv(value), origin)

        first = hang = None
        if "first" in pl:
            (kind, num), origin = pl["first"]
            cm = to_cm((kind, abs(num)), size)
            first = Valued(cm if num > 0 else 0.0, origin)
            hang = Valued(cm if num < 0 else 0.0, origin)
        line = v("line")
        if line is not None and pl["line_rule"][0] == "auto":
            line = Valued(round(line.value / 240, 3), line.origin)
        elif line is not None:
            line = Valued(round(line.value / 20, 2), line.origin)
        return ParaFormat(
            first_line_cm=first, hanging_cm=hang,
            left_cm=v("left", lambda x: to_cm(x, size)),
            right_cm=v("right", lambda x: to_cm(x, size)),
            line_spacing=line, line_rule=v("line_rule"),
            space_before_pt=v("before", lambda x: to_pt(x, size)),
            space_after_pt=v("after", lambda x: to_pt(x, size)),
            align=v("jc"), v_align=v("v_align"), keep_next=v("keep_next"),
            keep_lines=v("keep_lines"), page_break_before=v("page_break_before"),
        )  # fmt: skip

    # --- текст ----------------------------------------------------------------------------
    def resolve_run(self, run: etree._Element, base: ParaResolution) -> RunProps:
        """Жирность, курсив, размер и шрифт знака: основа абзаца + стиль символа + прямое w:rPr."""
        rpr = run.find(qn("w:rPr"))
        rstyle = attr(rpr.find(qn("w:rStyle")), "val") if rpr is not None else None
        char: dict[str, Any] = {}
        for st in self.chain(rstyle) if self.style_exists(rstyle) else []:
            char.update(parse_rpr(st.find(qn("w:rPr"))))
        direct = parse_rpr(rpr)
        size_hp = direct.get("size_hp") or char.get("size_hp")
        return RunProps(
            bold=self._toggle("b", base, char, direct),
            italic=self._toggle("i", base, char, direct),
            size_pt=size_hp / 2 if size_hp else base.font_size_pt,
            font=direct.get("font") or char.get("font") or base.rprops.get("font", (None,))[0],
        )

    @staticmethod
    def _toggle(key: str, base: ParaResolution, char: dict, direct: dict) -> bool:
        if key in direct:
            return bool(direct[key])
        votes = [
            bool(base.rprops[f"{key}@{cat}"][0])
            for cat in ("table_style", "para_style")
            if f"{key}@{cat}" in base.rprops
        ]
        if key in char:
            votes.append(bool(char[key]))
        if votes:
            return sum(votes) % 2 == 1
        return bool(base.rprops.get(f"{key}@defaults", (False,))[0])


__all__ = [
    "CM_PER_PT", "COND_ORDER", "ParaResolution", "RunProps", "StyleSheet", "TableContext",
    "TableLook", "parse_cnf", "parse_tbl_look",
]  # fmt: skip
