"""Подписи таблиц и рисунков и привязка к объектам (ARCHITECTURE.md §7 п.6)."""

from __future__ import annotations

import re
from dataclasses import replace

from vkr_checker.docx.fields import stale_seq_paragraphs
from vkr_checker.model.document import Caption, Document, Image, Paragraph, Table

from .patterns import CAPTION

_TABLE_LABELS = ("таблица", "табл.")
_MAX_CAPTION_CHARS = 300
_CONTINUATION = re.compile(r"^\s*продолжение\b", re.IGNORECASE)


def _parts(number: str) -> tuple[str, ...]:
    return tuple(x for x in re.split(r"[.\-]", number) if x)


def _kind(label: str) -> str:
    return "table" if label.lower() in _TABLE_LABELS else "figure"


def _source(doc: Document, p: Paragraph, seq_paras: set[int]) -> str:
    if any(f.kind == "SEQ" and f.paragraph_idx == p.idx for f in doc.fields):
        return "seq_field"
    return "autonum" if p.num_label else "text"


def _match(p: Paragraph):
    text = " ".join(p.full_text.split())
    if not text or len(text) > _MAX_CAPTION_CHARS or _CONTINUATION.match(text):
        return None
    return CAPTION.match(text)


def _is_caption_like(m: re.Match) -> bool:
    """Без разделителя после номера «Таблица 3 показывает ...» - обычное предложение."""
    return bool(m.group("sep")) and bool(m.group("title").strip())


def _body_blocks(doc: Document):
    return list(doc.blocks)


def build_captions(doc: Document, in_appendix) -> Document:
    """Находит подписи, связывает с таблицами и рисунками; возвращает обновлённый Document."""
    seq_stale = stale_seq_paragraphs(list(doc.fields))
    blocks = _body_blocks(doc)
    image_paras: dict[int, list[Image]] = {}
    for img in doc.images:
        if img.paragraph_idx is not None:
            image_paras.setdefault(img.paragraph_idx, []).append(img)
    captions: list[Caption] = []
    table_cap: dict[int, int] = {}
    image_cap: dict[int, int] = {}
    used: set[int] = set()

    def add(p: Paragraph, m: re.Match, kind: str, target: int | None, image_idx=None) -> int:
        number = m.group("num")
        captions.append(
            Caption(
                kind=kind,
                number=number,
                title=m.group("title").strip(),  # type: ignore[arg-type]
                label_text=m.group("label"),
                number_parts=_parts(number),
                number_source=_source(doc, p, seq_stale),  # type: ignore[arg-type]
                seq_field_stale_suspect=p.idx in seq_stale,
                paragraph_idx=p.idx if image_idx is None else None,
                image_idx=image_idx,
                target=target,
                in_appendix=in_appendix(p.section_id),
            )  # fmt: skip
        )
        return len(captions) - 1

    body = [b for b in blocks]
    for pos, block in enumerate(body):
        if not isinstance(block, Paragraph):
            continue
        m = _match(block)
        if m is None:
            continue
        kind = _kind(m.group("label"))
        if kind == "table":
            target = _next_table(body, pos)
            if target is None and not _is_caption_like(m):
                continue
            cap = add(block, m, "table", target.idx if target else None)
            if target is not None:
                table_cap[target.idx] = cap
            used.add(block.idx)
        else:
            img = _figure_target(body, pos, image_paras, image_cap)
            if img is None and not _is_caption_like(m):
                continue
            cap = add(block, m, "figure", img.idx if img else None)
            if img is not None:
                image_cap[img.idx] = cap
            used.add(block.idx)
    # подписи внутри надписей
    for img in doc.images:
        if img.idx in image_cap:
            continue
        for tp in img.textbox_paragraphs:
            m = _match(tp)
            if m is not None and _kind(m.group("label")) == "figure":
                host = doc.paragraph(img.paragraph_idx) if img.paragraph_idx else tp
                image_cap[img.idx] = add(host, m, "figure", img.idx, image_idx=img.idx)
                break
    tables = tuple(replace(t, caption_idx=table_cap.get(t.idx, t.caption_idx)) for t in doc.tables)
    images = tuple(replace(i, caption_idx=image_cap.get(i.idx, i.caption_idx)) for i in doc.images)
    return replace(doc, captions=tuple(captions), tables=tables, images=images)


def _next_table(body: list, pos: int) -> Table | None:
    """Таблица сразу после подписи (допускается один пустой абзац или «Продолжение»)."""
    skipped = 0
    for nxt in body[pos + 1 :]:
        if isinstance(nxt, Table):
            return nxt
        if nxt.text.strip() and not _CONTINUATION.match(nxt.text):
            return None
        skipped += 1
        if skipped > 1:
            return None
    return None


def _figure_target(body: list, pos: int, image_paras: dict, taken: dict) -> Image | None:
    """Рисунок до подписи (ближайший абзац с картинкой), иначе в следующем абзаце."""
    for back in (1, 2):
        if pos - back >= 0:
            prev = body[pos - back]
            if isinstance(prev, Paragraph) and prev.idx in image_paras:
                free = [i for i in image_paras[prev.idx] if i.idx not in taken]
                if free:
                    return free[0]
            if isinstance(prev, Paragraph) and prev.text.strip():
                break
            if isinstance(prev, Table):
                break
    if pos + 1 < len(body):
        nxt = body[pos + 1]
        if isinstance(nxt, Paragraph) and nxt.idx in image_paras:
            free = [i for i in image_paras[nxt.idx] if i.idx not in taken]
            if free:
                return free[0]
    return None
