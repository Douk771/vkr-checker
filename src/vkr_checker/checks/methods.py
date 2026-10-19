"""MET-01..04: методы, методики и авторы (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.engine import need_section
from vkr_checker.checks.facts.authors import authors_in
from vkr_checker.checks.facts.common import paragraphs_in
from vkr_checker.checks.registry import register
from vkr_checker.checks.rulehelpers import in_section_tree, mention_location, section_id_of
from vkr_checker.nlp.lexicons.methods import METHODS
from vkr_checker.nlp.normalize import normalize_text
from vkr_checker.nlp.sentences import split_sentences

SRC_ANALYSIS = Source("CH", "Анализ данных")
SRC_THEORY = Source("CH", "Теория и методики")


def _title(method_id: str) -> str:
    return METHODS[method_id].title if method_id in METHODS else method_id


@register
class Met01MethodsConsistency:
    id = "MET-01"
    title = "Методы обработки: введение, §2.1, результаты"
    block = "methods"
    source = SRC_ANALYSIS
    default_level = "suspicion"
    needs = frozenset({Need.INTRO, Need.SUB_2_1, Need.CH2})
    priority = "must"

    def run(self, ctx: CheckContext):
        intro = need_section(ctx.doc, Need.INTRO)
        sub = need_section(ctx.doc, Need.SUB_2_1)
        ch2 = need_section(ctx.doc, Need.CH2)
        assert intro and sub and ch2
        declared_intro: dict[str, object] = {}
        declared_sub: dict[str, object] = {}
        applied: dict[str, object] = {}
        for m in ctx.facts.methods:
            sid = section_id_of(ctx, m.loc)
            if m.kind == "name" and in_section_tree(ctx, sid, intro.id):
                declared_intro.setdefault(m.method_id, m)
            elif in_section_tree(ctx, sid, sub.id):
                declared_sub.setdefault(m.method_id, m)
            elif in_section_tree(ctx, sid, ch2.id):
                applied.setdefault(m.method_id, m)
        out = []
        for mid in sorted(set(declared_intro) ^ set(declared_sub)):
            where_intro = mid in declared_intro
            mention = declared_intro.get(mid) or declared_sub.get(mid)
            msg = (
                f"Метод «{_title(mid)}» назван во введении, но не описан в §2.1."
                if where_intro
                else f"Метод «{_title(mid)}» описан в §2.1, но не назван во введении."
            )
            out.append(
                new_finding(
                    self,
                    msg,
                    fingerprint=f"MET-01|mismatch|{mid}",
                    level="violation",
                    method="morph",
                    locations=[mention_location(ctx, mention.loc)],
                    values={"method": mid},
                )  # fmt: skip
            )
        declared = set(declared_intro) | set(declared_sub)
        for mid in sorted(declared - set(applied)):
            mention = declared_intro.get(mid) or declared_sub.get(mid)
            out.append(
                new_finding(
                    self,
                    f"Метод «{_title(mid)}» заявлен, но в результатах главы 2 не применён.",
                    fingerprint=f"MET-01|unused|{mid}",
                    method="morph",
                    locations=[mention_location(ctx, mention.loc)],
                    values={"method": mid},
                )  # fmt: skip
            )
        for mid in sorted(set(applied) - declared):
            out.append(
                new_finding(
                    self,
                    f"Метод «{_title(mid)}» применён в результатах, но не заявлен "
                    "ни во введении, ни в §2.1.",
                    fingerprint=f"MET-01|undeclared|{mid}",
                    method="morph",
                    locations=[mention_location(ctx, applied[mid].loc)],
                    values={"method": mid},
                )  # fmt: skip
            )
        return result_of(self, out)


def _chapter_text(ctx: CheckContext, section) -> list[tuple[int, str]]:
    return [(p.idx, normalize_text(p.text)) for p in paragraphs_in(ctx.doc, section) if p.text]


@register
class Met02InstrumentsInTheory:
    id = "MET-02"
    title = "Методики главы 2 описаны в главе 1"
    block = "methods"
    source = SRC_THEORY
    default_level = "suspicion"
    needs = frozenset({Need.SUB_2_1, Need.CH1})
    priority = "must"

    def run(self, ctx: CheckContext):
        ch1 = need_section(ctx.doc, Need.CH1)
        sentences = _chapter_sentences(ctx, ch1)
        authors_ch1 = {a.key for a in ctx.facts.authors if a.chapter == 1}
        out = []
        for ins in ctx.facts.instruments:
            matched = [s for s in sentences if self._mentions(ins, s.norm, ctx.th.INSTR_MATCH)]
            if not matched and not any(key in authors_ch1 for _s, key in ins.authors):
                out.append(
                    new_finding(
                        self,
                        f"Методика «{ins.name}» из главы 2 не обсуждается в главе 1.",
                        fingerprint=f"MET-02|{normalize_text(ins.name)}",
                        method="fuzzy",
                        locations=[mention_location(ctx, ins.loc)],
                        values={"instrument": ins.name, "abbr": ins.abbr},
                        hint="Опишите методику и её авторов в теоретической главе.",
                    )  # fmt: skip
                )
                continue
            out.extend(self._authors_mismatch(ctx, ins, matched))
        return result_of(self, out)

    def _authors_mismatch(self, ctx: CheckContext, ins, matched):
        """Авторы методики в главе 2 и в предложениях главы 1 о ней не пересекаются."""
        keys_ch2 = {key for _s, key in ins.authors}
        by_key: dict[str, str] = {}
        for s in matched:
            for surname, key in authors_in(s.raw):
                by_key.setdefault(key, surname)
        if not keys_ch2 or not by_key or keys_ch2 & by_key.keys():
            return []
        return [
            new_finding(
                self,
                f"Авторы методики «{ins.name}» в главе 2 ({', '.join(n for n, _k in ins.authors)}) "
                f"не совпадают с авторами в главе 1 ({', '.join(by_key.values())}).",
                fingerprint=f"MET-02|authors|{normalize_text(ins.name)}",
                method="morph",
                locations=[mention_location(ctx, ins.loc)],
                values={
                    "instrument": ins.name,
                    "authors_ch2": [n for n, _k in ins.authors],
                    "authors_ch1": list(by_key.values()),
                    "adaptation": ins.adaptation,
                },
                hint="Указывайте одних и тех же авторов и адаптацию методики в главах 1 и 2.",
            )  # fmt: skip
        ]

    @staticmethod
    def _mentions(ins, sentence: str, min_ratio: float) -> bool:
        """Предложение упоминает методику: название (все значимые слова), либо аббревиатура."""
        name = normalize_text(ins.name)
        if name in sentence:
            return True
        if ins.abbr and re.search(rf"(?<!\w){re.escape(ins.abbr)}(?!\w)", sentence, re.IGNORECASE):
            return True
        return _covers_words(name, sentence, min_ratio)


@dataclass(frozen=True, slots=True)
class _Sentence:
    raw: str
    norm: str


_WORD = re.compile(r"\w+")
MIN_NAME_WORD = 3


def _chapter_sentences(ctx: CheckContext, section) -> list[_Sentence]:
    return [
        _Sentence(s.text, normalize_text(s.text))
        for p in paragraphs_in(ctx.doc, section)
        if p.text
        for s in split_sentences(p.text)
    ]


def _covers_words(name: str, sentence: str, min_ratio: float) -> bool:
    """Каждое значимое слово названия есть в предложении (с учётом падежа и опечаток).

    Нечёткое сравнение идёт по словам, а не по подстроке длинного абзаца: иначе общая
    лексика темы («учебная мотивация») засчитывала бы методику найденной (BUG-Q7).
    """
    words = [w for w in _WORD.findall(name) if len(w) >= MIN_NAME_WORD]
    if not words:
        return False
    text_words = _WORD.findall(sentence)
    for w in words:
        stem = w[: max(MIN_NAME_WORD, len(w) - 2)]
        if not any(t.startswith(stem) or fuzz.ratio(w, t) >= min_ratio for t in text_words):
            return False
    return True


_QUOTED = re.compile(r"[«\"“]([^»\"”]{4,80})[»\"”]")


@register
class Met03TheoryBasis:
    id = "MET-03"
    title = "Теоретические основания раскрыты в главе 1"
    block = "methods"
    source = SRC_THEORY
    default_level = "suspicion"
    needs = frozenset({Need.INTRO, Need.CH1})
    priority = "must"

    def run(self, ctx: CheckContext):
        elements = [
            e for e in ctx.facts.intro_elements.get("theory_basis", []) if e.position != "inline"
        ]
        if not elements:
            return result_of(self, [])
        ch1 = need_section(ctx.doc, Need.CH1)
        ch1_authors = {a.key for a in ctx.facts.authors if a.chapter == 1}
        ch1_text = " ".join(t for _i, t in _chapter_text(ctx, ch1))
        content = {i for e in elements for i in e.content_paragraphs}
        out = []
        seen: set[str] = set()
        for a in ctx.facts.authors:
            if a.section_kind != "INTRO" or a.loc.paragraph_idx not in content or a.key in seen:
                continue
            seen.add(a.key)
            if a.key not in ch1_authors:
                out.append(
                    new_finding(
                        self,
                        f"Автор «{a.surname}» назван во введении среди теоретических "
                        "оснований, но не встречается в главе 1.",
                        fingerprint=f"MET-03|author|{a.key}",
                        method="morph",
                        locations=[mention_location(ctx, a.loc)],
                        values={"author": a.surname},
                    )  # fmt: skip
                )
        for idx in sorted(content):
            for q in _QUOTED.finditer(ctx.doc.paragraph(idx).text):
                term = normalize_text(q.group(1))
                if term in seen or term in ch1_text or fuzz.partial_ratio(term, ch1_text) >= 90:
                    continue
                seen.add(term)
                out.append(
                    new_finding(
                        self,
                        f"Концепция «{q.group(1)}» названа во введении, но не найдена в главе 1.",
                        fingerprint=f"MET-03|concept|{term}",
                        method="fuzzy",
                        locations=[ctx.loc.paragraph(idx, q.span())],
                        values={"concept": q.group(1)},
                    )  # fmt: skip
                )
        return result_of(self, out)


@register
class Met04DiscussionAuthors:
    id = "MET-04"
    title = "Авторы обсуждения главы 2 разобраны в главе 1"
    block = "methods"
    source = SRC_THEORY
    default_level = "suspicion"
    needs = frozenset({Need.CH1, Need.CH2})
    priority = "should"

    def run(self, ctx: CheckContext):
        ch2 = need_section(ctx.doc, Need.CH2)
        sub = need_section(ctx.doc, Need.SUB_2_1)
        ch1_keys = {a.key for a in ctx.facts.authors if a.chapter == 1}
        seen: set[str] = set()
        out = []
        for a in ctx.facts.authors:
            if a.chapter != 2 or a.key in ch1_keys or a.key in seen:
                continue
            sid = section_id_of(ctx, a.loc)
            if not in_section_tree(ctx, sid, ch2.id) or (
                sub is not None and in_section_tree(ctx, sid, sub.id)
            ):
                continue
            seen.add(a.key)
            out.append(
                new_finding(
                    self,
                    f"Автор «{a.surname}» упомянут в главе 2, но не разобран в главе 1.",
                    fingerprint=f"MET-04|{a.key}",
                    method="morph",
                    locations=[mention_location(ctx, a.loc)],
                    values={"author": a.surname},
                )  # fmt: skip
            )
        return result_of(self, out)
