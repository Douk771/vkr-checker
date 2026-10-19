"""Автонумерация абзацев (ARCHITECTURE.md §6.4, SPEC §6 п.3).

NumberingResolver вызывается для абзацев строго в порядке документа: счётчики ведутся по
abstractNumId (разные numId над одним abstractNum продолжают счёт, если нет startOverride),
более глубокие уровни сбрасываются при выходе на верхний (учитывается lvlRestart).
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from .styleprops import attr
from .styles import StyleSheet
from .xmlutil import qn

RU_LOWER = "абвгдежзиклмнопрстуфхцчшщэюя"
LATIN = "abcdefghijklmnopqrstuvwxyz"
ROMAN = (
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
    (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
)  # fmt: skip


MAX_WORD_NUMBER = 32767  # верхняя граница значений нумерации в Word


def _clamp_number(n: int) -> int:
    return max(0, min(n, MAX_WORD_NUMBER))


def _letters(n: int, alphabet: str) -> str:
    """Word: a..z, aa..zz, aaa..: буква повторяется."""
    n = max(min(n, MAX_WORD_NUMBER), 1)
    return alphabet[(n - 1) % len(alphabet)] * ((n - 1) // len(alphabet) + 1)


def _roman(n: int) -> str:
    n = _clamp_number(n)
    out = []
    for value, sym in ROMAN:
        while n >= value:
            out.append(sym)
            n -= value
    return "".join(out) or "0"


KNOWN_FORMATS = {
    "decimal", "decimalZero", "russianLower", "russianUpper", "lowerLetter", "upperLetter",
    "lowerRoman", "upperRoman", "bullet", "none",
}  # fmt: skip


def format_number(n: int, fmt: str) -> str:
    n = _clamp_number(n)
    if fmt == "decimalZero":
        return f"{n:02d}"
    if fmt == "russianLower":
        return _letters(n, RU_LOWER)
    if fmt == "russianUpper":
        return _letters(n, RU_LOWER).upper()
    if fmt == "lowerLetter":
        return _letters(n, LATIN)
    if fmt == "upperLetter":
        return _letters(n, LATIN).upper()
    if fmt == "lowerRoman":
        return _roman(n)
    if fmt == "upperRoman":
        return _roman(n).upper()
    return str(n)


@dataclass(frozen=True)
class NumberingResult:
    label: str | None  # None для маркеров и numFmt=none
    is_list_item: bool
    num_id: int
    ilvl: int
    num_fmt: str
    level_ppr: etree._Element | None = None  # w:pPr уровня (отступы) для styles.resolve


@dataclass
class _Level:
    start: int = 1
    fmt: str = "decimal"
    text: str = ""
    restart: int | None = None  # lvlRestart: None - по умолчанию; 0 - никогда
    is_legal: bool = False
    ppr: etree._Element | None = None
    p_style: str | None = None


def _int(value: str | None, default: int | None = None) -> int | None:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


class NumberingResolver:
    def __init__(self, numbering_root: etree._Element | None, styles: StyleSheet | None = None):
        self.styles = styles or StyleSheet()
        self.warnings: list[str] = []
        self._abstract: dict[int, etree._Element] = {}
        self._num: dict[int, etree._Element] = {}
        self._counters: dict[int, dict[int, int]] = {}
        self._started: set[tuple[int, int]] = set()
        self._warned: set[str] = set()
        if numbering_root is None:
            return
        for a in numbering_root.findall(qn("w:abstractNum")):
            aid = _int(attr(a, "abstractNumId"))
            if aid is not None:
                self._abstract[aid] = a
        for n in numbering_root.findall(qn("w:num")):
            nid = _int(attr(n, "numId"))
            if nid is not None:
                self._num[nid] = n

    def _warn(self, text: str) -> None:
        if text not in self._warned:
            self._warned.add(text)
            self.warnings.append(text)

    # --- определения ----------------------------------------------------------------------
    def _abstract_id(self, num_id: int) -> int | None:
        num = self._num.get(num_id)
        if num is None:
            self._warn(f"нумерация: список numId={num_id} не определён")
            return None
        aid = _int(attr(num.find(qn("w:abstractNumId")), "val"))
        seen: set[int] = set()
        while aid is not None and aid in self._abstract and aid not in seen:
            seen.add(aid)
            link = attr(self._abstract[aid].find(qn("w:numStyleLink")), "val")
            if not link:
                return aid
            linked_num, _ = self.styles.numpr(link)
            if linked_num is None or linked_num not in self._num:
                self._warn(f"нумерация: не разрешена ссылка numStyleLink={link}")
                return aid
            aid = _int(attr(self._num[linked_num].find(qn("w:abstractNumId")), "val"))
        if aid is None or aid not in self._abstract:
            self._warn(f"нумерация: abstractNum для numId={num_id} не найден")
            return None
        return aid

    def _level(self, num_id: int, aid: int, ilvl: int) -> _Level:
        node = None
        num = self._num.get(num_id)
        if num is not None:
            for ov in num.findall(qn("w:lvlOverride")):
                if _int(attr(ov, "ilvl")) == ilvl and ov.find(qn("w:lvl")) is not None:
                    node = ov.find(qn("w:lvl"))
        if node is None:
            for lvl in self._abstract[aid].findall(qn("w:lvl")):
                if _int(attr(lvl, "ilvl")) == ilvl:
                    node = lvl
                    break
        if node is None:
            self._warn(f"нумерация: уровень {ilvl} не определён в abstractNumId={aid}")
            return _Level(text=f"%{ilvl + 1}.")
        fmt = attr(node.find(qn("w:numFmt")), "val") or "decimal"
        if fmt not in KNOWN_FORMATS:
            self._warn(f"нумерация: формат {fmt} не поддерживается, показан как decimal")
        if node.find(qn("w:legacy")) is not None:
            self._warn("нумерация: w:legacy, метка определена по лучшей догадке")
        return _Level(
            start=self._bounded(_int(attr(node.find(qn("w:start")), "val"), 1) or 0, "w:start"),
            fmt=fmt,
            text=attr(node.find(qn("w:lvlText")), "val") or "",
            restart=_int(attr(node.find(qn("w:lvlRestart")), "val")),
            is_legal=node.find(qn("w:isLgl")) is not None,
            ppr=node.find(qn("w:pPr")),
            p_style=attr(node.find(qn("w:pStyle")), "val"),
        )

    def _bounded(self, value: int, what: str) -> int:
        if 0 <= value <= MAX_WORD_NUMBER:
            return value
        self._warn(f"нумерация: {what}={value} вне диапазона 0..{MAX_WORD_NUMBER}, значение ограничено")
        return _clamp_number(value)

    def _start_override(self, num_id: int, ilvl: int) -> int | None:
        num = self._num.get(num_id)
        if num is None:
            return None
        for ov in num.findall(qn("w:lvlOverride")):
            if _int(attr(ov, "ilvl")) == ilvl:
                value = _int(attr(ov.find(qn("w:startOverride")), "val"))
                return None if value is None else self._bounded(value, "w:startOverride")
        return None

    # --- numPr абзаца ---------------------------------------------------------------------
    def _effective_numpr(self, ppr: etree._Element | None) -> tuple[int | None, int]:
        style_id = attr(ppr.find(qn("w:pStyle")), "val") if ppr is not None else None
        s_num, s_lvl = self.styles.numpr(style_id)
        numpr = ppr.find(qn("w:numPr")) if ppr is not None else None
        d_num = _int(attr(numpr.find(qn("w:numId")), "val")) if numpr is not None else None
        d_lvl = _int(attr(numpr.find(qn("w:ilvl")), "val")) if numpr is not None else None
        num_id = d_num if d_num is not None else s_num
        if d_lvl is not None:
            return num_id, d_lvl
        if s_lvl is not None:
            return num_id, s_lvl
        if num_id and num_id in self._num and (a := self._abstract_id(num_id)) is not None:
            for lvl in self._abstract[a].findall(qn("w:lvl")):
                if style_id and attr(lvl.find(qn("w:pStyle")), "val") == style_id:
                    return num_id, _int(attr(lvl, "ilvl"), 0) or 0
        return num_id, 0

    # --- метка ----------------------------------------------------------------------------
    def label(self, ppr: etree._Element | None) -> NumberingResult | None:
        """Метка абзаца по его w:pPr; None - абзац не нумерован. Вызывать в порядке документа."""
        num_id, ilvl = self._effective_numpr(ppr)
        if not num_id:  # None или 0: нумерации нет
            return None
        aid = self._abstract_id(num_id)
        if aid is None:
            return None
        level = self._level(num_id, aid, ilvl)
        counters = self._counters.setdefault(aid, {})
        key = (num_id, ilvl)
        override = self._start_override(num_id, ilvl)
        if key not in self._started:
            self._started.add(key)
            if override is not None:
                counters[ilvl] = override - 1
        counters[ilvl] = counters.get(ilvl, level.start - 1) + 1
        self._reset_deeper(num_id, aid, ilvl, counters)
        if level.fmt == "bullet":
            return NumberingResult(None, True, num_id, ilvl, level.fmt, level.ppr)
        if level.fmt == "none":
            return NumberingResult(None, False, num_id, ilvl, level.fmt, level.ppr)
        text = self._render(num_id, aid, level, counters)
        return NumberingResult(text or None, True, num_id, ilvl, level.fmt, level.ppr)

    def _reset_deeper(self, num_id: int, aid: int, ilvl: int, counters: dict[int, int]) -> None:
        for deeper in [m for m in counters if m > ilvl]:
            restart = self._level(num_id, aid, deeper).restart
            if restart is None or (restart > 0 and ilvl <= restart - 1):
                del counters[deeper]

    def _render(self, num_id: int, aid: int, level: _Level, counters: dict[int, int]) -> str:
        out = level.text
        for n in range(9, 0, -1):  # %9 .. %1: сначала длинные, чтобы не задеть %1x
            token = f"%{n}"
            if token not in out:
                continue
            ref = self._level(num_id, aid, n - 1)
            value = counters.get(n - 1, ref.start)
            fmt = "decimal" if level.is_legal else ref.fmt
            out = out.replace(token, format_number(value, fmt))
        return out.strip()
