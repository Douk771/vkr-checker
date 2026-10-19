"""Замер времени конвейера (B-72): check и compare на синтетике; --profile печатает топ cProfile.

Без LibreOffice (вёрстка отключена): замеряется разбор + проверки + diff. Время вёрстки
замеряет scripts/measure_layout.py. Ничего не пишет в репозиторий.
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

CHECK_BUDGET_S = 30.0
COMPARE_BUDGET_S = 60.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", type=int, default=150)
    ap.add_argument("--profile", action="store_true", help="напечатать топ-25 по cumtime")
    args = ap.parse_args()

    from tests.fixtures.builders import variants

    from vkr_checker.config import Settings
    from vkr_checker.layout.soffice import SofficeInfo
    from vkr_checker.pipeline import CheckPipeline
    from vkr_checker.web.upload import UploadedFile

    pipe = CheckPipeline(Settings(_env_file=None), SofficeInfo(None, None))
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for seed in (1, 2):
            p = Path(tmp) / f"v{seed}.docx"
            p.write_bytes(variants.clean(args.pages, seed=seed).to_bytes())
            files.append(UploadedFile("file", p.name, p.stat().st_size, p))

        prof = cProfile.Profile() if args.profile else None
        t0 = time.monotonic()
        if prof:
            prof.enable()
        pipe.check(files[0])
        t_check = time.monotonic() - t0
        t0 = time.monotonic()
        pipe.compare(files[0], files[1])
        t_cmp = time.monotonic() - t0
        if prof:
            prof.disable()
            pstats.Stats(prof).sort_stats("cumtime").print_stats(25)

    print(
        f"check   {args.pages} стр.: {t_check:6.2f} с (бюджет {CHECK_BUDGET_S:.0f} с, с вёрсткой +~1 с)"
    )
    print(f"compare {args.pages} стр.: {t_cmp:6.2f} с (бюджет {COMPARE_BUDGET_S:.0f} с)")
    return 0 if t_check <= CHECK_BUDGET_S and t_cmp <= COMPARE_BUDGET_S else 1


if __name__ == "__main__":
    raise SystemExit(main())
