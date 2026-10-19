"""Конвейер как модуль: вызовы напрямую, soffice подменён (без сети и без реального LibreOffice)."""

import zipfile
from pathlib import Path

import pytest

from tests.unit.test_layout_align import _tiny_pdf
from vkr_checker.config import Settings
from vkr_checker.layout.soffice import LayoutError, SofficeInfo
from vkr_checker.pipeline import CheckPipeline
from vkr_checker.web.ports import InputFileError
from vkr_checker.web.upload import UploadedFile

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
TEXTS = [
    "Introduction to the study",
    "The first paragraph about motivation",
    "The second paragraph about adaptation",
]


def make_docx(path: Path, texts=TEXTS) -> UploadedFile:
    body = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in texts)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", f"<w:document {W}><w:body>{body}</w:body></w:document>")
    return UploadedFile("file", path.name, path.stat().st_size, path)


class FakeRunner:
    def __init__(self, pdf_pages=None, error=None):
        self.pdf_pages, self.error, self.workdirs = pdf_pages, error, []

    def convert_to_pdf(self, docx: Path, workdir: Path) -> Path:
        self.workdirs.append(workdir)
        assert workdir.is_dir() and docx.is_file()
        if self.error:
            raise self.error
        out = workdir / "lo-run" / "out"
        out.mkdir(parents=True)
        pdf = out / "document.pdf"
        pdf.write_bytes(_tiny_pdf(self.pdf_pages))
        return pdf


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(scratch))
    pipe = CheckPipeline(Settings(_env_file=None), SofficeInfo(None, None))
    pipe.scratch = scratch
    return pipe


def test_layout_failure_gives_estimate_report_and_cleans_temp(pipeline, tmp_path):
    pipeline._runner = FakeRunner(error=LayoutError("вёрстка не уложилась в 20 с"))
    report = pipeline.check(make_docx(tmp_path / "a.docx"))
    assert report.layout.status == "failed"
    assert report.layout.reason == "вёрстка не уложилась в 20 с"
    assert report.volume.method == "estimate"
    assert report.file.name == "a.docx" and len(report.file.sha256) == 64
    assert list(pipeline.scratch.iterdir()) == []  # временных файлов после запроса нет


def test_layout_ok_uses_pdf_pages(pipeline, tmp_path):
    runner = FakeRunner(pdf_pages=[" ".join(TEXTS[:2]), TEXTS[2]])
    pipeline._runner = runner
    report = pipeline.check(make_docx(tmp_path / "a.docx"))
    assert report.layout.status == "ok"
    assert report.layout.page_count == 2 and report.layout.coverage == 1.0
    assert list(pipeline.scratch.iterdir()) == []
    assert not runner.workdirs[0].exists()


def test_no_soffice_means_failed_layout_with_reason(pipeline, tmp_path):
    report = pipeline.check(make_docx(tmp_path / "a.docx"))
    assert report.layout.status == "failed" and "LibreOffice" in report.layout.reason
    assert report.layout.disclaimer


def test_invalid_docx_is_input_error_before_layout_starts(pipeline, tmp_path):
    runner = FakeRunner(pdf_pages=["x"])
    pipeline._runner = runner
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"%PDF-1.7 not a docx")
    with pytest.raises(InputFileError) as exc:
        pipeline.check(UploadedFile("file", "bad.docx", 19, bad))
    assert exc.value.code == "unsupported_format" and exc.value.field == "file"
    assert runner.workdirs == [] and list(pipeline.scratch.iterdir()) == []


def test_rule_crash_does_not_leave_files(pipeline, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("сбой сборки отчёта")

    monkeypatch.setattr("vkr_checker.pipeline.assemble_check_report", boom)
    pipeline._runner = FakeRunner(pdf_pages=["x"])
    with pytest.raises(RuntimeError):
        pipeline.check(make_docx(tmp_path / "a.docx"))
    assert list(pipeline.scratch.iterdir()) == []


def test_report_is_deterministic_apart_from_time(pipeline, tmp_path):
    f = make_docx(tmp_path / "a.docx")
    a, b = pipeline.check(f), pipeline.check(f)
    assert a.model_dump(exclude={"checked_at"}) == b.model_dump(exclude={"checked_at"})


def test_reader_failure_waits_for_layout_before_temp_removal(pipeline, tmp_path, monkeypatch):
    """soffice ещё пишет в work, когда падает разбор: каталог удаляется только после ожидания."""
    import threading
    import time

    state = {"finished_at": None, "removed_before_finish": False}

    class SlowRunner(FakeRunner):
        def convert_to_pdf(self, docx, workdir):
            started.set()
            time.sleep(0.3)
            state["removed_before_finish"] = not workdir.exists()
            state["finished_at"] = time.monotonic()
            raise LayoutError("поздно")

    started = threading.Event()

    def bad_reader(*a, **k):
        started.wait(2)
        raise RuntimeError("сбой разбора")

    monkeypatch.setattr("vkr_checker.pipeline.read_document", bad_reader)
    pipeline._runner = SlowRunner()
    with pytest.raises(RuntimeError):
        pipeline.check(make_docx(tmp_path / "a.docx"))
    assert state["finished_at"] is not None
    assert state["removed_before_finish"] is False
    assert list(pipeline.scratch.iterdir()) == []
