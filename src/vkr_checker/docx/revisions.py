"""Рецензирование: правки считаются принятыми (ARCHITECTURE.md §6.2, SPEC §3.5).

Текст из w:ins и w:moveTo берётся, w:del / w:moveFrom / w:delText пропускаются. Изменения
форматирования (w:pPrChange, w:rPrChange) игнорируются: читатель берёт только актуальные
w:pPr / w:rPr, а блоки *Change остаются внутри них необработанными. Комментарии - не текст.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal

from lxml import etree

from .xmlutil import MC_ALTERNATE, W_P, choice_children, qn

Event = Literal["run", "simple_start", "simple_end"]

W_R = qn("w:r")
W_DEL = qn("w:del")
W_MOVE_FROM = qn("w:moveFrom")
W_FLD_SIMPLE = qn("w:fldSimple")
W_SDT = qn("w:sdt")
W_SDT_CONTENT = qn("w:sdtContent")
# контейнеры, чьё содержимое - обычный текст абзаца
_TRANSPARENT = {
    qn(t)
    for t in ("w:ins", "w:moveTo", "w:hyperlink", "w:smartTag", "w:customXml", "w:dir", "w:bdo")
}
_REJECTED = {W_DEL, W_MOVE_FROM}

_RUN_TEXT_TAGS = {
    qn("w:tab"): "\t",
    qn("w:noBreakHyphen"): "\u2011",
}
W_BR = qn("w:br")
W_CR = qn("w:cr")
W_T = qn("w:t")


def walk_inline(container: etree._Element) -> Iterator[tuple[Event, etree._Element]]:
    """События содержимого абзаца в порядке документа, без отклонённых правок.

    "run" - w:r; "simple_start"/"simple_end" обрамляют содержимое w:fldSimple.
    """
    for child in container:
        tag = child.tag
        if not isinstance(tag, str) or tag in _REJECTED:
            continue
        if tag == W_R:
            yield "run", child
        elif tag in _TRANSPARENT:
            yield from walk_inline(child)
        elif tag == W_SDT:
            content = child.find(W_SDT_CONTENT)
            if content is not None:
                yield from walk_inline(content)
        elif tag == W_FLD_SIMPLE:
            yield "simple_start", child
            yield from walk_inline(child)
            yield "simple_end", child
        elif tag == MC_ALTERNATE:
            for inner in choice_children(child):
                if inner.tag == W_R:
                    yield "run", inner
                elif inner.tag in _TRANSPARENT:
                    yield from walk_inline(inner)


def child_text(child: etree._Element) -> str:
    """Текст одного дочернего элемента w:r (w:t, табуляция, перенос строки)."""
    tag = child.tag
    if tag == W_T:
        return child.text or ""
    if tag in (W_BR, W_CR):
        return "" if child.get(qn("w:type")) in ("page", "column") else "\n"
    return _RUN_TEXT_TAGS.get(tag) or ""


def run_text(run: etree._Element) -> str:
    """Видимый текст w:r. w:delText, w:instrText и содержимое надписей не входят."""
    return "".join(child_text(c) for c in run)


def _has_child(parent: etree._Element | None, tag: str) -> bool:
    return parent is not None and parent.find(qn(tag)) is not None


def paragraph_mark_deleted(p: etree._Element) -> bool:
    """Знак абзаца удалён правкой: после принятия абзац сливается со следующим."""
    return _has_child(p.find(qn("w:pPr") + "/" + qn("w:rPr")), "w:del")


def paragraph_mark_moved_from(p: etree._Element) -> bool:
    return _has_child(p.find(qn("w:pPr") + "/" + qn("w:rPr")), "w:moveFrom")


def is_paragraph_removed(p: etree._Element) -> bool:
    """Абзац после принятия правок исчезает: знак удалён и видимого текста нет."""
    if not (paragraph_mark_deleted(p) or paragraph_mark_moved_from(p)):
        return False
    if any(run_text(r).strip() for ev, r in walk_inline(p) if ev == "run"):
        return False
    return not any(r.find(qn("w:drawing")) is not None for ev, r in walk_inline(p) if ev == "run")


def row_deleted(tr: etree._Element) -> bool:
    """Строка таблицы удалена правкой (trPr/del): после принятия её нет."""
    return _has_child(tr.find(qn("w:trPr")), "w:del")


def accepted_text(p: etree._Element) -> str:
    """Текст абзаца без учёта полей: принятые правки, без отклонённого."""
    assert p.tag == W_P
    return "".join(run_text(r) for ev, r in walk_inline(p) if ev == "run")
