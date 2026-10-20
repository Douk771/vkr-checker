from tests.unit.test_structure import H, doc_of
from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.bibliography import Bib01SourceReferences
from vkr_checker.checks.engine import run_rule
from vkr_checker.checks.numbering import Num01CaptionNumbering, Num02References, Num03TotalsPhrase
from vkr_checker.structure import analyze_structure
from vkr_checker.thresholds import Thresholds


def run(rule, items, th=None, **kw):
    doc = analyze_structure(doc_of(items, **kw))
    return run_rule(CheckContext.build(doc, th), rule)


T = ("TABLE",)


def messages(res):
    return [f.message for f in res.findings]


def test_num01_clean_continuous_numbering():
    res = run(Num01CaptionNumbering(), [H("ГЛАВА 1. Т"), "Таблица 1 - А", T, "Таблица 2 - Б", T])
    assert not res.findings


def test_num01_gap_duplicate_and_order():
    items = [
        H("ГЛАВА 1. Т"),
        "Таблица 1 - А", T, "Таблица 3 - Б", T, "Таблица 3 - В", T, "Таблица 2 - Г", T,
    ]  # fmt: skip
    res = run(Num01CaptionNumbering(), items)
    text = " | ".join(messages(res))
    assert "Пропущен номер 2" in text and "повторяется" in text and "Нарушен порядок" in text
    assert all(f.level == "violation" for f in res.findings)


def test_num01_mixed_schemes_and_chapter_prefix():
    items = [
        H("ГЛАВА 1. Т"), "Таблица 1.1 - А", T, "Таблица 2 - Б", T,
        H("ГЛАВА 2. Э"), "Таблица 1.2 - В", T,
    ]  # fmt: skip
    res = run(Num01CaptionNumbering(), items)
    text = " | ".join(messages(res))
    assert "Смешаны схемы" in text
    assert "стоит в главе 2" in text


def test_num01_appendix_numbered_separately():
    items = [
        H("ГЛАВА 1. Т"), "Таблица 1 - А", T,
        H("ПРИЛОЖЕНИЕ А"), "Таблица А.1 - Б", T, "Таблица А.2 - В", T,
    ]  # fmt: skip
    assert not run(Num01CaptionNumbering(), items).findings


def test_num01_appendix_continues_main_numbering():
    items = [
        H("ГЛАВА 1. Т"), "Таблица 1 - А", T, "Таблица 2 - Б", T,
        H("ПРИЛОЖЕНИЕ 1"), "Таблица 3 - В", T,
    ]  # fmt: skip
    assert not run(Num01CaptionNumbering(), items).findings


def test_two_line_caption_is_recognized():
    """«Таблица 1» отдельной строкой, название — следующим абзацем (как в чек-листе)."""
    items = [H("ГЛАВА 1. Т"), "Данные в табл. 1.", "Таблица 1", "Описательные статистики", T]
    assert not run(Num01CaptionNumbering(), items).findings
    assert not run(Num02References(), items).findings


def test_num03_counts_appendix_tables_too():
    items = [
        H("ВВЕДЕНИЕ"), "Работа содержит 2 таблицы.",
        H("ГЛАВА 1. Т"), "Таблица 1 - А", T,
        H("ПРИЛОЖЕНИЕ 1"), "Таблица 2 - Б", T,
    ]  # fmt: skip
    assert not run(Num03TotalsPhrase(), items).findings


def test_num01_table_without_caption_and_stale_seq():
    from vkr_checker.model.document import FieldRef

    res = run(Num01CaptionNumbering(), [H("ГЛАВА 1. Т"), "текст", T])
    assert "нет подписи" in messages(res)[0]
    fields = [FieldRef("SEQ", "SEQ Таблица", "1", 2), FieldRef("SEQ", "SEQ Таблица", "1", 3)]
    items = [H("ГЛАВА 1. Т"), "Таблица 1 - А", T, "Таблица 1 - Б", T]
    res = run(Num01CaptionNumbering(), items, fields=fields)
    assert any(f.level == "suspicion" and "SEQ" in f.message for f in res.findings)


def test_num02_missing_reference_far_reference_and_nonexistent():
    th = Thresholds(REF_FAR_PARAS=3)
    items = [H("ГЛАВА 1. Т"), "Таблица 1 - А", T, "Таблица 2 - Б", T, "п", "п", "п", "п"]
    items += ["Как видно из табл. 2, различий нет.", "См. также рис. 7."]
    res = run(Num02References(), items, th)
    by_fp = {f.fingerprint: f for f in res.findings}
    assert by_fp["NUM-02|noref|table|1"].level == "violation"
    assert by_fp["NUM-02|far|table|2"].level == "suspicion"
    assert "NUM-02|missing|figure|7" in by_fp


def test_num02_clean_when_referenced_before_object():
    items = [H("ГЛАВА 1. Т"), "Данные приведены в таблице 1.", "Таблица 1 - А", T]
    assert not run(Num02References(), items).findings


def test_num03_wrong_count_and_absent_phrase():
    items = [
        H("ВВЕДЕНИЕ"), "Работа содержит 5 таблиц.",
        H("ГЛАВА 1. Т"), "Таблица 1 - А", T, "Таблица 2 - Б", T,
    ]  # fmt: skip
    res = run(Num03TotalsPhrase(), items)
    assert len(res.findings) == 1
    assert res.findings[0].values == {"declared": 5, "actual": 2, "total": 2}
    res = run(Num03TotalsPhrase(), [H("ВВЕДЕНИЕ"), "текст", H("ГЛАВА 1. Т"), "Таблица 1 - А", T])
    assert res.findings[0].level == "suspicion"
    ok = [H("ВВЕДЕНИЕ"), "В работе содержится 1 таблица.", H("ГЛАВА 1. Т"), "Таблица 1 - А", T]
    assert not run(Num03TotalsPhrase(), ok).findings


def test_bib01_over_and_uncited():
    items = [
        H("ГЛАВА 1. Т"), "Это известно [1] и [9].",
        H("СПИСОК ЛИТЕРАТУРЫ"), "1. Иванов А.А. Книга.", "2. Петров Б.Б. Книга.",
    ]  # fmt: skip
    res = run(Bib01SourceReferences(), items)
    fps = {f.fingerprint: f for f in res.findings}
    assert fps["BIB-01|over|9"].level == "violation"
    assert fps["BIB-01|uncited"].level == "suspicion" and fps["BIB-01|uncited"].values == {
        "uncited": [2]
    }


def test_bib01_confidence_interval_is_not_a_citation():
    items = [
        H("ГЛАВА 1. Т"), "Связь значима (rs = 0,28; 95 % ДИ [0,03; 0,50]) [1].",
        H("СПИСОК ЛИТЕРАТУРЫ"), "1. Иванов А.А. Книга.",
    ]  # fmt: skip
    assert not run(Bib01SourceReferences(), items).findings


def test_bib01_author_year_style_does_not_flag_uncited():
    items = [
        H("ГЛАВА 1. Т"),
        "См. (Иванов, 2020).",
        H("СПИСОК ЛИТЕРАТУРЫ"),
        "1. Иванов А.А. Книга.",
    ]
    assert not run(Bib01SourceReferences(), items).findings
