import os
import signal
import subprocess
import zipfile
from pathlib import Path

import pytest

from vkr_checker.layout import soffice as so
from vkr_checker.layout.soffice import (
    LayoutError,
    SofficeInfo,
    SofficeRunner,
    build_command,
    find_soffice,
    parse_version,
    probe_soffice,
    sanitize_docx,
)

RELS = (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="styles" Target="styles.xml"/>'
    '<Relationship Id="rId2" Type="hyperlink" Target="http://evil.example/x"'
    ' TargetMode="External"/>'
    '<Relationship Id="rId3" Type="oleObject" Target="file:///etc/passwd" TargetMode="External"/>'
    "</Relationships>"
)
SETTINGS = (
    '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<w:attachedTemplate r:id="rId9"/><w:zoom w:percent="100"/></w:settings>'
)


def make_docx(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", "<d/>")
        zf.writestr("word/_rels/document.xml.rels", RELS)
        zf.writestr("word/settings.xml", SETTINGS)
    return path


def test_parse_version():
    assert parse_version("LibreOffice 24.2.1.2 4c8c7ff7c0fa\n") == "LibreOffice 24.2.1.2"
    assert parse_version("") is None
    assert parse_version("something else 1.0") is None


def test_find_soffice_prefers_configured_then_path(tmp_path, monkeypatch):
    fake = tmp_path / "soffice"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    assert find_soffice(str(fake)) == str(fake)
    monkeypatch.setattr(so.shutil, "which", lambda n: str(fake) if n == "soffice" else None)
    assert find_soffice(None) == str(fake)
    monkeypatch.setattr(so.shutil, "which", lambda n: None)
    monkeypatch.setattr(so, "MAC_SOFFICE", str(tmp_path / "missing"))
    assert find_soffice(str(tmp_path / "nope")) is None


def test_probe_reports_version(monkeypatch):
    monkeypatch.setattr(so, "find_soffice", lambda c=None: "/x/soffice")
    done = subprocess.CompletedProcess([], 0, stdout="LibreOffice 7.6.4.1 abc\n", stderr="")
    monkeypatch.setattr(so.subprocess, "run", lambda *a, **k: done)
    info = probe_soffice()
    assert info == SofficeInfo("/x/soffice", "LibreOffice 7.6.4.1")
    assert info.available


def test_probe_without_soffice_or_on_failure(monkeypatch):
    monkeypatch.setattr(so, "find_soffice", lambda c=None: None)
    assert not probe_soffice().available
    monkeypatch.setattr(so, "find_soffice", lambda c=None: "/x/soffice")

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("soffice", 1)

    monkeypatch.setattr(so.subprocess, "run", boom)
    assert not probe_soffice().available
    bad = subprocess.CompletedProcess([], 1, stdout="", stderr="err")
    monkeypatch.setattr(so.subprocess, "run", lambda *a, **k: bad)
    assert not probe_soffice().available


def test_sanitize_removes_external_links_and_template(tmp_path):
    src = make_docx(tmp_path / "in.docx")
    dst = tmp_path / "out.docx"
    sanitize_docx(src, dst)
    with zipfile.ZipFile(dst) as zf:
        rels = zf.read("word/_rels/document.xml.rels").decode()
        settings = zf.read("word/settings.xml").decode()
        assert zf.read("word/document.xml") == b"<d/>"
    assert "evil.example" not in rels
    assert "file:///" not in rels
    assert 'Target="styles.xml"' in rels
    assert "attachedTemplate" not in settings
    assert "w:zoom" in settings
    with zipfile.ZipFile(src) as zf:  # исходник не тронут
        assert "evil.example" in zf.read("word/_rels/document.xml.rels").decode()


def test_sanitize_bad_zip_becomes_layout_error(tmp_path):
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(LayoutError):
        sanitize_docx(bad, tmp_path / "o.docx")


def test_build_command_has_isolated_profile_and_headless_flags(tmp_path):
    cmd = build_command("/x/soffice", tmp_path / "pro file", tmp_path / "out", tmp_path / "a.docx")
    assert cmd[0] == "/x/soffice"
    assert {"--headless", "--norestore", "--nolockcheck", "--nodefault"} <= set(cmd)
    profile = next(c for c in cmd if c.startswith("-env:UserInstallation="))
    assert profile.startswith("-env:UserInstallation=file://")
    assert "pro%20file" in profile
    assert "pdf:writer_pdf_Export" in cmd


class FakeProc:
    def __init__(self, pid=4242, returncode=0, hang=False, on_wait=None):
        self.pid, self.returncode, self.hang, self.on_wait = pid, returncode, hang, on_wait
        self.waits = 0

    def wait(self, timeout=None):
        self.waits += 1
        if self.hang and self.waits == 1:
            raise subprocess.TimeoutExpired("soffice", timeout)
        if self.on_wait:
            self.on_wait()
        return self.returncode

    def poll(self):
        return self.returncode


@pytest.fixture
def runner():
    return SofficeRunner(SofficeInfo("/x/soffice", "LibreOffice 24.2"), timeout_s=3, concurrency=1)


def patch_popen(monkeypatch, proc, killed):
    captured = {}

    def popen(cmd, **kwargs):
        captured["cmd"], captured["kwargs"] = cmd, kwargs
        return proc

    monkeypatch.setattr(so.subprocess, "Popen", popen)
    monkeypatch.setattr(so.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    return captured


def test_timeout_kills_whole_process_group(runner, monkeypatch, tmp_path):
    killed = []
    patch_popen(monkeypatch, FakeProc(hang=True), killed)
    with pytest.raises(LayoutError) as exc:
        runner.convert_to_pdf(make_docx(tmp_path / "in.docx"), tmp_path)
    assert "3 с" in exc.value.reason
    assert (4242, signal.SIGKILL) in killed


def test_nonzero_exit_is_layout_error(runner, monkeypatch, tmp_path):
    patch_popen(monkeypatch, FakeProc(returncode=77), [])
    with pytest.raises(LayoutError):
        runner.convert_to_pdf(make_docx(tmp_path / "in.docx"), tmp_path)


def test_missing_pdf_is_layout_error(runner, monkeypatch, tmp_path):
    patch_popen(monkeypatch, FakeProc(), [])
    with pytest.raises(LayoutError):
        runner.convert_to_pdf(make_docx(tmp_path / "in.docx"), tmp_path)


def test_success_returns_pdf_and_uses_sanitized_copy_in_new_session(runner, monkeypatch, tmp_path):
    def write_pdf():
        (tmp_path / "lo-run" / "out" / so.OUTPUT_NAME).write_bytes(b"%PDF-1.4 x")

    captured = patch_popen(monkeypatch, FakeProc(on_wait=write_pdf), [])
    pdf = runner.convert_to_pdf(make_docx(tmp_path / "in.docx"), tmp_path)
    assert pdf.read_bytes().startswith(b"%PDF")
    assert captured["kwargs"]["start_new_session"] is True
    assert captured["cmd"][-1] == str(tmp_path / "lo-run" / so.INPUT_NAME)
    assert str(tmp_path / "in.docx") not in captured["cmd"]
    env = captured["kwargs"]["env"]
    assert Path(env["HOME"]).is_relative_to(tmp_path)  # профиль и HOME внутри temp dir запроса
    assert os.environ.get("HOME") != env["HOME"]


def test_unavailable_engine_is_layout_error(tmp_path):
    runner = SofficeRunner(SofficeInfo(None, None), 3, 1)
    with pytest.raises(LayoutError):
        runner.convert_to_pdf(tmp_path / "x.docx", tmp_path)
