"""MET-01..04: методы, методики и авторы (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.engine import need_section
from vkr_checker.checks.facts.common import paragraphs_in
from vkr_checker.checks.registry import register
from vkr_checker.checks.rulehelpers import in_section_tree, mention_location, section_id_of
from vkr_checker.nlp.lexicons.methods import METHODS
from vkr_checker.nlp.normalize import normalize_text

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
        texts = _chapter_text(ctx, ch1)
        authors_ch1 = {a.key for a in ctx.facts.authors if a.chapter == 1}
        out = []
        for ins in ctx.facts.instruments:
            if self._found(ins, texts, authors_ch1, ctx.th.INSTR_MATCH):
                continue
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
        return result_of(self, out)

    @staticmethod
    def _found(ins, texts, authors_ch1: set[str], min_ratio: float) -> bool:
        name = normalize_text(ins.name)
        for _idx, text in texts:
            if name in text or fuzz.partial_ratio(name, text) >= min_ratio:
                return True
            if ins.abbr and re.search(rf"(?<!\w){re.escape(ins.abbr)}(?!\w)", text, re.IGNORECASE):
                return True
        return any(key in authors_ch1 for _s, key in ins.authors)


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
