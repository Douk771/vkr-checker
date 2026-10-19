"""Гипотеза: части из введения, упоминания и статусы в главе 2 и заключении (HYP-01, матрица)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from vkr_checker.model.document import Document
from vkr_checker.nlp.sentences import split_sentences

from .common import Mention, chapter_number, section_kind_of
from .intro import IntroElement
from .tasks import ListItem, items_from_element

_HYP_WORD = re.compile(r"гипотез\w*", re.IGNORECASE)
_HYP_HEAD = re.compile(
    r"^\s*(?:рабоч\w+\s+|общ\w+\s+|частн\w+\s+)?гипотез\w*\s*\d*\s*[:.\-–—]?\s*", re.IGNORECASE
)
# Статус гипотезы распознаётся по оборотам, которые сообщают итог проверки:
# прошедшее время и краткие причастия («подтвердилась», «подтверждена»),
# «удалось подтвердить», «получила/нашла подтверждение», «свидетельствуют о
# подтверждении», «опровергнута». Цель, будущее время и модальность («для
# подтверждения», «подтвердить», «подтвердится», «будет/может быть
# подтверждена», «опровергнуть») статусом не считаются. Предложения о нулевой
# и альтернативной гипотезе (H0/H1) пропускаются: «H0 отклонена» означает
# обратное для рабочей гипотезы.
_W = r"(?:(?!(?:не|для)\s)[\w-]+\s+)"  # слово-вставка, но не «не» и не «для»
_NEG_BEFORE = re.compile(r"(?<!\w)не\s+(?:был[аио]?\s+)?$", re.IGNORECASE)
_MODAL_BEFORE = re.compile(
    r"(?<!\w)(?:будет|будут|может|могут|могла|могли|мог|должна|должны|должно|должен)"
    r"\s+(?:\w+\s+)?(?:быть\s+)?$",
    re.IGNORECASE,
)
_NULL_HYP = re.compile(
    r"(?<!\w)(?:нулев\w*|альтернативн\w*)\s+гипотез|(?<!\w)H\s?[01₀₁](?!\w)", re.IGNORECASE
)
_PARTICIPLE = re.compile(
    r"(?<!\w)(?:подтвердил\w*|подтвержд(?:ена|ено|ены|ен|ён|ается|аются|ал\w*))(?!\w)",
    re.IGNORECASE,
)
_STATUS_HITS: tuple[re.Pattern[str], ...] = (
    _PARTICIPLE,
    re.compile(rf"(?<!\w)(?P<neg>не\s+)?удалось\s+{_W}{{0,2}}подтвердить(?!\w)", re.IGNORECASE),
    re.compile(rf"(?<!\w)подтвердить\s+{_W}{{0,2}}(?P<neg>не\s+)?удалось(?!\w)", re.IGNORECASE),
    re.compile(
        rf"(?<!\w)(?P<neg>не\s+)?(?:получил\w*|нашл\w*|наш[её]л)\s+{_W}{{0,2}}подтверждени[еяю]",
        re.IGNORECASE,
    ),
    re.compile(rf"(?<!\w)свидетельству\w*\s+{_W}{{0,2}}о\s+подтверждении", re.IGNORECASE),
)
# Только итоговые формы: «опровергнута», «опровергли»; «опровергнуть» — цель.
_REFUTED = re.compile(r"(?<!\w)(?:опровергнут[аоы]?|опроверг(?:ла|ли|ло)?)(?!\w)", re.IGNORECASE)
_PARTIAL = re.compile(
    r"(?<!\w)(?<!даже\s)(?:частичн\w*|не\s+(?:был[аио]?\s+)?(?:полностью|в\s+полной\s+мере|вполне)"
    r"|не\s+(?:во|для)\s+всех|лишь\s+(?:для|в)\s+част\w*)(?!\w)",
    re.IGNORECASE,
)
_MOSTLY = re.compile(
    r"(?<!\w)(?:в\s+основном|в\s+значительной\s+(?:степени|мере)|преимущественно)(?!\w)",
    re.IGNORECASE,
)
STATUS_TITLES = {
    "not_confirmed": "не подтверждена",
    "partially_confirmed": "частично подтверждена",
    "mostly_confirmed": "в основном подтверждена",
    "confirmed": "подтверждена",
}


@dataclass(frozen=True, slots=True)
class HypothesisPart:
    index: int
    text: str
    loc: Mention


@dataclass(frozen=True, slots=True)
class HypothesisMention:
    section_kind: str  # CHAPTER | CHAPTER_CONCLUSIONS | CONCLUSION
    chapter: int | None
    text: str
    status: str | None
    loc: Mention


def status_of(text: str) -> str | None:
    """Статус гипотезы в одном предложении или None, если итог не сообщается."""
    if _NULL_HYP.search(text):
        return None
    found = negated = False
    for m in _REFUTED.finditer(text):
        before = text[: m.start()]
        if _MODAL_BEFORE.search(before):
            continue
        if _NEG_BEFORE.search(before):
            continue  # «не была опровергнута» — осторожная формулировка, не итог
        found = negated = True
    for pattern in _STATUS_HITS:
        for m in pattern.finditer(text):
            before = text[: m.start()]
            if pattern is _PARTICIPLE and _MODAL_BEFORE.search(before):
                continue
            found = True
            if m.groupdict().get("neg") or (
                "neg" not in pattern.groupindex and _NEG_BEFORE.search(before)
            ):
                negated = True
    if not found:
        return None
    if _PARTIAL.search(text):
        return "partially_confirmed"
    if negated:
        return "not_confirmed"
    if _MOSTLY.search(text):
        return "mostly_confirmed"
    return "confirmed"


def extract_hypothesis_parts(
    doc: Document, elements: dict[str, list[IntroElement]]
) -> list[HypothesisPart]:
    items: list[ListItem] = []
    for element in elements.get("hypothesis", []):
        if element.position == "inline":
            continue
        items.extend(items_from_element(doc, element))
    parts: list[HypothesisPart] = []
    for item in items:
        text = _HYP_HEAD.sub("", item.text).strip()
        if text:
            parts.append(
                HypothesisPart(len(parts) + 1, text, Mention(item.paragraph_idx, item.span))
            )
    return parts


def extract_hypothesis_mentions(doc: Document) -> list[HypothesisMention]:
    """Предложения о гипотезе в главе 2 и далее, выводах к главам и заключении."""
    result: list[HypothesisMention] = []
    for p in doc.paragraphs:
        if p.cell is not None:
            continue
        kind = section_kind_of(doc, p.section_id)
        chapter = chapter_number(doc, p.section_id)
        in_scope = kind in ("CHAPTER_CONCLUSIONS", "CONCLUSION") or (
            kind == "CHAPTER" and chapter is not None and chapter >= 2
        )
        if not in_scope:
            continue
        sentences = split_sentences(p.text)
        for i, s in enumerate(sentences):
            if not _HYP_WORD.search(s.text):
                continue
            status = status_of(s.text)
            # Статус в следующем предложении («Гипотеза 2 ... . Она подтвердилась.»)
            # берём, только если в текущем его нет и следующее не о другой гипотезе.
            if status is None and i + 1 < len(sentences):
                nxt = sentences[i + 1].text
                if not _HYP_WORD.search(nxt):
                    status = status_of(nxt)
            result.append(
                HypothesisMention(
                    section_kind=kind,
                    chapter=chapter,
                    text=s.text,
                    status=status,
                    loc=Mention(p.idx, (s.start, s.end)),
                )
            )
    return result
