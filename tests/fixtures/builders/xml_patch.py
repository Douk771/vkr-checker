"""lxml-патчи для конструкций, которых нет в python-docx (ARCHITECTURE_TASKS.md §3).

Волна 1: поле SEQ/TOC со стороной «сохранённый результат» и разрыв страницы.
Остальное (numbering, tblStylePr, рецензирование, надписи) добавляется вместе с B-12..B-15.
"""

from __future__ import annotations

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


def _fld_char(kind: str):
    run = OxmlElement("w:r")
    ch = OxmlElement("w:fldChar")
    ch.set(qn("w:fldCharType"), kind)
    run.append(ch)
    return run


def add_complex_field(paragraph: Paragraph, instruction: str, result: str) -> None:
    """Составное поле: begin -> instrText -> separate -> результат -> end (результат сохранён)."""
    p = paragraph._p
    p.append(_fld_char("begin"))
    instr_run = OxmlElement("w:r")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    instr_run.append(instr)
    p.append(instr_run)
    p.append(_fld_char("separate"))
    res_run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.set(qn("xml:space"), "preserve")
    text.text = result
    res_run.append(text)
    p.append(res_run)
    p.append(_fld_char("end"))


def add_page_break_before(paragraph: Paragraph) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    ppr.append(OxmlElement("w:pageBreakBefore"))
