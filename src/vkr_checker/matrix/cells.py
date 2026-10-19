"""Заполнение ячеек матрицы связности по фактам (MAT-01, ARCHITECTURE_CHECKS.md §7)."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.facts.common import chapter_number, paragraphs_in
from vkr_checker.checks.rulehelpers import mention_location
from vkr_checker.model.document import Document, Section
from vkr_checker.model.finding import Location
from vkr_checker.nlp.lexicons.methods import METHODS
from vkr_checker.nlp.morph import content_lemma_set, content_lemmas
from vkr_checker.report.schema import MatrixCell

MAX_CANDIDATES = 3
MAX_LOCATIONS = 3
SHORT = 80
_STAT = re.compile(
    r"(?<![A-Za-zА-Яа-я])(?:rs|r|p|U|t|F|H|χ[2²]|d)\s*(?:\(\s*\d+(?:\s*,\s*\d+)?\s*\))?"
    r"\s*[=<>≤≥]\s*[-−–]?\d+(?:[.,]\d+)?"
)


def gap(candidates: list[str] | None = None) -> MatrixCell:
    return MatrixCell(
        status="gap", text="", candidates=(candidates or [])[:MAX_CANDIDATES], locations=[]
    )


def not_required() -> MatrixCell:
    return MatrixCell(status="n/a", text="", candidates=[], locations=[])


def auto(text: str, locations: list[Location], candidates: list[str] | None = None) -> MatrixCell:
    return MatrixCell(
        status="auto",
        text=text,
        candidates=(candidates or [])[:MAX_CANDIDATES],
        locations=locations,
    )


def short(text: str, width: int = SHORT) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def _label(section: Section) -> str:
    return f"{section.number} {section.title}".strip() if section.number else section.title


@dataclass(frozen=True)
class Fragment:
    """Найденный фрагмент расчёта: таблица или абзац главы 2."""

    kind: str  # table | paragraph
    idx: int
    label: str
    score: int
    alt_paragraph: int | None = None  # лучший абзац главы 2, если найдена таблица


class TheoryIndex:
    """TF-IDF по подразделам главы 1."""

    def __init__(self, ctx: CheckContext) -> None:
        doc = ctx.doc
        sections = [
            s for s in doc.sections
            if s.kind in ("SUBSECTION", "CHAPTER") and chapter_number(doc, s.id) == 1
            and (s.kind == "SUBSECTION" or not s.children)
        ]  # fmt: skip
        self.ctx = ctx
        self.sections = sections
        self.paragraphs = {
            s.id: [p for p in paragraphs_in(doc, s) if p.idx != s.heading_paragraph_idx]
            for s in sections
        }
        self.tf = {
            s.id: Counter(content_lemmas(" ".join(p.text for p in self.paragraphs[s.id])))
            for s in sections
        }
        df: Counter[str] = Counter()
        for counter in self.tf.values():
            df.update(counter.keys())
        n = len(sections)
        self.idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
        self.norm = {
            sid: math.sqrt(sum((c * self.idf[w]) ** 2 for w, c in tf.items()))
            for sid, tf in self.tf.items()
        }

    def score(self, section: Section, keys: set[str]) -> float:
        tf, norm = self.tf[section.id], self.norm[section.id]
        qnorm = math.sqrt(sum(self.idf.get(w, 1.0) ** 2 for w in sorted(keys)))
        if not norm or not qnorm:
            return 0.0
        dot = sum(tf[w] * self.idf[w] * self.idf[w] for w in sorted(keys) if w in tf)
        return dot / (norm * qnorm)

    def find(self, keys: set[str]) -> MatrixCell:
        scored = sorted(
            ((self.score(s, keys), i, s) for i, s in enumerate(self.sections)),
            key=lambda x: (-x[0], x[1]),
        )
        if not scored:
            return gap()
        best_score, _, best = scored[0]
        others = [_label(s) for sc, _, s in scored[1:] if sc > 0]
        if best_score < self.ctx.th.MAT_THEORY_MIN:
            return gap(([_label(best)] if best_score > 0 else []) + others)
        paras = {p.idx for p in self.paragraphs[best.id]}
        counts = Counter(a.surname for a in self.ctx.facts.authors if a.loc.paragraph_idx in paras)
        names = [name for name, _ in counts.most_common(MAX_CANDIDATES)]
        text = _label(best) + (f" ({', '.join(names)})" if names else "")
        where = []
        if best.heading_paragraph_idx:
            where.append(self.ctx.loc.paragraph(best.heading_paragraph_idx))
        return auto(text, where, names)


def find_instrument(ctx: CheckContext, keys: set[str]) -> MatrixCell:
    best, best_score, names = None, 0, []
    for inst in ctx.facts.instruments:
        concept = set(content_lemmas(inst.name))
        idx = inst.loc.paragraph_idx
        if idx is not None:
            for s in ctx.facts.sentences(idx):
                if s.start <= inst.loc.span[0] < s.end:
                    concept |= content_lemma_set(s.text)
        score = len(keys & concept)
        label = inst.name + (f" ({inst.abbr})" if inst.abbr else "")
        names.append(label)
        if score > best_score:
            best, best_score = (inst, label), score
    if best is None:
        return gap(names)
    inst, label = best
    return auto(label, [mention_location(ctx, inst.loc)], [n for n in names if n != label])


def _table_methods(ctx: CheckContext, table_idx: int, number: str | None) -> list[str]:
    ids: list[str] = []
    ref_paras = {
        r.loc.paragraph_idx for r in ctx.facts.refs
        if r.kind == "table" and number and r.target == number
    }  # fmt: skip
    for m in ctx.facts.methods:
        in_table = m.loc.cell is not None and m.loc.cell.table_idx == table_idx
        if (in_table or m.loc.paragraph_idx in ref_paras) and m.method_id not in ids:
            ids.append(m.method_id)
    return [METHODS[i].title if i in METHODS else i for i in ids]


def _chapter2_units(ctx: CheckContext):
    doc: Document = ctx.doc
    for t in doc.tables:
        if t.parent_table_idx is not None or chapter_number(doc, t.section_id) != 2:
            continue
        cap = doc.captions[t.caption_idx] if t.caption_idx is not None else None
        header = " ".join(c.text for c in t.rows[0].cells) if t.rows else ""
        text = f"{cap.title if cap else ''} {header}"
        yield "table", t.idx, t.number_label(doc), content_lemma_set(text)
    headings = {s.heading_paragraph_idx for s in doc.sections}
    for p in doc.paragraphs:
        if p.cell is None and p.idx not in headings and chapter_number(doc, p.section_id) == 2:
            yield "paragraph", p.idx, f"абз. {p.idx} главы 2", content_lemma_set(p.text)


def find_calculation(ctx: CheckContext, keys: set[str]) -> tuple[MatrixCell, Fragment | None]:
    need = 2 if len(keys) >= 4 else 1
    scored = [(len(keys & lem), kind, idx, label) for kind, idx, label, lem in _chapter2_units(ctx)]
    ranked = sorted(
        (s for s in scored if s[0] > 0), key=lambda s: -s[0]
    )  # устойчиво: таблицы первыми
    if not ranked or ranked[0][0] < need:
        return gap([r[3] for r in ranked]), None
    score, kind, idx, label = ranked[0]
    doc = ctx.doc
    if kind == "table":
        table = doc.table(idx)
        cap = doc.captions[table.caption_idx] if table.caption_idx is not None else None
        methods = _table_methods(ctx, idx, cap.number if cap else None)
        where = (
            ctx.loc.paragraph(cap.paragraph_idx) if cap and cap.paragraph_idx
            else ctx.loc.cell(idx, 1, 1)
        )  # fmt: skip
    else:
        sel = {m.method_id for m in ctx.facts.methods if m.loc.paragraph_idx == idx}
        methods = [METHODS[i].title if i in METHODS else i for i in sorted(sel)]
        where = ctx.loc.paragraph(idx)
    text = label + (f": {', '.join(methods)}" if methods else "")
    alt = next((r[2] for r in ranked if r[1] == "paragraph" and r[0] >= need), None)
    fragment = Fragment(kind, idx, label, score, alt)
    return auto(text, [where], [r[3] for r in ranked[1:]]), fragment


def find_result(ctx: CheckContext, fragment: Fragment | None) -> MatrixCell:
    if fragment is None:
        return gap()
    found: list[tuple[str, Location]] = []
    if fragment.kind == "paragraph":
        sources = [(fragment.idx, ctx.doc.paragraph(fragment.idx).text)]
    else:
        table = ctx.doc.table(fragment.idx)
        cap = ctx.doc.captions[table.caption_idx] if table.caption_idx is not None else None
        refs = {
            r.loc.paragraph_idx for r in ctx.facts.refs
            if r.kind == "table" and cap and r.target == cap.number and r.loc.paragraph_idx
        }  # fmt: skip
        sources = [(i, ctx.doc.paragraph(i).text) for i in sorted(refs)]
        if not refs and fragment.alt_paragraph is not None:
            sources = [(fragment.alt_paragraph, ctx.doc.paragraph(fragment.alt_paragraph).text)]
    for idx, text in sources:
        for m in _STAT.finditer(text):
            found.append((" ".join(m.group().split()), ctx.loc.paragraph(idx, m.span())))
    if fragment.kind == "table":
        for m in ctx.facts.methods:
            if m.kind == "stat" and m.loc.cell is not None and m.loc.cell.table_idx == fragment.idx:
                found.append((m.text, mention_location(ctx, m.loc)))
    unique = list(dict.fromkeys(text for text, _ in found))
    if not unique:
        return gap()
    return auto(", ".join(unique[:6]), [loc for _, loc in found[:MAX_LOCATIONS]])
