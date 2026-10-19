"""Собирает синтетические .docx в tests/fixtures/generated/ (каталог в .gitignore).

Запуск: python scripts/build_fixtures.py [имя ...]   (без аргументов - все, кроме bad_zipbomb).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fixtures.builders.registry import BUILDERS, HEAVY_FIXTURES  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "generated"


def main(argv: list[str]) -> int:
    names = argv or [n for n in BUILDERS if n not in HEAVY_FIXTURES]
    unknown = [n for n in names if n not in BUILDERS]
    if unknown:
        print("неизвестные фикстуры:", ", ".join(unknown), file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = OUT / f"{name}.docx"
        path.write_bytes(BUILDERS[name]())
        print(f"{name}: {path.stat().st_size} байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
