"""Общие фикстуры pytest: ленивая генерация синтетических .docx с кэшем по хэшу генераторов."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

BUILDERS_DIR = Path(__file__).parent / "fixtures" / "builders"
GENERATED = Path(__file__).parent / "fixtures" / "generated"


def _builders_hash() -> str:
    h = hashlib.sha256()
    for f in sorted(BUILDERS_DIR.glob("*.py")):
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


@pytest.fixture(scope="session")
def fixture_path():
    """fixture_path("clean_70p") -> Path к .docx; пересборка при смене генераторов."""
    from tests.fixtures.builders.registry import BUILDERS

    tag = _builders_hash()

    def get(name: str) -> Path:
        path = GENERATED / tag / f"{name}.docx"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(BUILDERS[name]())
        return path

    return get
