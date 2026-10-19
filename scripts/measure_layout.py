"""Замер времени вёрстки LibreOffice на синтетике 70 и 150 стр. (B-20, ARCHITECTURE.md §8.2).

Запуск (из корня репозитория, в окружении проекта):
    python scripts/measure_layout.py [--runs 3] [--soffice /path/to/soffice]

Печатает холодный старт (первый запуск) и медиану прогретых запусков. Если на 150 стр.
медиана > 20 с, нужен план Б (постоянный процесс unoserver).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.fixtures.builders.registry import BUILDERS  # noqa: E402

from vkr_checker.layout.soffice import LayoutError, SofficeRunner, probe_soffice  # noqa: E402


def measure(runner: SofficeRunner, name: str, runs: int) -> list[float]:
    times: list[float] = []
    with tempfile.TemporaryDirectory(prefix="vkr-measure-") as tmp:
        docx = Path(tmp) / f"{name}.docx"
        docx.write_bytes(BUILDERS[name]())
        for i in range(runs):
            work = Path(tmp) / f"run{i}"
            work.mkdir()
            started = time.perf_counter()
            runner.convert_to_pdf(docx, work)
            times.append(time.perf_counter() - started)
    return times


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--soffice", default=None)
    ap.add_argument("--timeout", type=int, default=120, help="таймаут замера, не боевой")
    args = ap.parse_args()
    info = probe_soffice(args.soffice)
    if not info.available:
        print("LibreOffice не найден: установите его или укажите --soffice", file=sys.stderr)
        return 2
    print(f"движок: {info.engine}")
    runner = SofficeRunner(info, timeout_s=args.timeout, concurrency=1)
    for name in ("clean_70p", "clean_150p"):
        try:
            t = measure(runner, name, args.runs)
        except LayoutError as exc:
            print(f"{name}: сбой вёрстки: {exc.reason}")
            continue
        warm = t[1:] or t
        print(
            f"{name}: холодный {t[0]:.1f} с; прогретый медиана {statistics.median(warm):.1f} с "
            f"(макс {max(t):.1f} с, запусков {len(t)})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
