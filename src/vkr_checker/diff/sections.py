"""Выравнивание разделов (DIF-01, ARCHITECTURE_CHECKS.md §5.1)."""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from vkr_checker.model.document import Document, Paragraph, Section
from vkr_checker.report.schema import ParagraphDiff
from vkr_checker.thresholds import Thresholds

from .pairing import greedy_pairs
from .paragraphs import diff_paragraphs
from .words import fold, norm_title

PSEUDO_TITLE = "(вне разделов)"
MAX_LEVEL = 2


@dataclass(frozen=True)
class SecUnit:
    """Раздел уровней 1-2 вместе с абзацами подразделов глубже."""

    idx: int
    section: Section | None
    title: str
    norm: str
    kind: str
    parent_idx: int | None
    paragraphs: tuple[Paragraph, ...]

    @property
    def content(self) -> str:
        return fold(" ".join(p.text for p in self.paragraphs))


@dataclass
class SectionMatch:
    """Пара разделов (или один раздел) с полным списком операций над абзацами."""

    old: SecUnit | None
    new: SecUnit | None
    basis: str | None = None  # exact | title | content
    paragraphs: list[ParagraphDiff] = field(default_factory=list)


def display_title(section: Section) -> str:
    return f"{section.number} {section.title}".strip() if section.number else section.title


def diffable_paragraphs(doc: Document) -> list[Paragraph]:
    """Абзацы тела, участвующие в сравнении: без заголовков, оглавления, ячеек и пустых."""
    headings = {s.heading_paragraph_idx for s in doc.sections if s.heading_paragraph_idx}
    toc = {s.id for s in doc.sections if s.kind == "TOC"}
    return [
        p
        for p in doc.paragraphs
        if p.cell is None
        and p.container == "body"
        and p.idx not in headings
        and p.section_id not in toc
        and p.text.strip()
    ]


def build_units(doc: Document) -> list[SecUnit]:
    sections = sorted((s for s in doc.sections if s.level <= MAX_LEVEL), key=lambda s: s.start_idx)
    index_of = {s.id: i for i, s in enumerate(sections)}

    def owner(section_id: str | None) -> int | None:
        seen: set[str] = set()
        sec = doc.section_by_id(section_id)
        while sec is not None and sec.id not in seen:
            seen.add(sec.id)
            if sec.id in index_of:
                return index_of[sec.id]
            sec = doc.section_by_id(sec.parent_id)
        return None

    buckets: dict[int | None, list[Paragraph]] = {}
    for p in diffable_paragraphs(doc):
        buckets.setdefault(owner(p.section_id), []).append(p)
    units: list[SecUnit] = []
    if buckets.get(None):
        units.append(SecUnit(0, None, PSEUDO_TITLE, "", "UNKNOWN", None, tuple(buckets[None])))
    offset = len(units)
    for i, s in enumerate(sections):
        parent = index_of.get(s.parent_id) if s.parent_id else None
        units.append(
            SecUnit(
                i + offset,
                s,
                display_title(s),
                norm_title(s.title or ""),
                s.kind,
                None if parent is None else parent + offset,
                tuple(buckets.get(i, ())),
            )  # fmt: skip
        )
    return units


def _parents_compatible(o: SecUnit, n: SecUnit, mapping: dict[int, int]) -> bool:
    if o.parent_idx is None or n.parent_idx is None:
        return o.parent_idx is None and n.parent_idx is None
    mapped = mapping.get(o.parent_idx)
    return mapped is None or mapped == n.parent_idx or n.parent_idx not in mapping.values()


def match_units(
    old: list[SecUnit], new: list[SecUnit], th: Thresholds
) -> dict[int, tuple[int, str]]:
    """Три прохода (заголовок, близкий заголовок, содержимое): old.idx -> (new.idx, basis)."""
    used_o: set[int] = set()
    used_n: set[int] = set()
    result: dict[int, tuple[int, str]] = {}
    pos_o = {u.idx: k for k, u in enumerate(old)}
    pos_n = {u.idx: k for k, u in enumerate(new)}

    def run(candidates: list[tuple[float, int, int]], basis: str) -> None:
        for k, m, _ in greedy_pairs(candidates, used_o, used_n):
            result[old[k].idx] = (new[m].idx, basis)

    pseudo_o = next((u for u in old if u.section is None), None)
    pseudo_n = next((u for u in new if u.section is None), None)
    if pseudo_o and pseudo_n:
        run([(100.0, pos_o[pseudo_o.idx], pos_n[pseudo_n.idx])], "exact")

    exact: list[tuple[float, int, int]] = []
    for i, o in enumerate(old):
        for j, n in enumerate(new):
            if o.section and n.section and o.kind == n.kind and o.norm and o.norm == n.norm:
                exact.append((100 + fuzz.token_set_ratio(o.content, n.content) / 1000, i, j))
    run(exact, "exact")

    mapping = {pos_o[o]: pos_n[n] for o, (n, _) in result.items()}
    near: list[tuple[float, int, int]] = []
    for i, o in enumerate(old):
        for j, n in enumerate(new):
            if i in used_o or j in used_n or o.section is None or n.section is None:
                continue
            if o.kind != n.kind or not _parents_compatible(o, n, mapping):
                continue
            ratio = fuzz.token_set_ratio(o.norm, n.norm)
            if ratio >= th.SEC_RENAME_RATIO:
                near.append((ratio, i, j))
    run(near, "title")

    by_content: list[tuple[float, int, int]] = []
    for i, o in enumerate(old):
        for j, n in enumerate(new):
            if i in used_o or j in used_n or o.section is None or n.section is None:
                continue
            if o.kind != n.kind:
                continue
            a, b = o.content[: th.SEC_CONTENT_CHARS], n.content[: th.SEC_CONTENT_CHARS]
            if min(len(a), len(b)) < th.SEC_CONTENT_MIN_CHARS:
                continue
            ratio = fuzz.token_set_ratio(a, b)
            if ratio >= th.SEC_CONTENT_RATIO:
                by_content.append((ratio, i, j))
    run(by_content, "content")
    return result


def _whole(unit: SecUnit, new_side: bool) -> list[ParagraphDiff]:
    if new_side:
        return [
            ParagraphDiff(status="inserted", new_idx=p.idx, text=p.text) for p in unit.paragraphs
        ]
    return [ParagraphDiff(status="deleted", old_idx=p.idx, text=p.text) for p in unit.paragraphs]


def align_sections(old_doc: Document, new_doc: Document, th: Thresholds) -> list[SectionMatch]:
    """Список пар в порядке новой версии; удалённые разделы стоят после своего предшественника."""
    old_units, new_units = build_units(old_doc), build_units(new_doc)
    matched = match_units(old_units, new_units, th)
    old_by_idx = {u.idx: u for u in old_units}
    new_to_old = {n: (o, basis) for o, (n, basis) in matched.items()}

    def removed_after(unit_idx: int | None) -> list[SectionMatch]:
        """Подряд идущие удалённые разделы после старого раздела unit_idx (None - с начала)."""
        start = 0 if unit_idx is None else old_units.index(old_by_idx[unit_idx]) + 1
        out: list[SectionMatch] = []
        for u in old_units[start:]:
            if u.idx in matched:
                break
            out.append(SectionMatch(u, None, None, _whole(u, False)))
        return out

    result: list[SectionMatch] = removed_after(None)
    for n in new_units:
        if n.idx in new_to_old:
            o_idx, basis = new_to_old[n.idx]
            o = old_by_idx[o_idx]
            result.append(
                SectionMatch(
                    o, n, basis, diff_paragraphs(list(o.paragraphs), list(n.paragraphs), th)
                )
            )
            result.extend(removed_after(o_idx))
        else:
            result.append(SectionMatch(None, n, None, _whole(n, True)))
    return result
