"""Сравнение версий через конвейер как модуль (soffice нет, файлы - минимальные docx)."""

from dataclasses import replace

import pytest

from tests.unit.test_pipeline import make_docx, pipeline  # noqa: F401 - фикстура
from vkr_checker.report.schema import CompareReport
from vkr_checker.web.ports import InputFileError

OLD = ["Introduction to the study", "Sample was 50 people in total today", "Same closing line here"]
NEW = ["Introduction to the study", "Sample was 60 people in total today", "Same closing line here"]


def as_field(upload, field):
    return replace(upload, field=field)


def test_compare_builds_full_report(pipeline, tmp_path):  # noqa: F811
    old = as_field(make_docx(tmp_path / "old.docx", OLD), "old")
    new = as_field(make_docx(tmp_path / "new.docx", NEW), "new")
    report = pipeline.compare(old, new)
    assert isinstance(report, CompareReport)
    assert report.old.file.name == "old.docx" and report.new.file.name == "new.docx"
    assert [(c.old, c.new) for c in report.diff.number_changes] == [("50", "60")]
    assert list(pipeline.scratch.iterdir()) == []


def test_compare_bad_file_reports_which_field(pipeline, tmp_path):  # noqa: F811
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip at all")
    good = as_field(make_docx(tmp_path / "good.docx", OLD), "new")
    old = as_field(make_docx(tmp_path / "x.docx", OLD), "old")
    old = replace(old, path=bad, name="bad.docx")
    with pytest.raises(InputFileError) as err:
        pipeline.compare(old, good)
    assert err.value.field == "old"
