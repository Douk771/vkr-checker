"""Безопасное открытие .docx: zip-лимиты, сигнатуры, коды ошибок (ARCHITECTURE.md §6.1)."""

from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .xmlutil import NS, XmlParseError, parse_xml

ZIP_SIGNATURE = b"PK\x03\x04"
OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
ENCRYPTED_MARKER = "EncryptedPackage".encode("utf-16-le")
MAIN_PART = "word/document.xml"
SCAN_CHUNK = 1024 * 1024


class DocxError(Exception):
    """Файл нельзя принять. `code`: unsupported_format | invalid_docx | docx_limits_exceeded."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PackageLimits:
    max_unzipped_bytes: int = 200 * 1024 * 1024
    max_entries: int = 2000


def _sniff(path: Path) -> None:
    """Не-zip по сигнатуре, не по расширению: .doc/.pdf/.rtf -> 415, docx с паролем -> 422."""
    with path.open("rb") as fh:
        head = fh.read(8)
        if head[:4] == ZIP_SIGNATURE:
            return
        if head == OLE_SIGNATURE:
            # OLE: либо старый .doc/.xls (415), либо .docx под паролем (422)
            fh.seek(0)
            tail = b""
            while chunk := fh.read(SCAN_CHUNK):
                if ENCRYPTED_MARKER in tail + chunk:
                    raise DocxError(
                        "invalid_docx",
                        "Документ защищён паролем. Снимите пароль в Word и загрузите снова.",
                    )
                tail = chunk[-len(ENCRYPTED_MARKER) :]
    raise DocxError(
        "unsupported_format",
        "Нужен файл .docx. Сохраните документ в Word как .docx и загрузите снова.",
    )


def _check_name(name: str) -> None:
    norm = name.replace("\\", "/")
    if (
        norm.startswith("/")
        or "\x00" in name
        or ".." in posixpath.normpath(norm).split("/")
        or (len(norm) > 1 and norm[1] == ":")
    ):
        raise DocxError("invalid_docx", "Файл повреждён: недопустимые пути внутри архива.")


class DocxPackage:
    """Открытый .docx. Чтение частей ограничено фактическим, а не заявленным размером."""

    def __init__(self, zf: zipfile.ZipFile, limits: PackageLimits) -> None:
        self._zf = zf
        self._limits = limits
        self._read_total = 0
        self._names = {i.filename for i in zf.infolist()}

    @classmethod
    def open(cls, path: Path, limits: PackageLimits | None = None) -> DocxPackage:
        limits = limits or PackageLimits()
        _sniff(path)
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise DocxError("invalid_docx", "Файл повреждён или не является .docx.") from exc
        try:
            infos = zf.infolist()
            if len(infos) > limits.max_entries:
                raise DocxError("docx_limits_exceeded", "В файле слишком много внутренних частей.")
            if sum(i.file_size for i in infos) > limits.max_unzipped_bytes:
                raise DocxError(
                    "docx_limits_exceeded", "Содержимое файла после распаковки слишком велико."
                )
            seen: set[str] = set()
            for info in infos:
                _check_name(info.filename)
                if info.filename in seen:
                    raise DocxError("invalid_docx", "Файл повреждён: повторяющиеся части.")
                seen.add(info.filename)
                if info.flag_bits & 0x1:
                    raise DocxError("invalid_docx", "Документ защищён паролем.")
            if MAIN_PART not in seen:
                raise DocxError(
                    "unsupported_format",
                    "Это не документ Word: нужен файл .docx. Сохраните документ в Word как .docx.",
                )
            return cls(zf, limits)
        except BaseException:
            zf.close()
            raise

    def close(self) -> None:
        self._zf.close()

    def __enter__(self) -> DocxPackage:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def names(self) -> list[str]:
        return sorted(self._names)

    def has(self, name: str) -> bool:
        return name in self._names

    def read(self, name: str) -> bytes:
        """Байты части; лимит распаковки считается по фактическим байтам, не по заголовкам."""
        if name not in self._names:
            raise KeyError(name)
        budget = self._limits.max_unzipped_bytes - self._read_total
        try:
            with self._zf.open(name) as fh:
                data = fh.read(budget + 1)
        except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
            raise DocxError("invalid_docx", "Файл повреждён: часть не читается.") from exc
        if len(data) > budget:
            raise DocxError(
                "docx_limits_exceeded", "Содержимое файла после распаковки слишком велико."
            )
        self._read_total += len(data)
        return data

    def xml(self, name: str) -> etree._Element:
        try:
            return parse_xml(self.read(name))
        except XmlParseError as exc:
            raise DocxError(
                "invalid_docx", f"Файл повреждён: часть {name} не разбирается."
            ) from exc

    def xml_optional(self, name: str) -> etree._Element | None:
        return self.xml(name) if self.has(name) else None

    def relationships(self, part: str = MAIN_PART) -> dict[str, tuple[str, str, bool]]:
        """rId -> (type, target, is_external) для части; пусто, если .rels нет."""
        directory, base = posixpath.split(part)
        rels_name = posixpath.join(directory, "_rels", base + ".rels")
        root = self.xml_optional(rels_name)
        result: dict[str, tuple[str, str, bool]] = {}
        if root is None:
            return result
        for rel in root.findall(f"{{{NS['rel']}}}Relationship"):
            result[rel.get("Id", "")] = (
                rel.get("Type", ""),
                rel.get("Target", ""),
                rel.get("TargetMode") == "External",
            )
        return result
