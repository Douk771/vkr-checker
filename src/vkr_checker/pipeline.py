"""Конвейер проверки одного файла (ARCHITECTURE.md §4).

upload -> временный каталог -> параллельно: разбор .docx и вёрстка LibreOffice -> привязка
страниц (или откат) -> правила -> отчёт. Каталог и подпроцесс убираются в `finally`.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vkr_checker import __version__
from vkr_checker.checks.base import CheckContext
from vkr_checker.checks.engine import run_rules
from vkr_checker.checks.registry import all_rules
from vkr_checker.config import Settings
from vkr_checker.diff.compare import build_compare_report
from vkr_checker.diff.model import Side
from vkr_checker.docx.package import DocxError, DocxPackage, PackageLimits
from vkr_checker.docx.reader import read_document
from vkr_checker.layout.estimate import Volume, compute_volume
from vkr_checker.layout.outcome import LayoutOutcome, compute_layout, with_layout
from vkr_checker.layout.soffice import SofficeInfo, SofficeRunner
from vkr_checker.matrix.build import build_matrix, failed_matrix
from vkr_checker.model.document import Document
from vkr_checker.report.build import assemble_check_report
from vkr_checker.report.schema import (
    CheckReport,
    CompareReport,
    FileInfo,
    LayoutInfo,
    VolumeInfo,
    VolumeSection,
)
from vkr_checker.structure import analyze_structure
from vkr_checker.thresholds import DEFAULT_THRESHOLDS, Thresholds
from vkr_checker.web.ports import InputFileError
from vkr_checker.web.upload import UploadedFile

log = logging.getLogger("vkr_checker.pipeline")

DISCLAIMER_OK = "Страницы определены по вёрстке LibreOffice, возможна погрешность ±1–2 страницы."
DISCLAIMER_PARTIAL = (
    "Вёрстка LibreOffice привязана к тексту частично: страницы приблизительные, "
    "проверки по страницам дают не выше подозрения."
)
DISCLAIMER_FAILED = "Вёрстка недоступна: объём оценён по тексту, номера страниц не показываются."
LAYOUT_JOIN_GRACE_S = 5


@dataclass(frozen=True)
class Analysis:
    """Разобранный документ и отчёт по нему (compare использует оба)."""

    doc: Document
    report: CheckReport
    ctx: CheckContext


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def layout_info_of(doc: Document, outcome: LayoutOutcome) -> LayoutInfo:
    lay = doc.layout
    if lay is None:
        return LayoutInfo(status="failed", reason=outcome.reason, disclaimer=DISCLAIMER_FAILED)
    return LayoutInfo(
        status=lay.status,
        engine=lay.engine,
        page_count=lay.page_count,
        coverage=lay.coverage,
        font_substitutions=list(lay.font_substitutions),
        disclaimer=DISCLAIMER_OK if lay.status == "ok" else DISCLAIMER_PARTIAL,
    )


def volume_info_of(vol: Volume) -> VolumeInfo:
    return VolumeInfo(
        method=vol.method,  # type: ignore[arg-type]
        pages_main=vol.pages_main,
        by_section=[VolumeSection(title=t, pages=p) for t, p in vol.by_section],
        estimate_formula=vol.formula,
    )


class CheckPipeline:
    """Реализует web.ports.Pipeline: проверка одного файла и сравнение двух версий."""

    def __init__(
        self,
        settings: Settings,
        layout_info: SofficeInfo,
        th: Thresholds = DEFAULT_THRESHOLDS,
    ) -> None:
        self._limits = PackageLimits(settings.max_unzipped_bytes, settings.max_zip_entries)
        self._th = th
        self._info = layout_info
        self._runner = (
            SofficeRunner(layout_info, settings.layout_timeout_s, settings.layout_concurrency)
            if layout_info.available
            else None
        )
        self._grace_s = settings.layout_timeout_s + LAYOUT_JOIN_GRACE_S

    # --- публичный порт -------------------------------------------------------------------
    def check(self, file: UploadedFile) -> CheckReport:
        return self.analyze(file).report

    def compare(self, old: UploadedFile, new: UploadedFile) -> CompareReport:
        """Обе версии разбираются параллельно, затем строится diff (B-60..B-64)."""
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="compare") as pool:
            f_old = pool.submit(self.analyze, old)
            f_new = pool.submit(self.analyze, new)
            first_error: BaseException | None = None
            results: list[Analysis] = []
            for fut in (f_old, f_new):
                try:
                    results.append(fut.result())
                except InputFileError as exc:
                    first_error = first_error or exc
            if first_error is not None:
                raise first_error
        a_old, a_new = results
        started = time.monotonic()
        report = build_compare_report(
            Side(a_old.doc, a_old.ctx, a_old.report),
            Side(a_new.doc, a_new.ctx, a_new.report),
            service_version=__version__,
            checked_at=datetime.now(timezone.utc),  # noqa: UP017
            th=self._th,
        )
        log.info("compare diff=%.2fs", time.monotonic() - started)
        return report

    # --- разбор ---------------------------------------------------------------------------
    def analyze(self, file: UploadedFile) -> Analysis:
        started = time.monotonic()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="layout")
        future: Future[Path] | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="vkr-pipe-") as work:
                try:
                    pkg = DocxPackage.open(file.path, self._limits)
                except DocxError as exc:
                    raise InputFileError(file.field, exc.code, exc.message) from exc
                with pkg:
                    if self._runner is not None:
                        future = executor.submit(self._runner.convert_to_pdf, file.path, Path(work))
                    sha = sha256_of(file.path)
                    try:
                        doc = analyze_structure(read_document(pkg, file.name, sha), self._th)
                    except DocxError as exc:
                        raise InputFileError(file.field, exc.code, exc.message) from exc
                parsed = time.monotonic()
                outcome = self._join_layout(doc, future)
                future = None  # результат учтён; PDF удалится вместе с каталогом
                doc = with_layout(doc, outcome)
                laid_out = time.monotonic()
                report, ctx = self._build_report(doc, outcome, file, sha)
        finally:
            if future is not None:
                self._drain(future)
            executor.shutdown(wait=True)
        log.info(
            "check name=%.40s size=%d parse=%.2fs layout_wait=%.2fs checks=%.2fs layout=%s",
            file.name, file.size, parsed - started, laid_out - parsed,
            time.monotonic() - laid_out, report.layout.status,
        )  # fmt: skip
        return Analysis(doc, report, ctx)

    def _join_layout(self, doc: Document, future: Future[Path] | None) -> LayoutOutcome:
        if future is None:
            return LayoutOutcome(None, "LibreOffice не найден")
        return compute_layout(doc, future.result, engine=self._info.engine, th=self._th)

    def _drain(self, future: Future[Path]) -> None:
        """Ждёт завершения вёрстки перед удалением каталога (подпроцесс пишет в него)."""
        if future.cancel():
            return
        try:
            future.result(timeout=self._grace_s)
        except Exception:  # noqa: BLE001, S110 - итог вёрстки уже не важен
            pass

    def _build_report(
        self, doc: Document, outcome: LayoutOutcome, file: UploadedFile, sha: str
    ) -> tuple[CheckReport, CheckContext]:
        ctx = CheckContext.build(doc, self._th)
        results = run_rules(ctx, all_rules())
        try:
            matrix = build_matrix(ctx)
        except Exception as exc:  # noqa: BLE001 - матрица не должна ронять проверку
            log.error("матрица не построена: %s", type(exc).__name__)
            matrix = failed_matrix()
        report = assemble_check_report(
            doc,
            results,
            file=FileInfo(name=file.name, size_bytes=file.size, sha256=sha),
            layout=layout_info_of(doc, outcome),
            volume=volume_info_of(compute_volume(doc, self._th)),
            matrix=matrix,
            service_version=__version__,
            checked_at=datetime.now(timezone.utc),  # noqa: UP017 - проект поддерживает 3.10
            th=self._th,
        )
        return report, ctx
