"""ВСЕ пороги эвристик в одном месте (ARCHITECTURE_CHECKS.md §6).

Значения стартовые; `scripts/calibrate.py` печатает распределения на local_corpus/, по ним
правят числа. Логику проверок при калибровке не трогают.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    # форматирование (см)
    INDENT_EPS_CM: float = 0.01
    TBL_WIDTH_TOL_CM: float = 0.2
    MARGIN_TOL_CM: float = 0.05
    NUM_COL_MAX_CM: float = 1.5
    # таблицы
    CELL_NUMERIC_GRAY: tuple[float, float] = (0.3, 0.7)
    ROW_EXACT_MAX_PT: float = 28
    LONG_TABLE_ROWS: int = 15
    SHORT_TABLE_ROWS: int = 10
    SPILL_MAX_ROWS: int = 2
    TBL10_ROWS_EST: int = 25
    # объём и вёрстка
    VOL_MIN: float = 60
    VOL_MAX: float = 85
    PAGE_TOLERANCE: int = 2
    CHARS_PER_PAGE: int = 1800
    TABLE_ROW_PAGE_SHARE: float = 0.04  # доля страницы на строку таблицы (откат без вёрстки)
    IMAGE_PAGE_SHARE: float = 0.3  # доля страницы на рисунок (откат без вёрстки)
    LAYOUT_MIN_COVERAGE: float = 0.6  # ниже - вёрстка считается неудавшейся
    LAYOUT_OK_COVERAGE: float = 0.85  # ниже - status="partial"
    # структура
    STRUCT_LOW_CONFIDENCE: float = 0.5
    CH_CONCL_TAIL_PARAS: int = 40
    STR04_DUP_RATIO: float = 85
    TOC_MATCH_RATIO: float = 85
    HEADING_MAX_CHARS: int = 300
    HEURISTIC_HEADING_MAX_CHARS: int = 150
    ALIGN_WINDOW: int = 20000
    ALIGN_FUZZY_MIN: float = 85
    ALIGN_KEY_LEN: int = 40
    ALIGN_MIN_KEY: int = 8
    # смысловые сопоставления
    HYP_SIM_MIN: float = 0.7
    TSK_MATCH_MIN: float = 0.25
    TSK_COUNT_DIFF: int = 2
    INSTR_MATCH: float = 85
    MAT_THEORY_MIN: float = 0.15
    # ссылки и числа
    REF_FAR_PARAS: int = 15
    NEAR_PARAS: int = 3
    PCT_TOL: float = 0.5
    SD_RANGE_K: float = 3
    # сравнение версий
    SEC_RENAME_RATIO: float = 60
    SEC_CONTENT_RATIO: float = 70
    PARA_MODIFIED_RATIO: float = 50
    MOVE_RATIO: float = 0.9
    MOVE_MIN_CHARS: int = 40
    TBL_TITLE_RATIO: float = 80
    TBL_CONTENT_JACCARD: float = 0.6
    ANCHOR_CHANGED: float = 0.95
    # отчёт
    COLLAPSE_SHOW_LOCATIONS: int = 5
    NOISE_SUSPICION_BUDGET: int = 50


DEFAULT_THRESHOLDS = Thresholds()
