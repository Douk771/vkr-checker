"""LEX-01..03: формулировки (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

import re
from collections.abc import Iterator

from vkr_checker.checks.base import CheckContext, Source, new_finding, result_of
from vkr_checker.checks.facts.authors import authors_in
from vkr_checker.checks.facts.common import chapter_number, heading_idx_set, section_kind_of
from vkr_checker.checks.registry import register
from vkr_checker.model.document import Paragraph
from vkr_checker.nlp.morph import lemma, tokens
from vkr_checker.nlp.sentences import Sentence, split_sentences

SRC = Source("CH", "Правила формулировок")
CAUSAL_LEMMAS = frozenset(
    {"влиять", "определять", "обусловливать", "обусловить", "приводить", "зависеть", "вызывать"}
)
_CAUSE_PHRASE = re.compile(r"является\s+причин|являются\s+причин|причин\w+\s+(?:является|служит)")
_LINK_MARKER = re.compile(
    r"корреляц|регресс|(?<![A-Za-zА-Яа-я])(?:r|rs|β|R[²2])(?![A-Za-zА-Яа-я])|\bсвяз", re.IGNORECASE
)
_LINK_CASE_SENSITIVE = re.compile(r"(?<![A-Za-zА-Яа-я])(?:r|rs|β|R[²2])\s*[=<>]")
ESTABLISH_LEMMAS = frozenset({"установить", "выявить", "доказать", "установленный", "доказанный"})
_ATTRIBUTION = re.compile(r"\[\d+|по\s+данным|согласно|по\s+мнению|по\s+результатам\s+исследован")
_GUESS = re.compile(
    r"\b(?:возможно|вероятно|по[-\s]видимому|скорее\s+всего|можно\s+предположить)\b", re.IGNORECASE
)
_LIMITS_WORD = re.compile(r"ограничени|перспектив", re.IGNORECASE)


def _results_scope(ctx: CheckContext) -> Iterator[Paragraph]:
    """Абзацы результатов: глава 2 и далее, выводы к главам, заключение."""
    heads = heading_idx_set(ctx.doc)
    for p in ctx.doc.paragraphs:
        if p.cell is not None or not p.text.strip() or p.idx in heads:
            continue
        kind = section_kind_of(ctx.doc, p.section_id)
        chapter = chapter_number(ctx.doc, p.section_id)
        if kind in ("CHAPTER_CONCLUSIONS", "CONCLUSION") or (
            kind == "CHAPTER" and chapter is not None and chapter >= 2
        ):
            yield p


def _has_lemma(sentence: str, wanted: frozenset[str]) -> bool:
    return any(lemma(w) in wanted for w in tokens(sentence))


def _causal(sentence: str) -> bool:
    low = sentence.lower()
    if _CAUSE_PHRASE.search(low):
        return True
    for w in tokens(sentence):
        if lemma(w) in CAUSAL_LEMMAS:
            if lemma(w) == "приводить" and not re.search(r"\bк\b", low):
                continue
            return True
    return False


def _links(sentence: str) -> bool:
    return bool(_LINK_MARKER.search(sentence) or _LINK_CASE_SENSITIVE.search(sentence))


@register
class Lex01CausalWording:
    id = "LEX-01"
    title = "Причинные формулировки у корреляций и регрессий"
    block = "wording"
    source = SRC
    default_level = "suspicion"
    needs = frozenset()
    priority = "must"

    def run(self, ctx: CheckContext):
        out = []
        for p in _results_scope(ctx):
            for s in split_sentences(p.text):
                if _causal(s.text) and _links(s.text):
                    out.append(
                        new_finding(
                            self,
                            "Причинная формулировка при описании связи: корреляция и регрессия "
                            "не доказывают причинность.",
                            fingerprint=f"LEX-01|{p.idx}",
                            method="morph",
                            locations=[ctx.loc.paragraph(p.idx, (s.start, s.end))],
                            hint="Напишите «вносит вклад в объяснение», «сопряжено с», "
                            "«связано с».",
                        )  # fmt: skip
                    )
        return result_of(self, out)


@register
class Lex02EstablishedFindings:
    id = "LEX-02"
    title = "«Установлено» у чужих выводов"
    block = "wording"
    source = SRC
    default_level = "suspicion"
    needs = frozenset()
    priority = "must"

    def _chapter1_conclusion_ids(self, ctx: CheckContext) -> set[str]:
        doc, ids = ctx.doc, set()
        for s in doc.sections:
            if s.kind == "CHAPTER_CONCLUSIONS" and chapter_number(doc, s.id) == 1:
                ids.add(s.id)
        return ids

    def run(self, ctx: CheckContext):
        ch1_conclusions = self._chapter1_conclusion_ids(ctx)
        out = []
        heads = heading_idx_set(ctx.doc)
        for p in ctx.doc.paragraphs:
            if p.cell is not None or not p.text.strip() or p.idx in heads:
                continue
            kind = section_kind_of(ctx.doc, p.section_id)
            in_ch1_concl = p.section_id in ch1_conclusions
            if kind not in ("CONCLUSION", "CHAPTER_CONCLUSIONS"):
                continue
            for s in split_sentences(p.text):
                if not _has_lemma(s.text, ESTABLISH_LEMMAS):
                    continue
                if in_ch1_concl:
                    msg = "Выводы первой главы названы «установленными», а это чужие результаты."
                elif _ATTRIBUTION.search(s.text) or authors_in(s.text):
                    msg = "«Установлено/выявлено/доказано» стоит рядом со ссылкой на чужую работу."
                else:
                    continue
                out.append(self._finding(ctx, p, s, msg))
        return result_of(self, out)

    def _finding(self, ctx: CheckContext, p: Paragraph, s: Sentence, msg: str):
        return new_finding(
            self, msg, fingerprint=f"LEX-02|{p.idx}", method="morph",
            locations=[ctx.loc.paragraph(p.idx, (s.start, s.end))],
            hint="Для чужих выводов используйте «показано», «отмечено», «по данным ...».",
        )  # fmt: skip


@register
class Lex03Speculation:
    id = "LEX-03"
    title = "Догадки вне «ограничений и перспектив»"
    block = "wording"
    source = SRC
    default_level = "suspicion"
    needs = frozenset()
    priority = "should"

    def run(self, ctx: CheckContext):
        out = []
        in_limits_section: set[str] = set()
        for s in ctx.doc.sections:
            if _LIMITS_WORD.search(s.title):
                in_limits_section.add(s.id)
        in_limits_run = False
        last_section = None
        for p in _results_scope(ctx):
            if p.section_id != last_section:
                in_limits_run, last_section = False, p.section_id
            if _LIMITS_WORD.match(p.text.strip()):
                in_limits_run = True
            if in_limits_run or p.section_id in in_limits_section or _LIMITS_WORD.search(p.text):
                continue
            for s in split_sentences(p.text):
                m = _GUESS.search(s.text)
                if m:
                    out.append(
                        new_finding(
                            self,
                            f"Предположение «{m.group()}» в разделе результатов или выводов.",
                            fingerprint=f"LEX-03|{p.idx}",
                            method="regex",
                            locations=[
                                ctx.loc.paragraph(p.idx, (s.start + m.start(), s.start + m.end()))
                            ],
                            hint="Догадки уместны в блоке об ограничениях и перспективах.",
                        )  # fmt: skip
                    )
        return result_of(self, out)
