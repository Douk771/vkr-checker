"""Безопасный разбор XML и обход тела .docx (ARCHITECTURE.md §6.1)."""

from __future__ import annotations

from collections.abc import Iterator

from lxml import etree

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "v": "urn:schemas-microsoft-com:vml",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

W_P = f"{{{NS['w']}}}p"
W_TBL = f"{{{NS['w']}}}tbl"
W_SDT = f"{{{NS['w']}}}sdt"
W_SDT_CONTENT = f"{{{NS['w']}}}sdtContent"
W_TXBX_CONTENT = f"{{{NS['w']}}}txbxContent"
MC_ALTERNATE = f"{{{NS['mc']}}}AlternateContent"
MC_CHOICE = f"{{{NS['mc']}}}Choice"
MC_FALLBACK = f"{{{NS['mc']}}}Fallback"


def qn(tag: str) -> str:
    """'w:p' -> '{ns}p'."""
    prefix, _, local = tag.partition(":")
    return f"{{{NS[prefix]}}}{local}"


def safe_parser() -> etree.XMLParser:
    """Без сущностей, сети и огромных деревьев (защита от XXE и billion laughs)."""
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        load_dtd=False,
        dtd_validation=False,
        remove_comments=True,
        remove_pis=True,
    )


class XmlParseError(ValueError):
    """XML части не разобрался или содержит запрещённые конструкции."""


def parse_xml(data: bytes) -> etree._Element:
    if b"<!ENTITY" in data or b"<!DOCTYPE" in data:
        raise XmlParseError("DTD и объявления сущностей в .docx не допускаются")
    try:
        return etree.fromstring(data, safe_parser())
    except etree.XMLSyntaxError as exc:
        raise XmlParseError("XML повреждён") from exc


def w_attr(el: etree._Element, name: str, default: str | None = None) -> str | None:
    """Значение атрибута w:<name>."""
    return el.get(f"{{{NS['w']}}}{name}", default)


def choice_children(alt: etree._Element) -> list[etree._Element]:
    """Содержимое mc:AlternateContent: только mc:Choice, иначе Fallback (иначе двойной подсчёт)."""
    for child in alt:
        if child.tag == MC_CHOICE:
            return list(child)
    for child in alt:
        if child.tag == MC_FALLBACK:
            return list(child)
    return []


def iter_body_blocks(container: etree._Element) -> Iterator[etree._Element]:
    """Блоки тела (w:p, w:tbl) в порядке документа.

    w:sdt раскрывается (в нём часто лежит оглавление), mc:AlternateContent на уровне блоков
    даёт только Choice.
    """
    for child in container:
        tag = child.tag
        if tag in (W_P, W_TBL):
            yield child
        elif tag == W_SDT:
            content = child.find(W_SDT_CONTENT)
            if content is not None:
                yield from iter_body_blocks(content)
        elif tag == MC_ALTERNATE:
            for inner in choice_children(child):
                if inner.tag in (W_P, W_TBL):
                    yield inner
                elif inner.tag == W_SDT:
                    content = inner.find(W_SDT_CONTENT)
                    if content is not None:
                        yield from iter_body_blocks(content)


def iter_descendants(
    el: etree._Element, *, enter_textboxes: bool = False
) -> Iterator[etree._Element]:
    """Потомки в порядке документа с учётом AlternateContent (Choice вместо обоих веток).

    Содержимое w:txbxContent по умолчанию не заходится: надписи собираются отдельно
    через `textbox_contents`.
    """
    for child in el:
        if not isinstance(child.tag, str):
            continue
        if child.tag == MC_ALTERNATE:
            for inner in choice_children(child):
                yield inner
                yield from iter_descendants(inner, enter_textboxes=enter_textboxes)
            continue
        yield child
        if child.tag == W_TXBX_CONTENT and not enter_textboxes:
            continue
        yield from iter_descendants(child, enter_textboxes=enter_textboxes)


def textbox_contents(el: etree._Element) -> list[etree._Element]:
    """Корневые w:txbxContent внутри элемента (без вложенных надписей), только по ветке Choice."""
    return [d for d in iter_descendants(el) if d.tag == W_TXBX_CONTENT]


def textbox_paragraphs(el: etree._Element) -> list[etree._Element]:
    """Абзацы надписей элемента; вложенные таблицы надписи раскрываются в абзацы ячеек."""
    result: list[etree._Element] = []
    for content in textbox_contents(el):
        result.extend(p for p in content.iter(W_P))
    return result
