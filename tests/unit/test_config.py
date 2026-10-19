import pytest
from pydantic import ValidationError

from vkr_checker.config import Settings


def make(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(f"VKR_{k.upper()}", v)
    return Settings(_env_file=None)


def test_defaults_local(monkeypatch):
    s = make(monkeypatch)
    assert (s.mode, s.host, s.port) == ("local", "127.0.0.1", 8000)
    assert s.auth_required is False
    assert s.max_upload_bytes == 20 * 1024 * 1024
    assert (s.check_timeout_s, s.compare_timeout_s, s.max_concurrent_jobs) == (90, 150, 2)


def test_server_requires_password(monkeypatch):
    with pytest.raises(ValidationError):
        make(monkeypatch, mode="server")


def test_server_defaults(monkeypatch):
    s = make(monkeypatch, mode="server", password="x")
    assert s.host == "0.0.0.0" and s.auth_required is True


def test_local_ignores_password(monkeypatch):
    assert make(monkeypatch, password="x").password is None
