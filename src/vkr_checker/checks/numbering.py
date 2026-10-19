"""NUM-01..03: нумерация подписей, ссылки на объекты, фраза с числом объектов."""

from __future__ import annotations

import re
from collections import Counter

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.facts.common import chapter_number, section_kind_of
from vkr_checker.checks.registry import register
from vkr_checker.checks.rulehelpers import MAIN_KINDS, mention_location, table_in_main_part
from vkr_checker.model.document import Caption, Document
from vkr_checker.model.finding import Finding
from vkr_checker.nlp.sentences import split_sentences

KIND_NAME = {"table": "Таблица", "figure": "Рисунок"}
KIND_GEN = {"table": "таблицы", "figure": "рисунка"}


class _NumRule:
    block = "numbering"
    source = Source("CH", "Нумерация и ссылки на таблицы и рисунки")
    default_level = "violation"
    needs: frozenset[Need] = frozenset()
    priority = "must"


def _int_parts(caption: Caption) -> list[int] | None:
    try:
        return [int(x) for x in caption.number_parts]
    except ValueError:
        return None


def _scheme(caption: Caption) -> str:
    return "by_chapter" if len(caption.number_parts) >= 2 else "continuous"


def _caption_loc(ctx: CheckContext, caption: Caption):
    if caption.paragraph_idx is not None:
        return [ctx.loc.paragraph(caption.paragraph_idx)]
    return []


def _fmt_caption(caption: Caption) -> str:
    return f"{KIND_NAME[caption.kind]} {caption.number}"


@register
class Num01CaptionNumbering(_NumRule):
    id = "NUM-01"
    title = "Нумерация таблиц и рисунков"

    def run(self, ctx: CheckContext):
        doc, out = ctx.doc, []
        for kind in ("table", "figure"):
            caps = [c for c in doc.captions if c.kind == kind]
            out += self._sequence(ctx, [c for c in caps if not c.in_appendix], appendix=False)
            out += self._sequence(ctx, [c for c in caps if c.in_appendix], appendix=True)
        out += self._stale(ctx)
        out += self._without_caption(ctx)
        out += self._orphan_captions(ctx)
        return result_of(self, out)

    def _sequence(self, ctx: CheckContext, caps: list[Caption], appendix: bool) -> list[Finding]:
        if len(caps) < 1:
            return []
        out: list[Finding] = []
        kind = caps[0].kind
        where = "appendix" if appendix else "main"
        schemes = Counter(_scheme(c) for c in caps)
        majority = schemes.most_common(1)[0][0]
        if len(schemes) > 1:
            minority = [c for c in caps if _scheme(c) != majority]
            out.append(self._finding(
                ctx, minority[0], f"NUM-01|mixed|{kind}|{where}",
                f"Смешаны схемы нумерации: {_fmt_caption(minority[0])} не соответствует "
                f"остальным подписям ({'по главам' if majority == 'by_chapter' else 'сквозная'}).",
                values={"schemes": dict(sorted(schemes.items()))},
            ))  # fmt: skip
        groups: dict[str, list[Caption]] = {}
        for c in caps:
            if _scheme(c) != majority:
                continue
            prefix = ".".join(c.number_parts[:-1]) if majority == "by_chapter" else ""
            groups.setdefault(prefix, []).append(c)
        for prefix, items in groups.items():
            out += self._check_group(ctx, items, prefix, kind, where)
        if majority == "by_chapter" and not appendix:
            out += self._chapter_prefix(ctx, caps, kind)
        return out

    def _check_group(self, ctx, items: list[Caption], prefix: str, kind: str, where: str):
        out: list[Finding] = []
        nums: list[int] = []
        for c in items:
            try:
                nums.append(int(c.number_parts[-1]))
            except (ValueError, IndexError):
                continue
        expected = 1
        seen: set[int] = set()
        for c, n in zip(items, nums, strict=False):
            fp = f"NUM-01|{kind}|{where}|{prefix}"
            if n in seen:
                out.append(self._finding(ctx, c, f"{fp}|dup|{n}",
                           f"Номер повторяется: {_fmt_caption(c)}."))  # fmt: skip
            elif n > expected:
                out.append(self._finding(ctx, c, f"{fp}|gap|{n}",
                           f"Пропущен номер {prefix + '.' if prefix else ''}{expected}: после "
                           f"подписи идёт {_fmt_caption(c)}."))  # fmt: skip
                expected = n + 1
            elif n < expected:
                out.append(self._finding(ctx, c, f"{fp}|order|{n}",
                           f"Нарушен порядок: {_fmt_caption(c)} стоит после номера "
                           f"{prefix + '.' if prefix else ''}{expected - 1}."))  # fmt: skip
            else:
                expected = n + 1
            seen.add(n)
        return out

    def _chapter_prefix(self, ctx: CheckContext, caps: list[Caption], kind: str):
        out = []
        for c in caps:
            if _scheme(c) != "by_chapter" or c.paragraph_idx is None:
                continue
            para = ctx.doc.paragraph(c.paragraph_idx)
            chapter = chapter_number(ctx.doc, para.section_id)
            if (
                chapter is not None
                and c.number_parts[0].isdigit()
                and int(c.number_parts[0]) != chapter
            ):
                out.append(self._finding(
                    ctx, c, f"NUM-01|{kind}|chapter|{c.number_parts[0]}|{chapter}",
                    f"{_fmt_caption(c)} стоит в главе {chapter}, а номер начинается с "
                    f"{c.number_parts[0]}.",
                ))  # fmt: skip
        return out

    def _stale(self, ctx: CheckContext) -> list[Finding]:
        return [
            self._finding(
                ctx,
                c,
                f"NUM-01|stale|{c.kind}|{c.number}",
                f"Номер {_fmt_caption(c)} задан полем SEQ, которое, вероятно, не обновили "
                "(номер повторяется).",
                level="suspicion",
                hint="Выделите всё (Ctrl+A) и нажмите F9, чтобы обновить поля.",
            )  # fmt: skip
            for c in ctx.doc.captions
            if c.seq_field_stale_suspect
        ]

    def _without_caption(self, ctx: CheckContext) -> list[Finding]:
        doc, out = ctx.doc, []
        for t in doc.tables:
            kind = section_kind_of(doc, t.section_id)
            if (
                t.parent_table_idx is None
                and t.caption_idx is None
                and kind not in ("TITLE", "TOC")
            ):
                out.append(new_finding(
                    self, f"У таблицы №{t.idx} нет подписи.",
                    fingerprint=f"NUM-01|nocap|table|{t.idx}", method="regex",
                    locations=[ctx.loc.cell(t.idx, 1, 1)] if t.rows else [],
                    hint="Подпись «Таблица N - Название» ставится над таблицей.",
                ))  # fmt: skip
        for img in doc.images:
            if img.caption_idx is not None or img.paragraph_idx is None:
                continue
            para = doc.paragraph(img.paragraph_idx)
            if section_kind_of(doc, para.section_id) in ("TITLE", "TOC", "UNKNOWN"):
                continue
            out.append(new_finding(
                self, f"У рисунка в абзаце {para.idx} нет подписи.",
                fingerprint=f"NUM-01|nocap|figure|{img.idx}", method="regex",
                locations=[ctx.loc.paragraph(para.idx)],
                hint="Подпись «Рисунок N - Название» ставится под рисунком.",
            ))  # fmt: skip
        return out

    def _orphan_captions(self, ctx: CheckContext) -> list[Finding]:
        return [
            self._finding(
                ctx,
                c,
                f"NUM-01|orphan|{c.kind}|{c.number}",
                f"Подпись «{_fmt_caption(c)}» есть, а {KIND_GEN[c.kind]} рядом не найдено.",
                level="suspicion",
            )  # fmt: skip
            for c in ctx.doc.captions
            if c.target is None
        ]

    def _finding(self, ctx, caption, fingerprint, message, *, level=None, hint=None, values=None):
        return new_finding(
            self, message, fingerprint=fingerprint, level=level, method="regex",
            locations=_caption_loc(ctx, caption), hint=hint, values=values,
        )  # fmt: skip


def _object_paragraph(doc: Document, caption: Caption) -> int | None:
    """Абзац объекта: подпись; для рисунка в надписи - абзац, где он лежит."""
    if caption.paragraph_idx is not None:
        return caption.paragraph_idx
    if caption.image_idx is not None:
        return next(
            (i.paragraph_idx for i in doc.images if i.idx == caption.image_idx), None
        )  # fmt: skip
    return None


@register
class Num02References(_NumRule):
    id = "NUM-02"
    title = "Ссылки на таблицы и рисунки"

    def run(self, ctx: CheckContext):
        doc, out = ctx.doc, []
        refs_by: dict[tuple[str, str], list] = {}
        for r in ctx.facts.refs:
            if r.kind in ("table", "figure"):
                refs_by.setdefault((r.kind, r.target), []).append(r)
        known = {(c.kind, c.number) for c in doc.captions}
        for caption in doc.captions:
            if not caption.number.replace(".", "").isdigit():
                continue  # номера приложений («А.1») по ссылкам не сверяем
            obj_par = _object_paragraph(doc, caption)
            own = [
                r for r in refs_by.get((caption.kind, caption.number), [])
                if r.loc.paragraph_idx != caption.paragraph_idx
            ]  # fmt: skip
            label = _fmt_caption(caption)
            if not own:
                out.append(new_finding(
                    self, f"На {label} нет ссылки в тексте.",
                    fingerprint=f"NUM-02|noref|{caption.kind}|{caption.number}", method="regex",
                    locations=_caption_loc(ctx, caption),
                    hint="Сошлитесь на объект до его появления: «(табл. 1)», «на рис. 2».",
                ))  # fmt: skip
                continue
            first = min(r.loc.paragraph_idx or 0 for r in own)
            if obj_par is not None and first > obj_par + ctx.th.REF_FAR_PARAS:
                out.append(new_finding(
                    self, f"Первая ссылка на {label} стоит далеко от самого объекта "
                    f"(через {first - obj_par} абзацев).",
                    fingerprint=f"NUM-02|far|{caption.kind}|{caption.number}",
                    level="suspicion", method="regex", locations=_caption_loc(ctx, caption),
                    values={"distance_paragraphs": first - obj_par},
                ))  # fmt: skip
        for (kind, target), refs in sorted(refs_by.items()):
            if (kind, target) in known or not target.replace(".", "").isdigit():
                continue
            out.append(new_finding(
                self, f"Есть ссылка на несуществующий объект: {KIND_NAME[kind].lower()} {target}.",
                fingerprint=f"NUM-02|missing|{kind}|{target}", method="regex",
                locations=[mention_location(ctx, refs[0].loc)],
            ))  # fmt: skip
        return result_of(self, out)


_PHRASE_VERB = re.compile(r"содерж|включа|состо|насчитыва|име\w+\s+\d|объём|объем", re.IGNORECASE)
_COUNT = re.compile(
    r"(?P<n>\d+)\s+(?:(?:литературн|библиографическ)\w+\s+)?"
    r"(?P<noun>рисунк\w*|таблиц\w*|приложени\w*|источник\w*)",
    re.IGNORECASE,
)
_NOUN_KEY = {"рисунк": "figure", "таблиц": "table", "приложени": "appendix", "источник": "source"}
_NOUN_RU = {
    "figure": "рисунков",
    "table": "таблиц",
    "appendix": "приложений",
    "source": "источников",
}


def _count_main(ctx: CheckContext) -> dict[str, int]:
    doc = ctx.doc
    figures = sum(
        1
        for i in doc.images
        if i.paragraph_idx is not None
        and section_kind_of(doc, doc.paragraph(i.paragraph_idx).section_id) in MAIN_KINDS
    )
    tables = sum(1 for t in doc.tables if table_in_main_part(ctx, t))
    return {
        "figure": figures,
        "table": tables,
        "appendix": len(doc.appendices),
        "source": len(doc.bibliography),
    }


@register
class Num03TotalsPhrase(_NumRule):
    id = "NUM-03"
    title = "Фраза о числе рисунков и таблиц"

    def run(self, ctx: CheckContext):
        actual = _count_main(ctx)
        found: dict[str, tuple[int, int]] = {}  # вид -> (заявленное число, абзац)
        for p in ctx.doc.paragraphs:
            if p.cell is not None or section_kind_of(ctx.doc, p.section_id) in (
                "BIBLIOGRAPHY",
                "TOC",
            ):
                continue
            for s in split_sentences(p.text):
                if not _PHRASE_VERB.search(s.text):
                    continue
                for m in _COUNT.finditer(s.text):
                    key = next(
                        v for k, v in _NOUN_KEY.items() if m.group("noun").lower().startswith(k)
                    )
                    found.setdefault(key, (int(m.group("n")), p.idx))
        out: list[Finding] = []
        if not any(k in found for k in ("figure", "table")) and (
            actual["figure"] or actual["table"]
        ):
            out.append(new_finding(
                self, "Во введении или заключении не найдена фраза о числе рисунков и таблиц "
                "(например, «В работе содержится N рисунков и M таблиц»).",
                fingerprint="NUM-03|absent", level="suspicion", method="regex",
                values=actual, hint="Приложения в этой фразе отдельно не учитываются.",
            ))  # fmt: skip
        for key, (declared, par) in sorted(found.items()):
            if declared != actual[key]:
                out.append(new_finding(
                    self, f"В тексте указано {declared} {_NOUN_RU[key]}, а в работе их "
                    f"{actual[key]} (приложения в основной части не считаются).",
                    fingerprint=f"NUM-03|{key}", method="regex",
                    locations=[ctx.loc.paragraph(par)],
                    values={"declared": declared, "actual": actual[key]},
                ))  # fmt: skip
        return result_of(self, out, counts=actual)
