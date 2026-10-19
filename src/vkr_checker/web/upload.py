"""Приём multipart: поля-файлы -> файлы во временном каталоге, лимиты размера (API_CONTRACT §4)."""

from __future__ import annotations

import ntpath
import shutil
from dataclasses import dataclass
from pathlib import Path

from starlette.datastructures import UploadFile
from starlette.requests import Request

from .errors import ApiError

NAME_MAX = 200
COPY_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class UploadedFile:
    field: str
    name: str  # basename, не длиннее NAME_MAX
    size: int
    path: Path


def safe_basename(raw: str | None) -> str:
    """Только имя файла: без путей (в т.ч. Windows-стиля) и управляющих символов, до NAME_MAX."""
    name = ntpath.basename((raw or "").replace("\x00", "")).strip()
    name = "".join(ch for ch in name if ch.isprintable())
    return (name or "document.docx")[:NAME_MAX]


async def receive_files(
    request: Request, fields: tuple[str, ...], dest: Path, max_bytes: int
) -> dict[str, UploadedFile]:
    """Читает multipart, возвращает по одному файлу на каждое имя из `fields`.

    Ошибки: bad_request (не multipart, лишние части, повтор поля), missing_file (поля нет
    или файл пустой), file_too_large. Тело читает Starlette потоково, крупные части
    попадают на диск, а не в память.
    """
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise ApiError("bad_request", "Ожидается запрос multipart/form-data с файлом.")
    try:
        form = await request.form(max_files=len(fields) + 1, max_fields=len(fields) + 1)
    except ApiError:
        raise
    except Exception as exc:  # разбор multipart упал: битая граница, превышение числа частей
        raise ApiError("bad_request", "Не удалось разобрать multipart-запрос.") from exc

    result: dict[str, UploadedFile] = {}
    try:
        items = form.multi_items()
        for field in fields:
            matches = [v for k, v in items if k == field]
            if not matches or not isinstance(matches[0], UploadFile):
                raise ApiError("missing_file", field=field)
        if len(items) > len(fields) or any(k not in fields for k, _ in items):
            raise ApiError("bad_request", "В запросе лишние поля или файлы.")
        for field in fields:
            matches = [v for k, v in items if k == field]
            result[field] = _save(matches[0], field, dest, max_bytes)
    finally:
        await form.close()
    return result


def _save(upload: UploadFile, field: str, dest: Path, max_bytes: int) -> UploadedFile:
    target = dest / f"{field}.docx"
    size = 0
    upload.file.seek(0)
    with target.open("wb") as out:
        while chunk := upload.file.read(COPY_CHUNK):
            size += len(chunk)
            if size > max_bytes:
                raise ApiError(
                    "file_too_large",
                    f"Файл больше {max_bytes // (1024 * 1024)} МБ.",
                    field=field,
                )
            out.write(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise ApiError("missing_file", field=field)
    return UploadedFile(field=field, name=safe_basename(upload.filename), size=size, path=target)


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
