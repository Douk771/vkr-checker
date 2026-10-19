"""Свойства таблицы из XML: сетка, ширины, объединения (ARCHITECTURE.md §6.5)."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from vkr_checker.model.document import Row

from .revisions import row_deleted
from .xmlutil import qn, w_attr

CM_PER_TWIP = 2.54 / 1440


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def twips_to_cm(twips: int | float | None) -> float | None:
    return None if twips is None else round(twips * CM_PER_TWIP, 3)


@dataclass(frozen=True)
class TableProps:
    style_id: str | None
    grid_cols_cm: tuple[float, ...]
    width_cm: float | None
    width_type: str
    layout_type: str
    row_band_size: int
    col_band_size: int
    tbl_pr: etree._Element | None


def read_table_props(tbl: etree._Element) -> TableProps:
    pr = tbl.find(qn("w:tblPr"))
    style = pr.find(qn("w:tblStyle")) if pr is not None else None
    tbl_w = pr.find(qn("w:tblW")) if pr is not None else None
    layout = pr.find(qn("w:tblLayout")) if pr is not None else None
    width_type = "auto"
    width_cm = None
    if tbl_w is not None:
        kind = w_attr(tbl_w, "type") or "auto"
        value = _int(w_attr(tbl_w, "w"))
        if kind == "dxa" and value:
            width_type, width_cm = "dxa", twips_to_cm(value)
        elif kind == "pct":
            width_type = "pct"
    grid = tbl.find(qn("w:tblGrid"))
    cols = []
    if grid is not None:
        for col in grid.findall(qn("w:gridCol")):
            cols.append(twips_to_cm(_int(w_attr(col, "w")) or 0) or 0.0)

    def band(tag: str) -> int:
        el = pr.find(qn(tag)) if pr is not None else None
        return max(_int(w_attr(el, "val")) or 1, 1) if el is not None else 1

    return TableProps(
        style_id=w_attr(style, "val") if style is not None else None,
        grid_cols_cm=tuple(cols),
        width_cm=width_cm,
        width_type=width_type,
        layout_type="fixed"
        if layout is not None and w_attr(layout, "type") == "fixed"
        else "autofit",
        row_band_size=band("w:tblStyleRowBandSize"),
        col_band_size=band("w:tblStyleColBandSize"),
        tbl_pr=pr,
    )


def live_rows(tbl: etree._Element) -> list[etree._Element]:
    """Строки таблицы после принятия правок (удалённые строки пропущены)."""
    return [tr for tr in tbl.findall(qn("w:tr")) if not row_deleted(tr)]


def cell_elements(tr: etree._Element) -> list[etree._Element]:
    """w:tc строки, включая лежащие внутри w:sdt."""
    result: list[etree._Element] = []
    for child in tr:
        if child.tag == qn("w:tc"):
            result.append(child)
        elif child.tag == qn("w:sdt"):
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                result.extend(content.findall(qn("w:tc")))
    return result


def grid_span(tc: etree._Element) -> int:
    pr = tc.find(qn("w:tcPr"))
    span = pr.find(qn("w:gridSpan")) if pr is not None else None
    return max(_int(w_attr(span, "val")) or 1, 1) if span is not None else 1


def v_merge(tc: etree._Element) -> str | None:
    pr = tc.find(qn("w:tcPr"))
    vm = pr.find(qn("w:vMerge")) if pr is not None else None
    if vm is None:
        return None
    return "restart" if w_attr(vm, "val") == "restart" else "continue"


def cell_width_cm(tc: etree._Element) -> float | None:
    pr = tc.find(qn("w:tcPr"))
    w = pr.find(qn("w:tcW")) if pr is not None else None
    if w is not None and w_attr(w, "type") in (None, "dxa"):
        return twips_to_cm(_int(w_attr(w, "w")))
    return None


def row_props(tr: etree._Element, cells: tuple) -> Row:
    pr = tr.find(qn("w:trPr"))
    height = pr.find(qn("w:trHeight")) if pr is not None else None
    return Row(
        cells=cells,
        height_twips=_int(w_attr(height, "val")) if height is not None else None,
        height_rule=(w_attr(height, "hRule") or "atLeast") if height is not None else None,
        cant_split=pr is not None and pr.find(qn("w:cantSplit")) is not None,
    )


def section_page_setup(sect: etree._Element, section_idx: int):
    """PageSetup из w:sectPr: поля и ширина текста (с учётом переплёта)."""
    from vkr_checker.model.document import PageSetup

    size = sect.find(qn("w:pgSz"))
    mar = sect.find(qn("w:pgMar"))

    def twips(el, name):
        return _int(w_attr(el, name)) if el is not None else None

    page_w, left, right = twips(size, "w"), twips(mar, "left"), twips(mar, "right")
    gutter = twips(mar, "gutter") or 0
    text_w = None
    if page_w and left is not None and right is not None:
        text_w = twips_to_cm(page_w - left - right - gutter)
    return PageSetup(
        section_idx=section_idx,
        margin_left_cm=twips_to_cm(left),
        margin_right_cm=twips_to_cm(right),
        margin_top_cm=twips_to_cm(twips(mar, "top")),
        margin_bottom_cm=twips_to_cm(twips(mar, "bottom")),
        text_width_cm=text_w,
    )
