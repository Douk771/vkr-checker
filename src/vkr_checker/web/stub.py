"""Временная заглушка конвейера: отдаёт golden-JSON (до B-23). Не использовать в проде."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import ApiError
from .upload import UploadedFile

_GOLDEN = Path(__file__).resolve().parents[3] / "tests" / "golden"


def _load(name: str) -> dict:
    path = _GOLDEN / name
    if not path.is_file():
        raise ApiError("internal_error", "Заглушка конвейера недоступна: нет golden-файлов.")
    return json.loads(path.read_text(encoding="utf-8"))


class StubPipeline:
    def check(self, file: UploadedFile) -> dict:
        data = _load("check_clean.json")
        data["file"] = {**data["file"], "name": file.name, "size_bytes": file.size}
        return data

    def compare(self, old: UploadedFile, new: UploadedFile) -> dict:
        return _load("compare.json")
