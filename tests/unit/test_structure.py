from vkr_checker.model.document import (
    Cell,
    DocMeta,
    Document,
    FieldRef,
    ParaFormat,
    Paragraph,
    Row,
    RunInfo,
    Table,
    Valued,
)
from vkr_checker.structure import analyze_structure


def doc_of(items, tables=(), fields=()):
    """items: строки или (текст, kwargs Paragraph); таблица - маркер ('TABLE',)."""
    paras, blocks, tbls = [], [], []
    for it in items:
        if it == ("TABLE",):
            t = Table(
                idx=len(tbls) + 1,
                rows=(Row(cells=(Cell(row=1, col=1, text="x"),)),),
                prev_paragraph_idx=len(paras) or None,
            )
            tbls.append(t)
            blocks.append(t)
            continue
        text, kw = (it, {}) if isinstance(it, str) else it
        p = Paragraph(idx=len(paras) + 1, text=text, **kw)
        paras.append(p)
        blocks.append(p)
    return Document(
        meta=DocMeta("t.docx", "0" * 64), paragraphs=tuple(paras), blocks=tuple(blocks),
        tables=tuple(tbls), fields=tuple(fields),
    )  # fmt: skip


def H(text, level=1):
    return (text, dict(outline_level=level - 1, style_name=f"heading {level}"))


def kinds(doc):
    return [(s.kind, s.number) for s in doc.sections]


def test_styled_headings_and_tree():
    doc = analyze_structure(
        doc_of(
            [
                "Титул",
                H("ВВЕДЕНИЕ"), "текст",
                H("ГЛАВА 1. Теоретические основы"), H("1.1. Подход", 2), "текст",
                H("ГЛАВА 2. Эмпирическое исследование"), H("2.1. Методы", 2),
                H("ЗАКЛЮЧЕНИЕ"), H("СПИСОК ЛИТЕРАТУРЫ"),
            ]
        )
    )  # fmt: skip
    assert kinds(doc) == [
        ("TITLE", None), ("INTRO", None), ("CHAPTER", "1"), ("SUBSECTION", "1.1"),
        ("CHAPTER", "2"), ("SUBSECTION", "2.1"), ("CONCLUSION", None), ("BIBLIOGRAPHY", None),
    ]  # fmt: skip
    sub = doc.sections[3]
    assert sub.parent_id == doc.sections[2].id
    assert doc.sections[2].role_hint == "theoretical" and doc.sections[4].role_hint == "empirical"
    assert doc.paragraph(5).section_id == sub.id
    assert doc.sections[2].end_idx == 6  # глава охватывает подраздел


def test_pattern_headings_without_styles_and_list_items_not_headings():
    doc = analyze_structure(
        doc_of(
            [
                "ВВЕДЕНИЕ",
                "Задачи исследования:",
                "1. Изучить литературу по теме.",
                "ГЛАВА 1. Теория",
                "1.1. Подход к проблеме",
                "ЗАКЛЮЧЕНИЕ",
                "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ",
            ]
        )
    )
    assert [s.kind for s in doc.sections] == [
        "INTRO", "CHAPTER", "SUBSECTION", "CONCLUSION", "BIBLIOGRAPHY",
    ]  # fmt: skip
    assert all(s.detection == "pattern" for s in doc.sections)


def test_sentence_starting_with_keyword_is_not_heading():
    doc = analyze_structure(
        doc_of(
            [
                "ВВЕДЕНИЕ",
                "Введение новых методик в практику позволило, как показано выше, улучшить итоги.",
            ]
        )
    )
    assert [s.kind for s in doc.sections] == ["INTRO"]


def test_heuristic_only_when_few_headings():
    centered = ParaFormat(align=Valued("center"))
    bold = (RunInfo("НЕИЗВЕСТНЫЙ РАЗДЕЛ", bold=True),)
    doc = analyze_structure(
        doc_of([("НЕИЗВЕСТНЫЙ РАЗДЕЛ", dict(fmt=centered, runs=bold)), "текст"])
    )
    assert doc.sections[0].detection == "heuristic"
    assert doc.sections[0].confidence < 0.5


def test_toc_text_pattern_is_not_headings_and_entries_resolve():
    doc = analyze_structure(
        doc_of(
            [
                "Титул",
                "ОГЛАВЛЕНИЕ",
                "ВВЕДЕНИЕ ........ 3",
                "ГЛАВА 1. Теория ........ 5",
                "ЗАКЛЮЧЕНИЕ ........ 40",
                H("ВВЕДЕНИЕ"), "текст",
                H("ГЛАВА 1. Теория"), "текст",
                H("ЗАКЛЮЧЕНИЕ"),
            ]
        )
    )  # fmt: skip
    assert doc.toc is not None and doc.toc.source == "text_pattern"
    assert [e.page_num for e in doc.toc.entries] == [3, 5, 40]
    assert all(e.resolved_section_id for e in doc.toc.entries)
    assert [s.kind for s in doc.sections] == ["TITLE", "TOC", "INTRO", "CHAPTER", "CONCLUSION"]
    assert doc.toc.entries[1].number == "1"


def test_toc_field_range_by_result_lines():
    f = FieldRef("TOC", 'TOC \\o "1-3"', "Введение\t3\nГлава 1\t5\nЗаключение\t9", paragraph_idx=2)
    doc = analyze_structure(
        doc_of(
            ["Оглавление", "Введение\t3", "Глава 1\t5", "Заключение\t9", H("Введение")], fields=[f]
        )
    )
    assert doc.toc.source == "toc_field"
    assert len(doc.toc.entries) == 3 and doc.toc.entries[0].page_num == 3
    assert doc.toc.entries[1].number == "1" and doc.toc.entries[1].page_num == 5


def test_captions_bind_and_sentences_are_not_captions():
    doc = analyze_structure(
        doc_of(
            [
                H("ГЛАВА 1. Т"),
                "Таблица 1 - Данные",
                ("TABLE",),
                "Таблица 2 показывает различия между группами.",
                "Рисунок 1 - схема",
            ]
        )
    )  # fmt: skip
    kinds_ = [(c.kind, c.number, c.target) for c in doc.captions]
    assert kinds_ == [("table", "1", 1), ("figure", "1", None)]
    assert doc.tables[0].caption_idx == 0
    assert doc.captions[0].title == "Данные"


def test_bibliography_numbers_from_text():
    doc = analyze_structure(
        doc_of(
            [H("СПИСОК ЛИТЕРАТУРЫ"), "1. Иванов А.А. Книга. М., 2020.", "2. Петров Б.Б. Статья."]
        )
    )
    assert [(b.number, b.text[:6]) for b in doc.bibliography] == [("1", "Иванов"), ("2", "Петров")]


def test_appendix_key_title_and_new_page():
    doc = analyze_structure(
        doc_of(
            [
                H("ЗАКЛЮЧЕНИЕ"),
                ("ПРИЛОЖЕНИЕ А", dict(page_break_before=True, outline_level=0)),
                "Анкета",
                ("Приложение Б", dict(outline_level=0)),
            ]
        )
    )  # fmt: skip
    a, b = doc.appendices
    assert (a.key, a.title, a.starts_new_page) == ("А", "Анкета", True)
    assert (b.key, b.starts_new_page) == ("Б", False)


def test_no_intro_no_toc_means_no_title_section():
    doc = analyze_structure(doc_of(["Титул", H("ГЛАВА 1. Т")]))
    assert "TITLE" not in [s.kind for s in doc.sections]
