"""Golden-JSON валидны по схемам api/openapi.yaml (без сервера и сети)."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "api" / "openapi.yaml").read_text(encoding="utf-8"))
CASES = [
    ("check_clean.json", "CheckReport"),
    ("check_findings.json", "CheckReport"),
    ("check_layout_failed.json", "CheckReport"),
    ("compare.json", "CompareReport"),
]


@pytest.mark.parametrize(("fname", "schema"), CASES)
def test_golden_matches_schema(fname, schema):
    data = json.loads((ROOT / "tests" / "golden" / fname).read_text(encoding="utf-8"))
    validator = Draft202012Validator(
        {"$ref": f"#/components/schemas/{schema}", "components": SPEC["components"]}
    )
    errors = [f"{list(e.absolute_path)}: {e.message[:150]}" for e in validator.iter_errors(data)]
    assert not errors, "\n".join(errors)
