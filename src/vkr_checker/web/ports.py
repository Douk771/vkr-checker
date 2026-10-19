"""Порт между HTTP-слоем и конвейером (реализация - pipeline.py, B-23)."""

from __future__ import annotations

from typing import Protocol

from vkr_checker.report.schema import CheckReport, CompareReport

from .upload import UploadedFile


class InputFileError(Exception):
    """Входной файл не принят; `field` - какой именно (old | new | file)."""

    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.code = code
        self.message = message


class Pipeline(Protocol):
    """Синхронный конвейер: вызывается из рабочего потока, не из цикла событий."""

    def check(self, file: UploadedFile) -> CheckReport | dict: ...

    def compare(self, old: UploadedFile, new: UploadedFile) -> CompareReport | dict: ...
