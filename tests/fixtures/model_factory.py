"""Сборка Document в тестах без .docx (для проверок на модели).

b = DocBuilder("t.docx")
b.heading("Введение", kind="INTRO"); b.para("Текст.")
b.heading("Теория", kind="CHAPTER", number="1")
b.table([["a", "b"], ["1", "2"]], caption="Таблица 1 - Данные")
doc = b.build()
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

from vkr_checker.model.document import (
    Caption,
    Cell,
    DocMeta,
    Document,
    Layout,
    ParaFormat,
    Paragraph,
    Row,
    Section,
    Table,
)  # fmt: skip


class DocBuilder:
    def __init__(self, filename: str = "test.docx"):
        self.filename = filename
        self._blocks: list = []
        self._paras: list[Paragraph] = []
        self._tables: list[Table] = []
        self._captions: list[Caption] = []
        self._sections: list[dict] = []
        self._pages: dict[int, int] = {}
        self._table_pages: dict[int, int] = {}
        self._cur: str | None = None

    def para(self, text: str, page: int | None = None, **kw) -> Paragraph:
        p = Paragraph(
            idx=len(self._paras) + 1, text=text, section_id=self._cur,
            fmt=kw.pop("fmt", ParaFormat()), **kw,
        )  # fmt: skip
        self._paras.append(p)
        self._blocks.append(p)
        if page:
            self._pages[p.idx] = page
        return p

    def heading(self, title: str, kind: str = "CHAPTER", number: str | None = None,
                level: int = 1, parent: str | None = None, **kw) -> Paragraph:  # fmt: skip
        sid = f"s{len(self._sections) + 1}"
        self._cur = sid
        p = self.para(title, outline_level=level - 1, num_label=number, **kw)
        self._sections.append(dict(id=sid, kind=kind, title=title, number=number, level=level,
                                   parent_id=parent, heading_paragraph_idx=p.idx,
                                   start_idx=p.idx))  # fmt: skip
        return p

    def table(self, rows: list[list[str]], caption: str | None = None,
              page: int | None = None) -> Table:  # fmt: skip
        idx = len(self._tables) + 1
        cap_idx = None
        if caption:
            num = caption.split()[1].rstrip(".-—") if len(caption.split()) > 1 else str(idx)
            self._captions.append(Caption(kind="table", number=num, title=caption,
                                          label_text="Таблица", target=idx))  # fmt: skip
            cap_idx = len(self._captions) - 1
        trs = tuple(
            Row(cells=tuple(Cell(row=r, col=c, text=t) for c, t in enumerate(row, 1)))
            for r, row in enumerate(rows, 1)
        )
        t = Table(idx=idx, rows=trs, anchor_block=len(self._blocks), section_id=self._cur,
                  caption_idx=cap_idx, prev_paragraph_idx=len(self._paras) or None)  # fmt: skip
        self._tables.append(t)
        self._blocks.append(t)
        if page:
            self._table_pages[idx] = page
        return t

    def build(self, with_layout: bool = False) -> Document:
        ends = [s["start_idx"] - 1 for s in self._sections[1:]] + [len(self._paras)]
        sections = []
        for s, end in zip(self._sections, ends):
            children = tuple(c["id"] for c in self._sections if c["parent_id"] == s["id"])
            sections.append(Section(**s, end_idx=end, children=children))
        layout = None
        if with_layout:
            layout = Layout(page_count=max(self._pages.values(), default=1),
                            paragraph_pages=dict(self._pages),
                            table_pages=dict(self._table_pages))  # fmt: skip
        sha = hashlib.sha256("".join(p.text for p in self._paras).encode()).hexdigest()
        return Document(
            meta=DocMeta(filename=self.filename, sha256=sha),
            blocks=tuple(self._blocks), paragraphs=tuple(self._paras),
            tables=tuple(self._tables), captions=tuple(self._captions),
            sections=tuple(sections), layout=layout,
        )  # fmt: skip


def with_layout(doc: Document, layout: Layout | None) -> Document:
    return replace(doc, layout=layout)
