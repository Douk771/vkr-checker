"""Реестр синтетических фикстур: имя -> байты. Новые фикстуры добавляются сюда."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable

from . import variants

OLE_HEAD = bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 1024


def _zip(parts: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in parts.items():
            zf.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), data)
    return buf.getvalue()


BUILDERS: dict[str, Callable[[], bytes]] = {
    "clean_20p": lambda: variants.clean(20).to_bytes(),
    "clean_70p": lambda: variants.clean(70).to_bytes(),
    "clean_150p": lambda: variants.clean(150).to_bytes(),
    "rule_STR-01_no_conclusion": lambda: variants.missing_section("CONCLUSION").to_bytes(),
    "rule_STR-01_no_intro": lambda: variants.missing_section("INTRO").to_bytes(),
    "rule_TBL-01_indent": lambda: variants.table_indent().to_bytes(),
    "bad_pdf_as_docx": lambda: b"%PDF-1.7\n" + b"0" * 256,
    "bad_doc_as_docx": lambda: OLE_HEAD,
    "bad_empty": lambda: b"",
    "bad_odt_as_docx": lambda: _zip(
        {
            "mimetype": b"application/vnd.oasis.opendocument.text",
            "content.xml": b"<office:document-content/>",
        }
    ),  # fmt: skip
    "bad_zipbomb": lambda: _zip(
        {"word/document.xml": b"<w:document/>", "word/bomb.bin": b"\0" * (260 * 1024 * 1024)}
    ),  # fmt: skip
}

# Ожидаемые результаты для rule_* и diff_* (проверяются тестами правил в волнах 2-3).
EXPECTED: dict[str, dict[str, str]] = {
    "clean_20p": {},
    "clean_70p": {},
    "rule_STR-01_no_conclusion": {"STR-01": "violation"},
    "rule_STR-01_no_intro": {"STR-01": "violation"},
    "rule_TBL-01_indent": {"TBL-01": "violation"},
}

HEAVY_FIXTURES = {"bad_zipbomb"}  # большие по размеру: не собираются по умолчанию
