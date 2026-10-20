"""STR-01..06 и PAGE-01 (ARCHITECTURE_CHECKS.md §4)."""

from __future__ import annotations

import re
from statistics import median

from rapidfuzz import fuzz

from vkr_checker.checks.base import CheckContext, Need, Source, new_finding, result_of
from vkr_checker.checks.facts.common import paragraphs_in, section_kind_of
from vkr_checker.checks.registry import register
from vkr_checker.checks.rulehelpers import mention_location
from vkr_checker.checks.textfmt import fmt_num
from vkr_checker.model.document import Document, Section
from vkr_checker.model.finding import Finding, RuleResult
from vkr_checker.nlp.morph import content_lemmas
from vkr_checker.nlp.sentences import split_sentences

REQUIRED_TITLES = {
    "TITLE": "титульный лист",
    "TOC": "оглавление",
    "INTRO": "введение",
    "CONCLUSION": "заключение",
    "BIBLIOGRAPHY": "список литературы",
    "APPENDIX": "приложения",
}
ORDER = ("TITLE", "TOC", "INTRO", "CHAPTER", "CONCLUSION", "BIBLIOGRAPHY", "APPENDIX")
_ORDER_TITLES = {**REQUIRED_TITLES, "CHAPTER": "главы"}
_CONCL_HEAD = re.compile(r"^\s*выводы\b", re.IGNORECASE)
_APPENDIX_TITLE = re.compile(r"^\s*приложение\s+(?:[А-ЯA-Z]\b|\d+)", re.IGNORECASE)
MIN_DUP_LEMMAS = 5
PAGE_LEFT_CM = 3.0
PAGE_RIGHT_CM = 1.5


def _heading_loc(ctx: CheckContext, section: Section):
    return (
        [ctx.loc.paragraph(section.heading_paragraph_idx)] if section.heading_paragraph_idx else []
    )


def _has_kind(doc: Document, kind: str) -> bool:
    if kind == "TOC" and doc.toc is not None:
        return True
    if kind == "APPENDIX" and doc.appendices:
        return True
    return any(s.kind == kind for s in doc.sections)


@register
class Str01RequiredSections:
    id = "STR-01"
    title = "Обязательные разделы"
    block = "structure"
    source = Source("M", "Обязательные разделы работы")
    default_level = "violation"
    needs: frozenset[Need] = frozenset()
    priority = "must"

    def run(self, ctx: CheckContext):
        doc = ctx.doc
        out: list[Finding] = []
        for kind, name in REQUIRED_TITLES.items():
            if _has_kind(doc, kind):
                continue
            level = "suspicion" if kind == "TITLE" else "violation"
            hint = (
                "Титульный лист определяется по первым абзацам до оглавления."
                if kind == "TITLE"
                else None
            )
            out.append(
                new_finding(
                    self,
                    f"Не найден раздел: {name}.",
                    fingerprint=f"STR-01|missing|{kind}",
                    level=level,
                    values={"missing": kind},
                    hint=hint,
                )  # fmt: skip
            )
        chapters = [s for s in doc.sections if s.kind == "CHAPTER"]
        if len(chapters) != 2:
            out.append(
                new_finding(
                    self,
                    f"Глав в работе: {len(chapters)}; по методичке их две (теория и эмпирика).",
                    fingerprint="STR-01|chapters",
                    level="suspicion",
                    values={"chapters": len(chapters)},
                    hint="Число глав остаётся на усмотрение руководителя.",
                )  # fmt: skip
            )
        out.extend(self._order(ctx))
        return result_of(self, out)

    def _order(self, ctx: CheckContext) -> list[Finding]:
        seen: list[str] = []
        for s in ctx.doc.sections:
            if s.kind in ORDER and (not seen or seen[-1] != s.kind) and s.kind not in seen:
                seen.append(s.kind)
        expected = [k for k in ORDER if k in seen]
        if seen == expected:
            return []
        names = lambda ks: " → ".join(_ORDER_TITLES[k] for k in ks)  # noqa: E731
        return [
            new_finding(
                self,
                f"Порядок разделов: {names(seen)}; ожидается: {names(expected)}.",
                fingerprint="STR-01|order",
                level="suspicion",
                values={"actual": seen, "expected": expected},
            )  # fmt: skip
        ]


@register
class Str02TocVsHeadings:
    id = "STR-02"
    title = "Оглавление против заголовков"
    block = "structure"
    source = Source("CH", "Оглавление и заголовки")
    default_level = "violation"
    needs = frozenset({Need.TOC})
    priority = "must"

    def run(self, ctx: CheckContext):
        doc = ctx.doc
        assert doc.toc is not None
        out: list[Finding] = []
        resolved: set[str] = set()
        for e in doc.toc.entries:
            if e.resolved_section_id:
                resolved.add(e.resolved_section_id)
            elif e.level <= 2:
                locs = [ctx.loc.paragraph(e.paragraph_idx)] if e.paragraph_idx else []
                out.append(
                    new_finding(
                        self,
                        f"Пункт оглавления «{e.text}» не найден среди заголовков.",
                        fingerprint=f"STR-02|toc|{e.text}",
                        locations=locs,
                        method="fuzzy",
                        values={"entry": e.text},
                        hint="Обновите оглавление в Word: ссылки на заголовки устарели.",
                    )  # fmt: skip
                )
        for s in doc.sections:
            is_main = s.kind == "CHAPTER" or (s.kind == "SUBSECTION" and s.level <= 2)
            if is_main and s.id not in resolved:
                label = f"{s.number} {s.title}".strip() if s.number else s.title
                out.append(
                    new_finding(
                        self,
                        f"Заголовок «{label}» отсутствует в оглавлении.",
                        fingerprint=f"STR-02|heading|{label}",
                        locations=_heading_loc(ctx, s),
                        method="fuzzy",
                        values={"heading": label},
                        hint="Обновите оглавление в Word.",
                    )  # fmt: skip
                )
        return result_of(self, out)


@register
class Str03ChapterConclusions:
    id = "STR-03"
    title = "Выводы к главам"
    block = "structure"
    source = Source("M", "Выводы по главам")
    default_level = "violation"
    needs = frozenset({Need.CH1, Need.CH2})
    priority = "must"

    def _has_conclusions(self, ctx: CheckContext, chapter: Section) -> bool:
        doc = ctx.doc
        for s in doc.sections:
            if s.kind != "CHAPTER_CONCLUSIONS":
                continue
            parent = doc.section_by_id(s.parent_id)
            seen: set[str] = set()
            while parent is not None and parent.id != chapter.id and parent.id not in seen:
                seen.add(parent.id)
                parent = doc.section_by_id(parent.parent_id)
            if parent is not None and parent.id == chapter.id:
                return True
        tail = paragraphs_in(doc, chapter)[-ctx.th.CH_CONCL_TAIL_PARAS :]
        return any(_CONCL_HEAD.match(p.text) for p in tail)

    def run(self, ctx: CheckContext):
        chapters = [s for s in ctx.doc.sections if s.kind == "CHAPTER"][:2]
        out: list[Finding] = []
        for chapter in chapters:
            if self._has_conclusions(ctx, chapter):
                continue
            name = f"{chapter.number} {chapter.title}".strip() if chapter.number else chapter.title
            out.append(
                new_finding(
                    self,
                    f"В конце главы «{name}» нет выводов.",
                    fingerprint=f"STR-03|{chapter.id}",
                    locations=_heading_loc(ctx, chapter),
                    method="regex",
                    hint="Добавьте «Выводы по главе» в конец главы.",
                )  # fmt: skip
            )
        return result_of(self, out)


@register
class Str04ConclusionDuplicates:
    id = "STR-04"
    title = "Заключение не дублирует выводы глав"
    block = "structure"
    source = Source("M", "Заключение и выводы по главам")
    default_level = "suspicion"
    needs = frozenset({Need.CONCLUSION, Need.CH_CONCLUSIONS})
    priority = "should"

    @staticmethod
    def _sentences(doc: Document, section: Section):
        for p in paragraphs_in(doc, section):
            if p.idx == section.heading_paragraph_idx:
                continue
            for s in split_sentences(p.text):
                lemmas = content_lemmas(s.text)
                if len(lemmas) >= MIN_DUP_LEMMAS:
                    yield p.idx, s, " ".join(lemmas)

    def run(self, ctx: CheckContext):
        doc = ctx.doc
        concl = next(s for s in doc.sections if s.kind == "CONCLUSION")
        chapter_sentences = [
            item
            for sec in doc.sections
            if sec.kind == "CHAPTER_CONCLUSIONS"
            for item in self._sentences(doc, sec)
        ]
        out: list[Finding] = []
        for idx, sent, key in self._sentences(doc, concl):
            for c_idx, c_sent, c_key in chapter_sentences:
                ratio = fuzz.ratio(key, c_key)
                if ratio < ctx.th.STR04_DUP_RATIO:
                    continue
                out.append(
                    new_finding(
                        self,
                        "Предложение заключения почти дословно повторяет вывод главы.",
                        fingerprint=f"STR-04|{idx}|{c_idx}|{c_sent.start}",
                        locations=[
                            ctx.loc.paragraph(c_idx, (c_sent.start, c_sent.end)),
                            ctx.loc.paragraph(idx, (sent.start, sent.end)),
                        ],
                        method="fuzzy",
                        values={"ratio": round(ratio, 1)},
                        hint="В заключении подведите итоги целиком, а не повторяйте выводы глав.",
                    )  # fmt: skip
                )
                break
        return result_of(self, out)


_APPENDICES_HEAD = re.compile(r"^\s*приложени[яе]\s*$", re.IGNORECASE)


def _breaks_page(para) -> bool:
    fmt = para.fmt.page_break_before
    return bool(para.page_break_before) or (fmt is not None and fmt.value is True)


@register
class Str05Appendices:
    id = "STR-05"
    title = "Приложения"
    block = "structure"
    source = Source("CH", "Оформление приложений")
    default_level = "violation"
    needs = frozenset({Need.APPENDICES})
    priority = "must"

    @staticmethod
    def _starts_new_page(ctx: CheckContext, appendix, section) -> bool:
        if appendix.starts_new_page:
            return True
        idx = section.heading_paragraph_idx if section else None
        if idx is None:
            return False
        para = ctx.doc.paragraph(idx)
        if _breaks_page(para):
            return True
        # первое приложение сразу под общим заголовком «ПРИЛОЖЕНИЯ» (между ними только
        # пустые абзацы): страницу открывает этот заголовок
        j = idx - 1
        while j >= 0 and not ctx.doc.paragraph(j).text.strip():
            j -= 1
        if (
            j >= 0
            and _APPENDICES_HEAD.match(ctx.doc.paragraph(j).text)
            and _breaks_page(ctx.doc.paragraph(j))
        ):
            return True
        page, prev = ctx.doc.page_of_paragraph(idx), ctx.doc.page_of_paragraph(idx - 1)
        return page is not None and prev is not None and page > prev

    def run(self, ctx: CheckContext):
        doc = ctx.doc
        referenced = {
            r.target.upper()
            for r in ctx.facts.refs
            if r.kind == "appendix"
            and r.loc.paragraph_idx is not None
            and section_kind_of(doc, doc.paragraph(r.loc.paragraph_idx).section_id) != "APPENDIX"
        }
        out: list[Finding] = []
        for a in doc.appendices:
            section = doc.section_by_id(a.section_id)
            label = a.label or a.key
            locs = _heading_loc(ctx, section) if section else []
            heading = (
                f"{a.label} {a.title}".strip() if a.label else (section.title if section else "")
            )
            if not _APPENDIX_TITLE.match(heading):
                out.append(
                    new_finding(
                        self,
                        f"Приложение «{heading or label}» не озаглавлено как «Приложение N».",
                        fingerprint=f"STR-05|title|{a.key}",
                        locations=locs,
                        method="regex",
                        hint="Заголовок: «Приложение А», ниже название.",
                    )  # fmt: skip
                )
            if not self._starts_new_page(ctx, a, section):
                out.append(
                    new_finding(
                        self,
                        f"{label} не начинается с новой страницы.",
                        fingerprint=f"STR-05|page|{a.key}",
                        locations=locs,
                        method="layout" if doc.layout else "style",
                        hint="Поставьте разрыв страницы или «С новой страницы» перед приложением.",
                    )  # fmt: skip
                )
            if a.key.upper() not in referenced:
                out.append(
                    new_finding(
                        self,
                        f"На {label} нет ссылки в тексте работы.",
                        fingerprint=f"STR-05|ref|{a.key}",
                        locations=locs,
                        method="regex",
                        hint="Сошлитесь на приложение в основной части: «(см. Приложение А)».",
                    )  # fmt: skip
                )
        known = {a.key.upper() for a in doc.appendices}
        reported: set[str] = set()
        for r in ctx.facts.refs:
            target = r.target.upper()
            if (
                r.kind != "appendix"
                or target in known
                or target in reported
                or r.loc.paragraph_idx is None
                or section_kind_of(doc, doc.paragraph(r.loc.paragraph_idx).section_id) == "APPENDIX"
            ):
                continue
            reported.add(target)
            out.append(
                new_finding(
                    self,
                    f"В тексте есть ссылка на «Приложение {target}», но такого приложения нет.",
                    fingerprint=f"STR-05|dangling|{target}",
                    locations=[mention_location(ctx, r.loc)],
                    method="regex",
                    hint="Добавьте приложение или исправьте обозначение в ссылке.",
                )  # fmt: skip
            )
        return result_of(self, out)


# Нумерация страниц Word может начинаться не с первой страницы PDF (титул без
# номера и т.п.). Сдвиг принимаем, только если он небольшой и с ним сходится
# большинство пунктов оглавления; иначе (оглавление целиком устарело) сравниваем
# без сдвига — медиана по устаревшему оглавлению дала бы бессмысленные, в том
# числе отрицательные, номера страниц.
MAX_TOC_OFFSET = 3


def _toc_offset(diffs: list[int], tolerance: int) -> int:
    candidate = round(median(diffs))
    if abs(candidate) > MAX_TOC_OFFSET:
        return 0
    agree = sum(1 for d in diffs if abs(d - candidate) <= tolerance)
    return candidate if agree * 2 > len(diffs) else 0


@register
class Str06TocPages:
    id = "STR-06"
    title = "Номера страниц в оглавлении"
    block = "structure"
    source = Source("CH", "Оглавление")
    default_level = "suspicion"
    needs = frozenset({Need.TOC, Need.LAYOUT})
    priority = "should"

    def run(self, ctx: CheckContext):
        doc = ctx.doc
        assert doc.toc is not None
        pairs = []
        for e in doc.toc.entries:
            sec = doc.section_by_id(e.resolved_section_id)
            if e.page_num is None or sec is None or sec.heading_paragraph_idx is None:
                continue
            actual = doc.page_of_paragraph(sec.heading_paragraph_idx)
            if actual is not None:
                pairs.append((e, sec, actual))
        if not pairs:
            return result_of(self, [])
        offset = _toc_offset([actual - e.page_num for e, _, actual in pairs], ctx.th.PAGE_TOLERANCE)
        out: list[Finding] = []
        for e, sec, actual in pairs:
            diff = actual - e.page_num - offset
            if abs(diff) <= ctx.th.PAGE_TOLERANCE:
                continue
            out.append(
                new_finding(
                    self,
                    f"В оглавлении «{e.text}» стоит стр. {e.page_num}, по вёрстке LibreOffice "
                    f"заголовок примерно на стр. {int(actual - offset)}.",
                    fingerprint=f"STR-06|{sec.id}",
                    method="layout",
                    locations=_heading_loc(ctx, sec),
                    values={"toc_page": e.page_num, "layout_page": int(actual - offset)},
                    hint="Обновите оглавление в Word (LibreOffice и Word расходятся на 1-2 стр.).",
                )  # fmt: skip
            )
        return result_of(self, out)


@register
class Page01Margins:
    id = "PAGE-01"
    title = "Поля страницы"
    block = "structure"
    source = Source("CH", "Поля страницы")
    default_level = "violation"
    needs: frozenset[Need] = frozenset()
    priority = "must"

    def run(self, ctx: CheckContext) -> RuleResult:
        setups = ctx.doc.page_setup
        if not setups:
            finding = new_finding(
                self, "Поля страницы не удалось прочитать, проверка PAGE-01 пропущена.",
                fingerprint="PAGE-01|not_run", level="suspicion",
            ).model_copy(update={"not_run": True})  # fmt: skip
            return result_of(self, [finding]).model_copy(
                update={"outcome": "not_run", "skipped_reason": "поля страницы не прочитаны"}
            )
        tol = ctx.th.MARGIN_TOL_CM
        out: list[Finding] = []
        for ps in setups:
            for side, actual, wanted in (
                ("left", ps.margin_left_cm, PAGE_LEFT_CM),
                ("right", ps.margin_right_cm, PAGE_RIGHT_CM),
            ):
                if actual is None or abs(actual - wanted) <= tol:
                    continue
                name = "Левое" if side == "left" else "Правое"
                out.append(
                    new_finding(
                        self,
                        f"{name} поле {fmt_num(actual)} см, требуется {fmt_num(wanted)} см.",
                        fingerprint=f"PAGE-01|{side}|{fmt_num(actual)}",
                        method="style",
                        values={"side": side, "actual_cm": actual, "expected_cm": wanted},
                        hint="Поля: левое 3 см, правое 1,5 см.",
                    )  # fmt: skip
                )
        return result_of(self, out)
