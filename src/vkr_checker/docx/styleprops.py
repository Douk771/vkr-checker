"""Разбор свойств w:pPr / w:rPr / w:tcPr одного слоя каскада в плоский словарь.

Слой - это один источник свойств (docDefaults, стиль, прямое форматирование). Словарь содержит
только то, что слой задаёт явно; наложение слоёв делает styles.py.

Ключи pPr: left, right, first (группы отступов: ("twips"|"chars", число); first со знаком:
firstLine > 0, hanging < 0), line (число), line_rule, before, after (("twips"|"lines"|"auto",
число)), jc, keep_next, keep_lines, page_break_before, contextual, outline, v_align.
Ключи rPr: size_hp, font, b, i (toggle-свойства).
"""

from __future__ import annotations

import math
from typing import Any

from lxml import etree

from .xmlutil import qn

TWIPS_PER_PT = 20
CM_PER_PT = 2.54 / 72
CM_PER_TWIP = 2.54 / 1440
_OFF = {"0", "false", "off", "no"}
_JC = {"left": "left", "start": "left", "right": "right", "end": "right", "center": "center",
       "both": "justify", "distribute": "justify", "justify": "justify"}  # fmt: skip


def attr(el: etree._Element | None, name: str) -> str | None:
    return None if el is None else el.get(qn(f"w:{name}"))


def on_off(el: etree._Element | None) -> bool | None:
    """Элемент-переключатель (w:keepNext, w:b): нет элемента -> None; w:val по умолчанию true."""
    if el is None:
        return None
    val = attr(el, "val")
    return not (val is not None and val.strip().lower() in _OFF)


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _indent_group(
    ind: etree._Element, plain: tuple[str, ...], chars: str
) -> tuple[str, float] | None:
    ch = _num(attr(ind, chars))
    if ch is not None:
        return ("chars", ch)
    for name in plain:
        v = _num(attr(ind, name))
        if v is not None:
            return ("twips", v)
    return None


def _parse_ind(ind: etree._Element, out: dict[str, Any]) -> None:
    left = _indent_group(ind, ("left", "start"), "leftChars") or _indent_group(
        ind, ("start",), "startChars"
    )
    if left:
        out["left"] = left
    right = _indent_group(ind, ("right", "end"), "rightChars") or _indent_group(
        ind, ("end",), "endChars"
    )
    if right:
        out["right"] = right
    # hanging приоритетнее firstLine; формы *Chars приоритетнее абсолютных
    hang = _indent_group(ind, ("hanging",), "hangingChars")
    if hang:
        out["first"] = (hang[0], -hang[1])
        return
    first = _indent_group(ind, ("firstLine",), "firstLineChars")
    if first:
        out["first"] = first


def _spacing_value(sp: etree._Element, name: str) -> tuple[str, float] | None:
    auto = attr(sp, f"{name}Autospacing")
    if auto is not None and auto.strip().lower() not in _OFF:
        return ("auto", 0.0)
    lines = _num(attr(sp, f"{name}Lines"))
    if lines is not None:
        return ("lines", lines)
    twips = _num(attr(sp, name))
    return ("twips", twips) if twips is not None else None


def _parse_spacing(sp: etree._Element, out: dict[str, Any]) -> None:
    for name in ("before", "after"):
        v = _spacing_value(sp, name)
        if v:
            out[name] = v
    line = _num(attr(sp, "line"))
    rule = attr(sp, "lineRule")
    if line is not None:
        out["line"] = line
        out["line_rule"] = rule or "auto"
    elif rule:
        out["line_rule"] = rule


def parse_ppr(ppr: etree._Element | None, tcpr: etree._Element | None = None) -> dict[str, Any]:
    """Свойства абзаца из w:pPr (и vAlign из w:tcPr). w:pPrChange игнорируется."""
    out: dict[str, Any] = {}
    if ppr is not None:
        ind = ppr.find(qn("w:ind"))
        if ind is not None:
            _parse_ind(ind, out)
        sp = ppr.find(qn("w:spacing"))
        if sp is not None:
            _parse_spacing(sp, out)
        jc = attr(ppr.find(qn("w:jc")), "val")
        if jc in _JC:
            out["jc"] = _JC[jc]
        for key, tag in (
            ("keep_next", "w:keepNext"),
            ("keep_lines", "w:keepLines"),
            ("page_break_before", "w:pageBreakBefore"),
            ("contextual", "w:contextualSpacing"),
        ):
            v = on_off(ppr.find(qn(tag)))
            if v is not None:
                out[key] = v
        lvl = _num(attr(ppr.find(qn("w:outlineLvl")), "val"))
        if lvl is not None:
            out["outline"] = int(lvl)
    va = attr(tcpr.find(qn("w:vAlign")), "val") if tcpr is not None else None
    if va in ("top", "center", "bottom"):
        out["v_align"] = va
    return out


def parse_rpr(rpr: etree._Element | None) -> dict[str, Any]:
    """Свойства текста из w:rPr. w:rPrChange игнорируется."""
    out: dict[str, Any] = {}
    if rpr is None:
        return out
    sz = _num(attr(rpr.find(qn("w:sz")), "val"))
    if sz is not None:
        out["size_hp"] = sz
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is not None:
        name = attr(fonts, "ascii") or attr(fonts, "hAnsi")
        if name:
            out["font"] = name
    for key, tag in (("b", "w:b"), ("i", "w:i")):
        v = on_off(rpr.find(qn(tag)))
        if v is not None:
            out[key] = v
    return out


def to_cm(kind_value: tuple[str, float], size_pt: float) -> float:
    """Отступ в см. "chars" - сотые доли знака; знак приравнивается к размеру шрифта."""
    kind, value = kind_value
    if kind == "chars":
        return round(value / 100 * size_pt * CM_PER_PT, 4)
    return round(value * CM_PER_TWIP, 4)


def to_pt(kind_value: tuple[str, float], size_pt: float) -> float | str:
    """Интервал в pt или "auto". "lines" - сотые доли строки, строка ~ размеру шрифта."""
    kind, value = kind_value
    if kind == "auto":
        return "auto"
    if kind == "lines":
        return round(value / 100 * size_pt, 2)
    return round(value / TWIPS_PER_PT, 2)
