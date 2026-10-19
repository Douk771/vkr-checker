"""Запуск LibreOffice headless для вёрстки (ARCHITECTURE.md §8.2).

Вход - санитизированная копия .docx (внешние связи вырезаны), отдельный профиль на запуск,
жёсткий таймаут с убийством всей группы процессов, семафор на число одновременных запусков.
Любой сбой - LayoutError: вёрстка не является ошибкой HTTP, конвейер откатывается на оценку.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from vkr_checker.docx.xmlutil import NS, parse_xml

log = logging.getLogger("vkr_checker.layout")

MAC_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
PROBE_TIMEOUT_S = 30
INPUT_NAME = "layout_input.docx"
OUTPUT_NAME = "layout_input.pdf"
ATTACHED_TEMPLATE = f"{{{NS['w']}}}attachedTemplate"
REL_TAG = f"{{{NS['rel']}}}Relationship"


class LayoutError(Exception):
    """Вёрстка не получена; `reason` безопасен для показа (без путей и текста работы)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SofficeInfo:
    path: str | None
    engine: str | None  # "LibreOffice 24.2.1.2" | None

    @property
    def available(self) -> bool:
        return self.path is not None and self.engine is not None


def find_soffice(configured: str | None = None) -> str | None:
    """Путь к soffice: VKR_SOFFICE_PATH -> PATH -> стандартный путь macOS."""
    candidates: list[str | None] = []
    if configured:
        candidates.append(configured)
    candidates += [shutil.which("soffice"), shutil.which("libreoffice"), MAC_SOFFICE]
    for cand in candidates:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def parse_version(output: str) -> str | None:
    """'LibreOffice 24.2.1.2 4c8...' -> 'LibreOffice 24.2.1.2'."""
    parts = output.strip().split()
    if len(parts) >= 2 and parts[0].lower().startswith("libreoffice"):
        return f"LibreOffice {parts[1]}"
    return None


def probe_soffice(configured: str | None = None) -> SofficeInfo:
    """`soffice --version`; результат кладётся в /api/health (layout_available, layout_engine)."""
    path = find_soffice(configured)
    if path is None:
        return SofficeInfo(None, None)
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("soffice --version не отработал: %s", type(exc).__name__)
        return SofficeInfo(None, None)
    engine = parse_version(proc.stdout) if proc.returncode == 0 else None
    return SofficeInfo(path if engine else None, engine)


def _strip_external_rels(data: bytes) -> bytes:
    root = parse_xml(data)
    for rel in list(root.findall(REL_TAG)):
        if rel.get("TargetMode") == "External":
            root.remove(rel)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _strip_attached_template(data: bytes) -> bytes:
    root = parse_xml(data)
    for el in list(root.iter(ATTACHED_TEMPLATE)):
        el.getparent().remove(el)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def sanitize_docx(src: Path, dst: Path) -> None:
    """Копия .docx без внешних связей: LibreOffice не должен ничего грузить из сети/диска.

    Вырезаются Relationship с TargetMode="External" во всех .rels (ссылки, внешние
    картинки, OLE-связи, присоединённый шаблон) и w:attachedTemplate в settings.xml.
    """
    try:
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename.endswith(".rels"):
                    data = _strip_external_rels(data)
                elif info.filename == "word/settings.xml":
                    data = _strip_attached_template(data)
                zout.writestr(info.filename, data)
    except (zipfile.BadZipFile, ValueError, OSError) as exc:
        raise LayoutError("не удалось подготовить копию файла для вёрстки") from exc


def build_command(soffice: str, profile_dir: Path, outdir: Path, docx: Path) -> list[str]:
    return [
        soffice,
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--nodefault",
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(outdir),
        str(docx),
    ]


def _kill_group(proc: subprocess.Popen) -> None:
    """SIGKILL всей группы: soffice порождает soffice.bin."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        log.error("процесс soffice не завершился после SIGKILL")


class SofficeRunner:
    """Конвертирует .docx в PDF. Потокобезопасен: число одновременных запусков ограничено."""

    def __init__(self, info: SofficeInfo, timeout_s: int, concurrency: int) -> None:
        self.info = info
        self.timeout_s = timeout_s
        self._sem = threading.BoundedSemaphore(concurrency)

    def convert_to_pdf(self, docx: Path, workdir: Path) -> Path:
        """PDF в `workdir`; любой сбой -> LayoutError. Профиль и копия лежат внутри workdir."""
        if not self.info.available or self.info.path is None:
            raise LayoutError("LibreOffice не найден")
        run_dir = Path(workdir) / "lo-run"
        profile = run_dir / "profile"
        home = run_dir / "home"
        out = run_dir / "out"
        for d in (profile, home, out):
            d.mkdir(parents=True, exist_ok=True)
        sanitized = run_dir / INPUT_NAME
        sanitize_docx(docx, sanitized)
        cmd = build_command(self.info.path, profile, out, sanitized)
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "LANG": "C.UTF-8"}
        with self._sem:
            proc = subprocess.Popen(  # noqa: S603 - команда собрана из доверенных частей
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            try:
                proc.wait(timeout=self.timeout_s)
            except subprocess.TimeoutExpired:
                _kill_group(proc)
                raise LayoutError(f"вёрстка не уложилась в {self.timeout_s} с") from None
            except BaseException:
                _kill_group(proc)
                raise
            finally:
                _kill_group(
                    proc
                )  # добивает и осиротевший soffice.bin; безвредно, если группы уже нет
        if proc.returncode != 0:
            raise LayoutError("LibreOffice завершился с ошибкой")
        pdf = out / OUTPUT_NAME
        if not pdf.is_file() or pdf.stat().st_size == 0:
            raise LayoutError("LibreOffice не создал PDF")
        return pdf
