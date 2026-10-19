"""Отчёты настоящего конвейера на синтетике валидны по openapi.yaml (B-70); soffice отключён."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from tests.fixtures.builders.registry import EXPECTED
from vkr_checker.config import Settings
from vkr_checker.layout.soffice import SofficeInfo
from vkr_checker.pipeline import CheckPipeline
from vkr_checker.web.upload import UploadedFile

ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "api" / "openapi.yaml").read_text(encoding="utf-8"))


def _errors(data: dict, schema: str) -> list[str]:
    v = Draft202012Validator(
        {"$ref": f"#/components/schemas/{schema}", "components": SPEC["components"]}
    )
    return [f"{list(e.absolute_path)}: {e.message[:150]}" for e in v.iter_errors(data)]


def _dump(report) -> dict:
    return json.loads(report.model_dump_json(by_alias=True, exclude_none=False))


@pytest.fixture(scope="module")
def pipe():
    return CheckPipeline(Settings(_env_file=None), SofficeInfo(None, None))


def _upload(path: Path) -> UploadedFile:
    return UploadedFile("file", path.name, path.stat().st_size, path)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_check_report_valid_and_levels(pipe, fixture_path, name):
    report = pipe.check(_upload(fixture_path(name)))
    data = _dump(report)
    assert not _errors(data, "CheckReport")
    findings = [f for b in data["blocks"] for r in b["rule_results"] for f in r["findings"]]
    levels = {f["rule_id"]: f["level"] for f in findings}
    for rule, level in EXPECTED[name].items():
        assert levels.get(rule) == level, f"{name}: {rule}"


def test_compare_report_valid(pipe, fixture_path):
    report = pipe.compare(
        _upload(fixture_path("clean_20p")), _upload(fixture_path("rule_TBL-01_indent"))
    )
    assert not _errors(_dump(report), "CompareReport")


def test_clean_fixture_has_no_violations(pipe, fixture_path):
    data = _dump(pipe.check(_upload(fixture_path("clean_70p"))))
    findings = [f for b in data["blocks"] for r in b["rule_results"] for f in r["findings"]]
    flagged = [f for f in findings if f["level"] in ("violation", "suspicion") and not f["not_run"]]
    assert not flagged
