"""Печать распределений мер по local_corpus/*.docx для калибровки порогов (B-71).

Ничего не пишет в репозиторий: только stdout. Каталог по умолчанию local_corpus/ (в .gitignore).
Вёрстка LibreOffice не запускается: меры берутся из разбора и правил.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _describe(name: str, values: list[float]) -> str:
    if not values:
        return f"{name:<28} нет данных"
    qs = statistics.quantiles(values, n=4) if len(values) >= 2 else [values[0]] * 3
    return (
        f"{name:<28} n={len(values):<3} min={min(values):<9.1f} q1={qs[0]:<9.1f} "
        f"med={qs[1]:<9.1f} q3={qs[2]:<9.1f} max={max(values):.1f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corpus", nargs="?", default=str(ROOT / "local_corpus"))
    args = ap.parse_args()
    files = sorted(Path(args.corpus).glob("*.docx"))
    if not files:
        print(f"В {args.corpus} нет .docx - калибровать не на чем.", file=sys.stderr)
        return 1

    from vkr_checker.config import Settings
    from vkr_checker.layout.soffice import SofficeInfo
    from vkr_checker.pipeline import CheckPipeline
    from vkr_checker.web.upload import UploadedFile

    pipe = CheckPipeline(Settings(_env_file=None), SofficeInfo(None, None))
    measures: dict[str, list[float]] = {"абзацы": [], "таблицы": [], "оценка объёма, стр.": []}
    per_rule: dict[str, list[int]] = {}
    levels: Counter[str] = Counter()
    for path in files:
        try:
            an = pipe.analyze(UploadedFile("file", path.name, path.stat().st_size, path))
        except Exception as exc:  # noqa: BLE001 - скрипт-отчёт: продолжаем по остальным файлам
            print(f"{path.name}: пропущен ({type(exc).__name__}: {exc})", file=sys.stderr)
            continue
        report = an.report
        measures["абзацы"].append(len(an.doc.paragraphs))
        measures["таблицы"].append(len(an.doc.tables))
        if report.volume.pages_main is not None:
            measures["оценка объёма, стр."].append(report.volume.pages_main)
        counts: Counter[str] = Counter()
        for block in report.blocks:
            for rr in block.rule_results:
                for f in rr.findings:
                    if f.level in ("violation", "suspicion") and not f.not_run:
                        counts[f.rule_id] += f.count or 1
                        levels[f.level] += 1
        for rule in set(counts) | set(per_rule):
            per_rule.setdefault(rule, []).append(counts.get(rule, 0))

    print(f"Файлов: {len(files)}\n")
    for name, vals in measures.items():
        print(_describe(name, vals))
    print("\nНаходок на файл по правилам (нарушения и подозрения):")
    for rule in sorted(per_rule):
        print(_describe(rule, [float(v) for v in per_rule[rule]]))
    print(f"\nИтого находок: {dict(levels)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
