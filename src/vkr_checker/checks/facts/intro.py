"""Элементы введения (INT-01 и опоры для HYP, TSK, MET-03, матрицы).

Каждый элемент ищется по ключевым словам в начале абзаца или предложения. Положение:
heading (отдельный заголовок) > para_start > sentence_start > inline (только в теле абзаца).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from vkr_checker.model.document import Document, Paragraph
from vkr_checker.nlp.sentences import split_sentences

from .common import heading_idx_set, paragraphs_in

Position = Literal["heading", "para_start", "sentence_start", "inline"]
POSITION_RANK = {"heading": 0, "para_start": 1, "sentence_start": 2, "inline": 3}

# ключ -> регэксп начала (после необязательного номера/маркера); порядок = порядок в SPEC INT-01
ELEMENT_KEYWORDS: dict[str, str] = {
    "actuality": r"актуальност\w*",
    "elaboration": r"(?:степень\s+)?(?:изученност|разработанност)\w*",
    "goal": r"цел(?:ь|и|ью|ей|ях)\b",
    "object": r"объект\w*",
    "subject": r"предмет\w*",
    "tasks": r"задач\w*",
    "hypothesis": r"(?:рабоч\w+\s+|общ\w+\s+|частн\w+\s+)?гипотез\w*",
    "theory_basis": r"теоретико[-\s]*методологическ\w+(?:\s+основ\w*)?|теоретическ\w+\s+основ\w*",
    "methods": r"методы?\b|методик\w*|методы\s+исследования",
    "sample": r"выборк\w*|эмпирическ\w+\s+база",
    "novelty": r"(?:научн\w+\s+)?новизн\w*",
    "theory_value": r"теоретическ\w+\s+значимост\w*",
    "practice_value": r"практическ\w+\s+значимост\w*",
    "defense": r"положени\w+[^.:]{0,40}(?:выносим|защит)\w*",
    "approbation": r"апробаци\w*",
    "implementation": r"внедрени\w*",
}
REQUIRED = tuple(k for k in ELEMENT_KEYWORDS if k != "implementation")
_LEAD = r"^[\s\d.)\-–—•*]*"
_START = {k: re.compile(_LEAD + f"(?P<kw>{v})", re.IGNORECASE) for k, v in ELEMENT_KEYWORDS.items()}
_AFTER_KEYWORD = re.compile(
    r"^\s*(?:исследования|работы|исследовательской\s+работы|проекта|исследование)?"
    r"\s*(?:является|являются|состоит\s+в\s+том,?\s+что|[:.\-–—])?\s*",
    re.IGNORECASE,
)
_ANY = {k: re.compile(f"(?:{v})", re.IGNORECASE) for k, v in ELEMENT_KEYWORDS.items()}


@dataclass(frozen=True, slots=True)
class IntroElement:
    key: str
    position: Position
    paragraph_idx: int
    span: tuple[int, int]  # ключевое слово в тексте абзаца
    text: str  # содержание элемента: остаток абзаца без ключевых слов
    content_paragraphs: tuple[int, ...]  # абзац и следующие до начала другого элемента


def _classify(par: Paragraph, is_heading: bool) -> list[tuple[str, Position, tuple[int, int]]]:
    found: list[tuple[str, Position, tuple[int, int]]] = []
    text = par.text
    sentences = split_sentences(text)[1:]
    for key in ELEMENT_KEYWORDS:
        m = _START[key].match(text)
        if m is not None:
            # длинная фраза-заголовок с этим словом внутри - не заголовок элемента
            pos: Position = "heading" if is_heading and len(text) < 80 else "para_start"
            found.append((key, pos, m.span("kw")))
            continue
        for s in sentences:
            ms = _START[key].match(s.text)
            if ms is not None:
                found.append(
                    (key, "sentence_start", (s.start + ms.start("kw"), s.start + ms.end("kw")))
                )
                break
        else:
            mi = _ANY[key].search(text)
            if mi is not None:
                heading_like = is_heading and len(text) < 80
                found.append((key, "heading" if heading_like else "inline", mi.span()))
    return found


def _content_text(text: str, span: tuple[int, int]) -> str:
    """Остаток после ключевого слова: «Цель исследования - изучить X» -> «изучить X»."""
    rest = text[span[1] :]
    return rest[_AFTER_KEYWORD.match(rest).end() :].strip()


def extract_intro_elements(doc: Document) -> dict[str, list[IntroElement]]:
    """key -> элементы на лучшем из найденных положений (несколько - если их несколько)."""
    intro = next((s for s in doc.sections if s.kind == "INTRO"), None)
    paras = [
        p for p in paragraphs_in(doc, intro) if p.idx != getattr(intro, "heading_paragraph_idx", 0)
    ]
    headings = heading_idx_set(doc)
    starts: dict[int, list[tuple[str, Position, tuple[int, int]]]] = {}
    for p in paras:
        starts[p.idx] = _classify(p, p.idx in headings)
    boundary = {
        idx
        for idx, found in starts.items()
        if any(pos in ("heading", "para_start") for _, pos, _ in found)
    }
    boundary |= {p.idx for p in paras if p.idx in headings}
    order = [p.idx for p in paras]
    candidates: dict[str, list[IntroElement]] = {}
    for p in paras:
        for key, pos, span in starts[p.idx]:
            content = [p.idx]
            if pos in ("heading", "para_start"):
                for nxt in order[order.index(p.idx) + 1 :]:
                    if nxt in boundary:
                        break
                    content.append(nxt)
            text = _content_text(p.text, span) if pos != "heading" else ""
            candidates.setdefault(key, []).append(
                IntroElement(key, pos, p.idx, span, text, tuple(content))
            )
    result: dict[str, list[IntroElement]] = {}
    for key, items in candidates.items():
        best = min(POSITION_RANK[i.position] for i in items)
        result[key] = [i for i in items if POSITION_RANK[i.position] == best]
    return result
