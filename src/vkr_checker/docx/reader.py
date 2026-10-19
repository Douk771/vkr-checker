"""XML -> плоская модель документа (ARCHITECTURE.md §6.1, §6.5).

Читатель идёт по телу строго в порядке документа (счётчики нумерации и состояние полей
зависят от порядка). Результат - Document без разделов, подписей и оглавления: их достраивает
пакет structure/. Абзацы ячеек входят в `Document.paragraphs` (с `cell`), нумерация сквозная.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from vkr_checker.model.document import (
    Cell,
    CellRef,
    DocMeta,
    Document,
    FieldRef,
    Image,
    PageSetup,
    Paragraph,
    RunInfo,
    Table,
)

from .drawings import paragraph_images
from .fields import FieldParser
from .numbering import NumberingResolver
from .package import MAIN_PART, DocxPackage
from .revisions import is_paragraph_removed
from .styles import ParaResolution, StyleSheet, TableContext, parse_cnf, parse_tbl_look
from .tableprops import (
    TableProps,
    cell_elements,
    cell_width_cm,
    grid_span,
    live_rows,
    read_table_props,
    row_props,
    section_page_setup,
    v_merge,
)
from .xmlutil import W_P, W_TBL, iter_body_blocks, qn, w_attr

STYLES_PART = "word/styles.xml"
NUMBERING_PART = "word/numbering.xml"


@dataclass
class _State:
    paragraphs: list[Paragraph]
    tables: list[Table]
    images: list[Image]
    blocks: list
    page_setups: list[PageSetup]
    pending_break: bool = False
    last_body_paragraph: int | None = None


class DocumentReader:
    def __init__(self, styles_root, numbering_root) -> None:
        self.styles = StyleSheet(styles_root)
        self.numbering = NumberingResolver(numbering_root, self.styles)
        self.fields = FieldParser()
        self.st = _State([], [], [], [], [])
        self._open_tables_waiting_next: list[int] = []

    # --- абзац ------------------------------------------------------------------------------
    def _runs(self, content, res: ParaResolution) -> tuple[RunInfo, ...]:
        runs: list[RunInfo] = []
        for text, run in content.segments:
            props = self.styles.resolve_run(run, res)
            info = RunInfo(text, props.bold, props.italic, props.size_pt, props.font)
            if runs and (runs[-1].bold, runs[-1].italic, runs[-1].size_pt, runs[-1].font) == (
                info.bold, info.italic, info.size_pt, info.font,
            ):  # fmt: skip
                runs[-1] = RunInfo(runs[-1].text + text, *(info.bold, info.italic, info.size_pt,
                                                           info.font))  # fmt: skip
            else:
                runs.append(info)
        return tuple(runs)

    def _paragraph(
        self, p: etree._Element, table: TableContext | None, cell: CellRef | None
    ) -> Paragraph:
        ppr = p.find(qn("w:pPr"))
        idx = len(self.st.paragraphs) + 1
        num = self.numbering.label(ppr)
        res = self.styles.resolve_paragraph(p, table, num.level_ppr if num is not None else None)
        content = self.fields.feed_paragraph(p, idx)
        style_el = ppr.find(qn("w:pStyle")) if ppr is not None else None
        style_id = w_attr(style_el, "val") if style_el is not None else None
        style_id = style_id or self.styles.default_paragraph_style
        direct_break = bool(res.fmt.page_break_before and res.fmt.page_break_before.value)
        para = Paragraph(
            idx=idx,
            text=content.text,
            num_label=num.label if num is not None else None,
            style_id=style_id,
            style_name=self.styles.style_name(style_id),
            outline_level=res.outline_level,
            fmt=res.fmt,
            runs=self._runs(content, res),
            container="table_cell" if cell else "body",
            cell=cell,
            page_break_before=direct_break or self.st.pending_break,
        )
        self.st.pending_break = _ends_with_page_break(p, content.text)
        self.st.paragraphs.append(para)
        if cell is None:
            self.st.blocks.append(para)
            self.st.last_body_paragraph = idx
            for t_idx in self._open_tables_waiting_next:
                self._set_next(t_idx, idx)
            self._open_tables_waiting_next.clear()
        self._images(p, idx, table, cell)
        return para

    def _set_next(self, table_idx: int, para_idx: int) -> None:
        t = self.st.tables[table_idx - 1]
        self.st.tables[table_idx - 1] = _replace_table(t, next_paragraph_idx=para_idx)
        for i, b in enumerate(self.st.blocks):
            if isinstance(b, Table) and b.idx == table_idx:
                self.st.blocks[i] = self.st.tables[table_idx - 1]

    def _images(self, p, idx, table, cell) -> None:
        for raw in paragraph_images(p):
            tb: list[Paragraph] = []
            for tp in raw.textbox:
                fp = FieldParser()
                tres = self.styles.resolve_paragraph(tp)
                tcontent = fp.feed_paragraph(tp, idx)
                tppr = tp.find(qn("w:pPr"))
                sid_el = tppr.find(qn("w:pStyle")) if tppr is not None else None
                tb.append(
                    Paragraph(
                        idx=idx,
                        text=tcontent.text,
                        fmt=tres.fmt,
                        container="textbox",
                        style_id=w_attr(sid_el, "val") if sid_el is not None else None,
                        outline_level=tres.outline_level,
                        runs=self._runs(tcontent, tres),
                    )  # fmt: skip
                )
            self.st.images.append(
                Image(
                    idx=len(self.st.images) + 1,
                    paragraph_idx=idx,
                    kind=raw.kind,  # type: ignore[arg-type]
                    in_textbox=bool(raw.textbox),
                    textbox_paragraphs=tuple(tb),
                )  # fmt: skip
            )

    # --- таблица ----------------------------------------------------------------------------
    def _table(self, tbl: etree._Element, parent_idx: int | None) -> Table:
        props: TableProps = read_table_props(tbl)
        t_idx = len(self.st.tables) + 1
        look = parse_tbl_look(props.tbl_pr)
        rows_xml = live_rows(tbl)
        n_cols = len(props.grid_cols_cm) or max(
            (sum(grid_span(tc) for tc in cell_elements(tr)) for tr in rows_xml), default=0
        )
        anchor = len(self.st.blocks)
        placeholder = Table(
            idx=t_idx, anchor_block=anchor, prev_paragraph_idx=self.st.last_body_paragraph,
            grid_cols_cm=props.grid_cols_cm, width_cm=props.width_cm,
            width_type=props.width_type, layout_type=props.layout_type,
            style_id=props.style_id,
            style_exists=props.style_id is None or self.styles.style_exists(props.style_id),
            parent_table_idx=parent_idx,
        )  # fmt: skip
        self.st.tables.append(placeholder)
        if parent_idx is None:
            self.st.blocks.append(placeholder)
            self._open_tables_waiting_next.append(t_idx)
        rows = []
        for r_no, tr in enumerate(rows_xml, 1):
            tr_pr = tr.find(qn("w:trPr"))
            cells = []
            col = 1
            for tc in cell_elements(tr):
                span = grid_span(tc)
                tc_pr = tc.find(qn("w:tcPr"))
                ctx = TableContext(
                    style_id=props.style_id, row=r_no - 1, col=col - 1,
                    n_rows=len(rows_xml), n_cols=n_cols, look=look,
                    cnf=parse_cnf(tc_pr, tr_pr),
                    row_band_size=props.row_band_size, col_band_size=props.col_band_size,
                    tc_pr=tc_pr,
                )  # fmt: skip
                ref = CellRef(t_idx, r_no, col)
                paras = self._cell_content(tc, ctx, ref, t_idx)
                cells.append(
                    Cell(
                        row=r_no,
                        col=col,
                        text="\n".join(p.text for p in paras),
                        grid_span=span,
                        v_merge=v_merge(tc),
                        width=cell_width_cm(tc),
                        paragraphs=tuple(paras),
                    )  # fmt: skip
                )
                col += span
            rows.append(row_props(tr, tuple(cells)))
        table = _replace_table(placeholder, rows=tuple(rows))
        self.st.tables[t_idx - 1] = table
        if parent_idx is None:
            self.st.blocks[anchor] = table
        return table

    def _cell_content(self, tc, ctx: TableContext, ref: CellRef, t_idx: int) -> list[Paragraph]:
        paras: list[Paragraph] = []
        for child in iter_body_blocks(tc):
            if child.tag == W_P:
                if is_paragraph_removed(child):
                    continue
                paras.append(self._paragraph(child, ctx, ref))
            elif child.tag == W_TBL:
                self._table(child, t_idx)
        return paras

    # --- тело -------------------------------------------------------------------------------
    def read_body(self, body: etree._Element) -> None:
        for block in iter_body_blocks(body):
            if block.tag == W_P:
                if is_paragraph_removed(block):
                    continue
                self._paragraph(block, None, None)
                sect = block.find(qn("w:pPr") + "/" + qn("w:sectPr"))
                if sect is not None:
                    self.st.page_setups.append(
                        section_page_setup(sect, len(self.st.page_setups) + 1)
                    )
                    if (w_attr(sect.find(qn("w:type")), "val") or "nextPage") != "continuous":
                        self.st.pending_break = True
            else:
                self._table(block, None)
        last = body.find(qn("w:sectPr"))
        if last is not None:
            self.st.page_setups.append(section_page_setup(last, len(self.st.page_setups) + 1))

    def build(self, filename: str, sha256: str) -> Document:
        st = self.st
        warnings = tuple(self.numbering.warnings)
        fields: tuple[FieldRef, ...] = tuple(self.fields.completed)
        return Document(
            meta=DocMeta(filename=filename, sha256=sha256, warnings=warnings),
            page_setup=tuple(st.page_setups),
            blocks=tuple(st.blocks),
            paragraphs=tuple(st.paragraphs),
            tables=tuple(st.tables),
            images=tuple(st.images),
            fields=fields,
        )


def _ends_with_page_break(p: etree._Element, text: str) -> bool:
    """Абзац заканчивается разрывом страницы без текста после него: следующий начнёт страницу."""
    if text.strip():
        return False
    return any(br.get(qn("w:type")) == "page" for br in p.iter(qn("w:br")))


def _replace_table(table: Table, **changes) -> Table:
    from dataclasses import replace

    return replace(table, **changes)


def read_document(pkg: DocxPackage, filename: str, sha256: str) -> Document:
    """Плоская модель документа из открытого пакета."""
    body = pkg.xml(MAIN_PART).find(qn("w:body"))
    if body is None:
        from .package import DocxError

        raise DocxError("invalid_docx", "Файл повреждён: в документе нет тела.")
    reader = DocumentReader(pkg.xml_optional(STYLES_PART), pkg.xml_optional(NUMBERING_PART))
    reader.read_body(body)
    return reader.build(filename, sha256)
