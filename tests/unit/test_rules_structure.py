from dataclasses import replace

from tests.fixtures.model_factory import DocBuilder
from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.engine import run_rule
from vkr_checker.checks.structure import (
    Page01Margins,
    Str01RequiredSections,
    Str02TocVsHeadings,
    Str03ChapterConclusions,
    Str04ConclusionDuplicates,
    Str05Appendices,
    Str06TocPages,
)
from vkr_checker.model.document import Appendix, Layout, PageSetup, Toc, TocEntry


def clean_builder(*, appendix=True, conclusions=True, concl_extra=""):
    b = DocBuilder()
    b.heading("Титульный лист", kind="TITLE")
    b.heading("Оглавление", kind="TOC")
    b.heading("Введение", kind="INTRO")
    b.para("Актуальность темы.")
    b.heading("Теоретический анализ", kind="CHAPTER", number="1")
    b.para("Текст первой главы.")
    if conclusions:
        b.heading("Выводы по главе 1", kind="CHAPTER_CONCLUSIONS", level=2, parent="s4")
        b.para(
            "Теоретический анализ показал значимость социальной поддержки для адаптации студентов."
        )
    b.heading("Эмпирическое исследование", kind="CHAPTER", number="2")
    b.para("Текст второй главы.")
    if conclusions:
        b.heading("Выводы по главе 2", kind="CHAPTER_CONCLUSIONS", level=2, parent="s6")
        b.para(
            "Эмпирически выявлены различия между экспериментальной и контрольной группами выборки."
        )
    b.heading("Заключение", kind="CONCLUSION")
    b.para("Подведены итоги исследования и намечены перспективы дальнейшей работы." + concl_extra)
    b.heading("Список литературы", kind="BIBLIOGRAPHY")
    if appendix:
        b.heading("Приложение А", kind="APPENDIX")
    return b


def run(rule, doc):
    return run_rule(CheckContext.build(doc), rule)


def ids(res):
    return sorted(f.fingerprint for f in res.findings)


# --- STR-01 -------------------------------------------------------------------------------
def test_str01_clean_passes():
    doc = clean_builder().build()
    doc = replace(doc, appendices=(Appendix("Приложение А", "А"),))
    assert run(Str01RequiredSections(), doc).outcome == "passed"


def test_str01_missing_conclusion_is_violation():
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.heading("Глава 1", kind="CHAPTER", number="1")
    b.heading("Глава 2", kind="CHAPTER", number="2")
    res = run(Str01RequiredSections(), b.build())
    by_fp = {f.fingerprint: f for f in res.findings}
    assert by_fp["STR-01|missing|CONCLUSION"].level == "violation"
    assert "заключение" in by_fp["STR-01|missing|CONCLUSION"].message
    assert by_fp["STR-01|missing|TITLE"].level == "suspicion"


def test_str01_chapter_count_is_suspicion_never_violation():
    b = clean_builder()
    b.heading("Глава 3", kind="CHAPTER", number="3")
    res = run(Str01RequiredSections(), replace(b.build(), appendices=(Appendix("П", "А"),)))
    f = next(f for f in res.findings if f.fingerprint == "STR-01|chapters")
    assert f.level == "suspicion" and f.values["chapters"] == 3


def test_str01_order_suspicion_with_actual_and_expected():
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    b.heading("Заключение", kind="CONCLUSION")
    b.heading("Глава 1", kind="CHAPTER", number="1")
    res = run(Str01RequiredSections(), b.build())
    f = next(f for f in res.findings if f.fingerprint == "STR-01|order")
    assert f.level == "suspicion" and f.values["expected"][:3] == ["INTRO", "CHAPTER", "CONCLUSION"]


def test_str01_toc_in_document_object_counts():
    b = DocBuilder()
    b.heading("Введение", kind="INTRO")
    doc = replace(b.build(), toc=Toc(source="toc_field"))
    assert "STR-01|missing|TOC" not in ids(run(Str01RequiredSections(), doc))


# --- STR-02 -------------------------------------------------------------------------------
def toc_doc(entries):
    doc = clean_builder().build()
    return replace(doc, toc=Toc(source="toc_field", entries=tuple(entries)))


def test_str02_unresolved_entry_and_missing_heading():
    doc = toc_doc(
        [
            TocEntry("Теоретический анализ", level=1, resolved_section_id="s4", paragraph_idx=2),
            TocEntry("Несуществующий раздел", level=1, resolved_section_id=None, paragraph_idx=3),
        ]
    )
    res = run(Str02TocVsHeadings(), doc)
    assert all(f.level == "violation" for f in res.findings)
    fps = ids(res)
    assert "STR-02|toc|Несуществующий раздел" in fps
    assert "STR-02|heading|2 Эмпирическое исследование" in fps
    assert not any("Теоретический анализ" in fp for fp in fps)


def test_str02_deep_levels_ignored_and_no_toc_not_run():
    doc = toc_doc([TocEntry("1.1.1 Глубокий", level=3)])
    assert not [f for f in run(Str02TocVsHeadings(), doc).findings if "Глубокий" in f.message]
    assert run(Str02TocVsHeadings(), clean_builder().build()).outcome == "not_run"


# --- STR-03 -------------------------------------------------------------------------------
def test_str03_present_missing_and_tail_heading():
    assert run(Str03ChapterConclusions(), clean_builder().build()).outcome == "passed"
    res = run(Str03ChapterConclusions(), clean_builder(conclusions=False).build())
    assert len(res.findings) == 2 and all(f.level == "violation" for f in res.findings)
    b = DocBuilder()
    b.heading("Глава 1", kind="CHAPTER", number="1")
    b.para("Текст.")
    b.para("Выводы по первой главе")
    b.heading("Глава 2", kind="CHAPTER", number="2")
    b.para("Текст.")
    res = run(Str03ChapterConclusions(), b.build())
    assert [f.fingerprint for f in res.findings] == ["STR-03|s2"]


def test_str03_needs_two_chapters():
    b = DocBuilder()
    b.heading("Глава 1", kind="CHAPTER", number="1")
    assert run(Str03ChapterConclusions(), b.build()).outcome == "not_run"


# --- STR-04 -------------------------------------------------------------------------------
def test_str04_duplicate_sentence_pairs_locations():
    b = clean_builder()
    doc = b.build()
    dup = "Теоретический анализ показал значимость социальной поддержки для адаптации студентов."
    paras = list(doc.paragraphs)
    concl = next(p for p in paras if p.text.startswith("Подведены"))
    paras[concl.idx - 1] = replace(concl, text=dup)
    blocks = tuple(
        paras[p.idx - 1] if getattr(p, "idx", None) and hasattr(p, "text") else p
        for p in doc.blocks
    )
    doc = replace(doc, paragraphs=tuple(paras), blocks=blocks)
    res = run(Str04ConclusionDuplicates(), doc)
    assert len(res.findings) == 1
    f = res.findings[0]
    assert f.level == "suspicion" and len(f.locations) == 2 and f.values["ratio"] >= 85


def test_str04_clean_and_short_sentences_pass():
    assert run(Str04ConclusionDuplicates(), clean_builder().build()).outcome == "passed"


# --- STR-05 -------------------------------------------------------------------------------
def appendix_doc(*, title="Приложение А", new_page=True, referenced=True):
    b = clean_builder(appendix=False, concl_extra=" Данные в приложении А." if referenced else "")
    h = b.heading(title, kind="APPENDIX")
    doc = b.build()
    app = Appendix(title, "А", section_id=doc.sections[-1].id, starts_new_page=new_page)
    return replace(doc, appendices=(app,)), h


def test_str05_clean():
    doc, _ = appendix_doc()
    assert run(Str05Appendices(), doc).outcome == "passed"


def test_str05_all_three_violations():
    doc, _ = appendix_doc(title="Дополнительные материалы", new_page=False, referenced=False)
    doc = replace(doc, appendices=(replace(doc.appendices[0], label="Дополнительные материалы"),))
    kinds = {fp.split("|")[1] for fp in ids(run(Str05Appendices(), doc))}
    assert kinds == {"title", "page", "ref"}


def test_str05_new_page_from_layout_or_break_flag():
    doc, h = appendix_doc(new_page=False)
    layout = Layout(page_count=3, paragraph_pages={h.idx - 1: 2, h.idx: 3})
    assert "STR-05|page|А" not in ids(run(Str05Appendices(), replace(doc, layout=layout)))
    paras = list(doc.paragraphs)
    paras[h.idx - 1] = replace(paras[h.idx - 1], page_break_before=True)
    flagged = replace(doc, paragraphs=tuple(paras))
    assert "STR-05|page|А" not in ids(run(Str05Appendices(), flagged))


def test_str05_reference_inside_appendix_does_not_count():
    doc, h = appendix_doc(referenced=False)
    b_paras = list(doc.paragraphs)
    b_paras[h.idx - 1] = replace(
        b_paras[h.idx - 1], text="Приложение А", section_id=doc.sections[-1].id
    )
    assert "STR-05|ref|А" in ids(run(Str05Appendices(), replace(doc, paragraphs=tuple(b_paras))))


# --- STR-06 -------------------------------------------------------------------------------
def test_str06_offset_tolerant_and_flags_outlier():
    b = DocBuilder()
    for i, title in enumerate(["Введение", "Теория", "Практика", "Итоги"], 1):
        b.heading(title, kind="CHAPTER", number=str(i), page=3 + i * 10)
    doc = b.build(with_layout=True)
    # в оглавлении нумерация со сдвигом 2 (титул не нумеруется), у «Итоги» ошибка в 8 стр.
    entries = [
        TocEntry("Введение", page_num=11, resolved_section_id="s1"),
        TocEntry("Теория", page_num=21, resolved_section_id="s2"),
        TocEntry("Практика", page_num=31, resolved_section_id="s3"),
        TocEntry("Итоги", page_num=33, resolved_section_id="s4"),
    ]
    doc = replace(doc, toc=Toc(source="toc_field", entries=tuple(entries)))
    res = run(Str06TocPages(), doc)
    assert [f.fingerprint for f in res.findings] == ["STR-06|s4"]
    assert res.findings[0].level == "suspicion" and res.findings[0].method == "layout"


def test_str06_without_layout_is_not_checked():
    doc = toc_doc([TocEntry("Введение", page_num=3, resolved_section_id="s3")])
    assert run(Str06TocPages(), doc).outcome == "not_checked"


# --- PAGE-01 ------------------------------------------------------------------------------
def test_page01_margins():
    ok = replace(
        clean_builder().build(), page_setup=(PageSetup(0, 3.0, 1.5), PageSetup(1, 3.02, 1.52))
    )
    assert run(Page01Margins(), ok).outcome == "passed"
    bad = replace(clean_builder().build(), page_setup=(PageSetup(0, 2.0, 1.0),))
    res = run(Page01Margins(), bad)
    assert sorted(f.values["side"] for f in res.findings) == ["left", "right"]
    assert all(f.level == "violation" for f in res.findings)
    assert "2" in res.findings[0].message or "1" in res.findings[0].message


def test_page01_same_error_in_many_sections_collapses():
    sections = tuple(PageSetup(i, 2.0, 1.5) for i in range(3))
    res = run(Page01Margins(), replace(clean_builder().build(), page_setup=sections))
    assert len(res.findings) == 1 and res.findings[0].count == 3


def test_page01_no_page_setup_is_not_run():
    res = run(Page01Margins(), clean_builder().build())
    assert res.outcome == "not_run" and res.findings[0].not_run
