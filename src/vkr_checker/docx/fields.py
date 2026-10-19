"""Поля Word: w:fldSimple и составные fldChar (ARCHITECTURE.md §6.2).

В текст абзаца идёт сохранённый результат поля, инструкция (SEQ, REF, PAGEREF, TOC) уходит в
FieldRef. Поля не пересчитываются. Составное поле может начаться в одном абзаце и закончиться
в другом (TOC), поэтому состояние живёт в FieldParser и переносится между абзацами.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

from vkr_checker.model.document import FieldRef

from .revisions import child_text, walk_inline
from .xmlutil import qn

W_FLD_CHAR = qn("w:fldChar")
W_INSTR = qn("w:instrText")
_TYPE = qn("w:fldCharType")
_INSTR_ATTR = qn("w:instr")
_SEQ_SWITCH_RESET = re.compile(r"\\[rsc]\b", re.IGNORECASE)


@dataclass
class _Frame:
    start_idx: int | None
    instr: list[str] = field(default_factory=list)
    result: list[str] = field(default_factory=list)
    in_result: bool = False


@dataclass
class ParagraphContent:
    """Видимое содержимое абзаца: текст и сегменты (текст, w:r) для форматирования."""

    text: str
    segments: list[tuple[str, etree._Element]]
    fields: list[FieldRef]


def field_kind(instruction: str) -> str:
    """'SEQ Таблица \\* ARABIC' -> 'SEQ'. Пустая инструкция -> ''."""
    tokens = instruction.strip().lstrip('"').split()
    return tokens[0].upper() if tokens else ""


class FieldParser:
    def __init__(self) -> None:
        self._stack: list[_Frame] = []
        self.completed: list[FieldRef] = []

    @property
    def open_fields(self) -> int:
        return len(self._stack)

    def _emit_text(self, text: str) -> bool:
        """Учитывает текст в результатах открытых полей; True - текст виден в абзаце."""
        if not self._stack:
            return True
        if not self._stack[-1].in_result:
            return False
        for frame in self._stack:
            if frame.in_result:
                frame.result.append(text)
        return True

    def _finish(self, frame: _Frame) -> FieldRef:
        instruction = " ".join("".join(frame.instr).split())
        ref = FieldRef(
            kind=field_kind(instruction),
            instruction=instruction,
            result="".join(frame.result).strip(),
            paragraph_idx=frame.start_idx,
        )
        self.completed.append(ref)
        return ref

    def feed_paragraph(self, p: etree._Element, paragraph_idx: int | None) -> ParagraphContent:
        text: list[str] = []
        segments: list[tuple[str, etree._Element]] = []
        done: list[FieldRef] = []
        simple_frames: list[_Frame] = []

        def visible(chunk: str, run: etree._Element) -> None:
            if chunk and self._emit_text(chunk):
                text.append(chunk)
                segments.append((chunk, run))

        for event, el in walk_inline(p):
            if event == "simple_start":
                frame = _Frame(paragraph_idx, [el.get(_INSTR_ATTR, "")], in_result=True)
                self._stack.append(frame)
                simple_frames.append(frame)
            elif event == "simple_end":
                frame = self._stack.pop()
                simple_frames.pop()
                done.append(self._finish(frame))
            else:
                self._feed_run(el, paragraph_idx, visible, done)
        if self._stack:  # поле продолжится в следующем абзаце
            for frame in self._stack:
                if frame.in_result:
                    frame.result.append("\n")
        return ParagraphContent("".join(text), segments, done)

    def _feed_run(self, run, paragraph_idx, visible, done) -> None:
        pending: list[str] = []

        def flush() -> None:
            if pending:
                visible("".join(pending), run)
                pending.clear()

        for child in run:
            tag = child.tag
            if tag == W_FLD_CHAR:
                flush()
                kind = child.get(_TYPE)
                if kind == "begin":
                    self._stack.append(_Frame(paragraph_idx))
                elif kind == "separate" and self._stack:
                    self._stack[-1].in_result = True
                elif kind == "end" and self._stack:
                    done.append(self._finish(self._stack.pop()))
            elif tag == W_INSTR:
                if self._stack and not self._stack[-1].in_result:
                    self._stack[-1].instr.append(child.text or "")
            else:
                chunk = child_text(child)
                if chunk:
                    pending.append(chunk)
        flush()


def parse_paragraph(p: etree._Element, paragraph_idx: int | None = None) -> ParagraphContent:
    """Содержимое одного абзаца без переноса состояния полей (для тестов и простых случаев)."""
    return FieldParser().feed_paragraph(p, paragraph_idx)


def stale_seq_paragraphs(fields: list[FieldRef]) -> set[int]:
    """Абзацы с SEQ, чей результат повторяет номер в той же последовательности (SPEC §3.5).

    Последовательности с переключателями \\r, \\s, \\c (сброс или привязка к заголовку) могут
    законно повторять номера, поэтому не проверяются.
    """
    seen: dict[str, set[str]] = {}
    stale: set[int] = set()
    for f in fields:
        if f.kind != "SEQ" or f.paragraph_idx is None or not f.result:
            continue
        tokens = f.instruction.split()
        if len(tokens) < 2 or _SEQ_SWITCH_RESET.search(f.instruction):
            continue
        name = tokens[1].lower()
        numbers = seen.setdefault(name, set())
        if f.result in numbers:
            stale.add(f.paragraph_idx)
        numbers.add(f.result)
    return stale
