"""Эталон и мутации: clean() и по одной мутации на пункт правила (ARCHITECTURE_TASKS.md §3)."""

from __future__ import annotations

from docx.shared import Cm

from .base import ThesisBuilder

TABLE_ROWS = [["Показатель", "Группа 1", "Группа 2"], ["M", "12,4", "13,1"], ["SD", "2,1", "2,4"]]


def clean(
    pages_main: float = 70, *, seed: int = 1, skip: frozenset[str] = frozenset()
) -> ThesisBuilder:
    """Эталон: все разделы, 2 главы, таблицы, рисунки, приложение. Ожидание: 0 Н и 0 П.

    `skip` - имена разделов, которые не создаются (INTRO, CONCLUSION, BIBLIOGRAPHY, APPENDIX):
    основа для мутаций вида «нет заключения».
    """
    b = ThesisBuilder(seed)
    b.title_page()
    b.toc([("ВВЕДЕНИЕ", 3), ("ГЛАВА 1", 6), ("ГЛАВА 2", 30), ("ЗАКЛЮЧЕНИЕ", 70)])
    if "INTRO" not in skip:
        b.intro(pages=3)
    per_chapter = (pages_main - 5) / 2
    b.chapter(1, "Теоретические основы", ["Понятие мотивации", "Подходы к адаптации"],
              pages=per_chapter * 0.9)  # fmt: skip
    b.table(TABLE_ROWS, "Описательные статистики").figure("Схема исследования")
    b.chapter(2, "Эмпирическое исследование", ["Организация и методы исследования", "Результаты"],
              pages=per_chapter * 0.9)  # fmt: skip
    b.table(TABLE_ROWS, "Сравнение групп")
    if "CONCLUSION" not in skip:
        b.conclusion()
    if "BIBLIOGRAPHY" not in skip:
        b.bibliography()
    if "APPENDIX" not in skip:
        b.appendix("1")
    return b


def missing_section(kind: str, pages_main: float = 20) -> ThesisBuilder:
    """Мутация STR-01: раздела нет (INTRO | CONCLUSION | BIBLIOGRAPHY | APPENDIX)."""
    return clean(pages_main, skip=frozenset({kind}))


def table_indent(pages_main: float = 20, cm: float = 1.25) -> ThesisBuilder:
    """Мутация TBL-01: красная строка в ячейках таблиц (прямое форматирование)."""
    b = clean(pages_main)
    for table in b.doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.first_line_indent = Cm(cm)
    return b
