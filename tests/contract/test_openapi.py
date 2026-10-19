"""Pydantic-модели и app.openapi() совпадают с api/openapi.yaml (API_CONTRACT §7 п.1).

Без запуска сервера и HTTP: сравниваются схемы и сериализация golden-JSON моделями.
"""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from vkr_checker.config import Settings
from vkr_checker.layout.soffice import SofficeInfo
from vkr_checker.main import create_app
from vkr_checker.model import finding
from vkr_checker.report import schema

ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "api" / "openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]

# Эндпоинты, которых ещё нет в коде: убирать из списка по мере реализации.
PENDING_PATHS = {"/api/session": "B-04", "/api/export/matrix.xlsx": "B-51"}
# Схемы openapi, которые в Python выражены алиасами Literal, а не классами.
ALIAS_SCHEMAS = {"Level", "Outcome", "Method", "BlockId", "RuleId"}
# Вспомогательные классы для inline-объектов openapi (в yaml у них нет имени).
EXTRA_COMPONENTS = {
    "Limits", "ErrorBody", "FindingSource", "VolumeSection", "MatrixCells", "MatrixStats",
    "CompareOld", "Dynamics",
}  # fmt: skip
STATUS_FREE = {"404", "405"}


@pytest.fixture(scope="module")
def generated():
    app = create_app(Settings(_env_file=None), SofficeInfo(None, None))
    return app.openapi()


def _model(name: str):
    return getattr(schema, name, None) or getattr(finding, name, None)


def test_paths_methods_and_status_codes_match(generated):
    expected = {p: v for p, v in SPEC["paths"].items() if p not in PENDING_PATHS}
    assert set(generated["paths"]) == set(expected)
    for path, ops in expected.items():
        assert set(generated["paths"][path]) == set(ops), path
        for method, op in ops.items():
            got = set(generated["paths"][path][method]["responses"]) - STATUS_FREE - {"422"}
            want = set(op["responses"]) - {"422"}
            # 422 FastAPI добавляет сам; сверяем его отдельно там, где он есть в контракте
            assert got == want, f"{method.upper()} {path}"
            if "422" in op["responses"]:
                assert "422" in generated["paths"][path][method]["responses"]
            assert generated["paths"][path][method]["operationId"] == op["operationId"]


def test_request_bodies_are_multipart_with_required_fields(generated):
    for path in ("/api/check", "/api/compare"):
        want = SPEC["paths"][path]["post"]["requestBody"]["content"]["multipart/form-data"]
        got = generated["paths"][path]["post"]["requestBody"]["content"]["multipart/form-data"]
        assert got["schema"]["required"] == want["schema"]["required"]
        assert set(got["schema"]["properties"]) == set(want["schema"]["properties"])


def test_generated_components_are_known(generated):
    names = set(generated["components"]["schemas"])
    unknown = names - set(SCHEMAS) - EXTRA_COMPONENTS
    assert not unknown, f"схемы вне openapi.yaml: {sorted(unknown)}"


@pytest.mark.parametrize("name", sorted(set(SCHEMAS) - ALIAS_SCHEMAS))
def test_model_fields_match_schema(name):
    model = _model(name)
    assert model is not None, f"нет класса {name}"
    got = model.model_json_schema(mode="validation")
    if "$ref" in got:  # самоссылающиеся модели (StructureNode)
        got = got["$defs"][got["$ref"].rsplit("/", 1)[-1]]
    want = SCHEMAS[name]
    if "properties" not in want:
        pytest.skip("схема без свойств (enum/alias)")
    assert set(got["properties"]) == set(want["properties"]), name
    assert set(got.get("required", [])) == set(want.get("required", [])), name


def _strip_none(obj):
    """Необязательные поля в golden опущены, а модель выдаёт их как null или пустой список."""
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None and v != []}
    if isinstance(obj, list):
        return [_strip_none(v) for v in obj]
    return obj


GOLDEN = ["check_clean.json", "check_findings.json", "check_layout_failed.json", "compare.json"]


@pytest.mark.parametrize("fname", GOLDEN)
def test_models_roundtrip_golden_against_schema(fname):
    data = json.loads((ROOT / "tests" / "golden" / fname).read_text(encoding="utf-8"))
    model = schema.CompareReport if "diff" in data else schema.CheckReport
    dumped = json.loads(model.model_validate(data).model_dump_json())
    validator = Draft202012Validator(
        {"$ref": f"#/components/schemas/{model.__name__}", "components": SPEC["components"]}
    )
    errors = [f"{list(e.absolute_path)}: {e.message[:120]}" for e in validator.iter_errors(dumped)]
    assert not errors, "\n".join(errors)
    assert _strip_none(dumped) == _strip_none(data)
