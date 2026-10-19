"""Словарь статистических методов (SPEC MET-01): названия и обозначения статистик.

id -> MethodDef. names - регэкспы названий без учёта регистра (падежные формы покрыты основой).
stats - регэкспы обозначений статистик в тексте и таблицах (с учётом регистра).
Словарь дополняется на корпусе; новые методы добавляются сюда, логика не меняется.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DASH = r"[-–—\s]*"
SQ = r"[2²]"


@dataclass(frozen=True)
class MethodDef:
    id: str
    title: str
    names: tuple[re.Pattern[str], ...]
    stats: tuple[re.Pattern[str], ...] = ()


def _n(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


def _s(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in patterns)


METHODS: dict[str, MethodDef] = {
    m.id: m
    for m in (
        MethodDef(
            "mann_whitney",
            "U Манна-Уитни",
            _n(rf"манн\w*{DASH}уитн\w*", r"u-критери\w*"),
            _s(r"(?<![A-Za-z])U\s*=\s*\d"),
        ),  # fmt: skip
        MethodDef(
            "kruskal_wallis",
            "H Краскела-Уоллиса",
            _n(rf"краскел\w*{DASH}уол+ис\w*", r"h-критери\w*"),
            _s(r"(?<![A-Za-z])H\s*(?:\(\d+\))?\s*=\s*\d"),
        ),  # fmt: skip
        MethodDef(
            "wilcoxon", "T Вилкоксона", _n(r"вилкоксон\w*"), _s(r"(?<![A-Za-z])T\s*=\s*\d")
        ),  # fmt: skip
        MethodDef(
            "student_t",
            "t Стьюдента",
            _n(r"стьюдент\w*", r"t-критери\w*"),
            _s(r"(?<![A-Za-z])t\s*(?:\(\d+\))?\s*=\s*[-−–]?\d"),
        ),  # fmt: skip
        MethodDef(
            "chi_square",
            "χ²",
            _n(rf"хи{DASH}квадрат\w*", r"критери\w*\s+хи"),
            _s(rf"χ\s*{SQ}", r"(?<![A-Za-z])chi"),
        ),  # fmt: skip
        MethodDef(
            "pearson",
            "r Пирсона",
            _n(r"пирсон\w*"),
            _s(r"(?<![A-Za-z])r\s*(?:\(\d+\))?\s*=\s*[-−–]?\d"),
        ),  # fmt: skip
        MethodDef(
            "spearman",
            "rs Спирмена",
            _n(r"спирмен\w*"),
            _s(r"(?<![A-Za-z])r\s?s\s*=\s*[-−–]?\d", r"ρ\s*=\s*[-−–]?\d"),
        ),  # fmt: skip
        MethodDef("kendall", "τ Кендалла", _n(r"кендал+\w*"), _s(r"τ\s*=\s*[-−–]?\d")),
        MethodDef(
            "anova",
            "ANOVA / F",
            _n(r"дисперсионн\w+\s+анализ\w*", r"\banova\b"),
            _s(r"(?<![A-Za-z])F\s*\(\s*\d+\s*[,;]\s*\d+\s*\)\s*="),
        ),  # fmt: skip
        MethodDef(
            "regression", "регрессия", _n(r"регресс\w+"), _s(rf"(?<![A-Za-z])R{SQ}\s*=", r"β\s*=")
        ),  # fmt: skip
        MethodDef("eta_squared", "η²", _n(rf"эта{DASH}квадрат\w*"), _s(rf"η\s*{SQ}")),  # fmt: skip
        MethodDef(
            "cohen_d",
            "d Коэна",
            _n(rf"d{DASH}коэн\w*", r"коэн\w*"),
            _s(r"(?<![A-Za-z])d\s*=\s*[-−–]?\d"),
        ),  # fmt: skip
        MethodDef("cronbach", "α Кронбаха", _n(r"кронбах\w*"), _s(r"α\s*=\s*\d")),
        MethodDef("factor", "факторный анализ", _n(r"факторн\w+\s+анализ\w*")),
        MethodDef("cluster", "кластерный анализ", _n(r"кластерн\w+\s+анализ\w*")),
    )
}
