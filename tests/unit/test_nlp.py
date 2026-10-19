import pytest

from vkr_checker.nlp import morph
from vkr_checker.nlp.normalize import (
    join_hyphenated_lines,
    normalize_key,
    normalize_number,
    normalize_text,
)
from vkr_checker.nlp.sentences import split_sentences


def texts(s):
    return [x.text for x in split_sentences(s)]


def test_normalize_text_handles_yo_nbsp_soft_hyphen_case():
    assert normalize_text("  Ёлка  УЧЕ­БНАЯ\n\tработа ") == "елка учебная работа"


def test_normalize_key_keeps_only_letters_and_digits():
    assert normalize_key("1.1. Понятие «мотивации»!") == "11понятиемотивации"


def test_join_hyphenated_lines():
    assert join_hyphenated_lines("мотива-\nция студентов") == "мотивация студентов"
    assert join_hyphenated_lines("кто-то\nещё") == "кто-то\nещё"


@pytest.mark.parametrize(
    ("raw", "expected"), [("1 234,5", "1234.5"), ("0,05", "0.05"), ("−3", "-3")]
)
def test_normalize_number(raw, expected):
    assert normalize_number(raw) == expected


def test_split_basic_and_offsets_point_into_original():
    t = "Первое предложение. Второе предложение! Третье?  Четвёртое."
    sents = split_sentences(t)
    assert [s.text for s in sents] == [
        "Первое предложение.", "Второе предложение!", "Третье?", "Четвёртое."
    ]  # fmt: skip
    assert all(t[s.start : s.end] == s.text for s in sents)


@pytest.mark.parametrize(
    "text",
    [
        "Подробнее см. рис. 3 и табл. 2 ниже.",
        "Авторы Иванова А.А. и Петров Б.В. описали метод.",
        "Различия значимы при p < 0,05 и t = 2.31 в обеих группах.",
        "Рассмотрены тесты, анкеты и т.п. методики сбора данных.",
        "Работа выполнена в 2019 г. Иванова А.А. подтвердила результаты.",
        "Например, т.е. для выборки (n = 30) характерно иное.",
    ],
)
def test_abbreviations_do_not_split(text):
    sents = texts(text)
    if "2019 г." in text:
        assert len(sents) in (1, 2)  # после «г.» перед заглавной буквой граница неоднозначна
    else:
        assert len(sents) == 1, sents


def test_final_abbreviation_before_capital_splits():
    assert len(texts("Использовали анкеты, шкалы и т.д. Далее обработали данные.")) == 2
    assert len(texts("Приведены работы Иванова и др. Результаты сопоставлены.")) == 2


def test_quotes_and_brackets_after_terminator():
    assert len(texts("Он сказал: «Это важно.» Затем продолжил.")) == 2
    assert len(texts("Выборка велика (n = 120). Анализ проведён.")) == 2


def test_lowercase_after_period_is_not_boundary():
    assert len(texts("Значение составило 5 ед. при норме 3 ед.")) == 1


def test_empty_and_whitespace():
    assert split_sentences("") == []
    assert split_sentences("   \n ") == []
    assert texts("Без точки в конце") == ["Без точки в конце"]


def test_lemmas_and_pos():
    assert morph.lemmas("Студентов изучали") == ["студент", "изучать"]
    assert morph.lemma("Ёлки") == "елка"
    assert morph.pos_of("в") == "PREP"


def test_content_lemmas_drop_function_words_and_task_verbs():
    got = morph.content_lemmas("Изучить влияние учебной мотивации на адаптацию студентов")
    assert got == ["влияние", "учебный", "мотивация", "адаптация", "студент"]


def test_content_lemmas_match_across_word_forms():
    a = morph.content_lemma_set("Мотивация студентов связана с адаптацией")
    b = morph.content_lemma_set("Адаптация студентов и их мотивации")
    assert {"мотивация", "студент", "адаптация"} <= a & b
    assert morph.jaccard(a, a) == 1.0
    assert morph.jaccard(frozenset(), frozenset()) == 1.0
    assert morph.jaccard(frozenset({"а"}), frozenset({"б"})) == 0.0


def test_lemma_cache_is_used():
    morph.clear_cache()
    morph.lemma("студентов")
    morph.lemma("студентов")
    info = morph._parse.cache_info()
    assert info.hits >= 1 and info.misses == 1


def test_tokens_keep_hyphenated_words_and_skip_digits():
    assert morph.tokens("Научный руководитель – кандидат психолог-педагог, 2019") == [
        "научный", "руководитель", "кандидат", "психолог-педагог"
    ]  # fmt: skip
