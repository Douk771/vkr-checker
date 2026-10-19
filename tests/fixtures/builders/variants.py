"""Эталон и мутации: clean() и по одной мутации на пункт правила (ARCHITECTURE_TASKS.md §3)."""

from __future__ import annotations

from docx.shared import Cm

from .base import NB, ThesisBuilder

TABLE_ROWS = [
    ["Показатель", "Группа 1", "Группа 2"],
    ["Среднее значение (M)", "12,4", "13,1"],
    ["Стандартное отклонение", "2,1", "2,4"],
]


def clean(
    pages_main: float = 70, *, seed: int = 1, skip: frozenset[str] = frozenset()
) -> ThesisBuilder:
    """Эталон: все разделы, 2 главы, таблицы, рисунки, приложение. Ожидание: 0 Н и 0 П.

    `skip` - имена разделов, которые не создаются (INTRO, CONCLUSION, BIBLIOGRAPHY, APPENDIX):
    основа для мутаций вида «нет заключения».
    """
    b = ThesisBuilder(seed)
    b.title_page()
    b.toc([
        ("ВВЕДЕНИЕ", 3),
        ("ГЛАВА 1. Теоретические основы", 6),
        ("1.1. Понятие мотивации", 6),
        ("1.2. Подходы к адаптации", 12),
        ("Выводы по главе 1", 28),
        ("ГЛАВА 2. Эмпирическое исследование", 30),
        ("2.1. Организация и методы исследования", 30),
        ("2.2. Результаты", 50),
        ("Выводы по главе 2", 68),
        ("ЗАКЛЮЧЕНИЕ", 70),
        ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 72),
        ("ПРИЛОЖЕНИЕ А", 74),
    ])  # fmt: skip
    if "INTRO" not in skip:
        b.intro(pages=3, full=True)
    per_chapter = (pages_main - 5) / 2
    b.chapter(1, "Теоретические основы", ["Понятие мотивации", "Подходы к адаптации"],
              pages=per_chapter * 0.9, lead={1: [
                  "Шкала учебной мотивации описана в литературе как инструмент диагностики.",
                  "Подход С.Л. Рубинштейна и А.Н. Леонтьева рассматривает мотивацию как систему."
              ]})  # fmt: skip
    b.para("Схема исследования показана на рисунке 1; описательные статистики даны в таблице 1, "
           "полные данные приведены в приложении А.")  # fmt: skip
    b.table(TABLE_ROWS, "Описательные статистики", conformant=True)
    b.figure("Схема исследования")
    b.chapter_conclusions(1)
    b.chapter(2, "Эмпирическое исследование", ["Организация и методы исследования", "Результаты"],
              pages=per_chapter * 0.9, lead={
                  1: ["Применялись коэффициент корреляции Спирмена и методика «Шкала учебной "
                      "мотивации»."],
                  2: [f"Выявлена положительная связь мотивации и адаптации "
                      f"(rs{NB}={NB}0,45; p{NB}<{NB}0,01). Гипотеза о том, что учебная мотивация "
                      f"студентов положительно связана с уровнем академической адаптации, "
                      f"подтверждена."],
              })  # fmt: skip
    b.para("Сравнение групп приведено в таблице 2, полные данные приведены в приложении А.")
    b.table(TABLE_ROWS, "Сравнение групп", conformant=True)
    b.chapter_conclusions(2)
    if "CONCLUSION" not in skip:
        b.conclusion(hypothesis=True)
    if "BIBLIOGRAPHY" not in skip:
        b.bibliography()
    if "APPENDIX" not in skip:
        b.appendix("А")
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
