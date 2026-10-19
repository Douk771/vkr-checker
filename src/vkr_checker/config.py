"""Настройки сервиса: переменные окружения VKR_* (ARCHITECTURE.md §2.2, API_CONTRACT.md §4)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VKR_", env_file=".env", extra="ignore")

    mode: Literal["local", "server"] = "local"
    host: str | None = None
    port: int = Field(8000, ge=1, le=65535)
    password: str | None = None
    soffice_path: str | None = None
    extra_fonts_dir: str | None = None
    layout_timeout_s: int = Field(20, ge=1)
    layout_concurrency: int = Field(2, ge=1)
    max_upload_mb: int = Field(20, ge=1)
    max_unzipped_mb: int = Field(200, ge=1)
    max_zip_entries: int = Field(2000, ge=1)
    max_json_mb: int = Field(5, ge=1)
    max_concurrent_jobs: int = Field(2, ge=2, description="compare занимает 2 слота")
    check_timeout_s: int = Field(90, ge=1)
    compare_timeout_s: int = Field(150, ge=1)
    session_ttl_h: int = Field(12, ge=1)
    login_rate_per_min: int = Field(5, ge=1)
    trust_proxy: bool = False
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _check_mode(self) -> Settings:
        if self.mode == "server" and not self.password:
            raise ValueError("VKR_PASSWORD обязателен при VKR_MODE=server")
        if self.mode == "local":
            self.password = None
        if self.host is None:
            self.host = "0.0.0.0" if self.mode == "server" else "127.0.0.1"
        return self

    @property
    def auth_required(self) -> bool:
        return self.mode == "server"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_json_bytes(self) -> int:
        return self.max_json_mb * 1024 * 1024

    @property
    def max_unzipped_bytes(self) -> int:
        return self.max_unzipped_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
