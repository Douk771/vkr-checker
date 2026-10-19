# ruff: noqa: E501
"""Фикстуры функциональных тестов: приложение в local-режиме без LibreOffice, помощники отчёта.

Окружение изолированное: TestClient поверх create_app(Settings(_env_file=None)), своя
временная папка, сети нет, ключей внешних сервисов нет.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from tests.functional.thesis import Thesis
from vkr_checker.config import Settings
from vkr_checker.layout.soffice import SofficeInfo
from vkr_checker.main import create_app

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def make_client(**env) -> TestClient:
    settings = Settings(_env_file=None, **env)
    return TestClient(create_app(settings, SofficeInfo(None, None)))


@pytest.fixture(scope="session")
def client():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return make_client()


class Api:
    def __init__(self, client: TestClient):
        self.c = client

    def check(self, data: bytes | Thesis, name: str = "work.docx"):
        raw = data.bytes() if isinstance(data, Thesis) else data
        return self.c.post("/api/check", files={"file": (name, raw, DOCX)})

    def report(self, thesis: Thesis | bytes, name: str = "work.docx") -> dict:
        r = self.check(thesis, name)
        assert r.status_code == 200, r.text[:500]
        return r.json()

    def compare(self, old: Thesis | bytes, new: Thesis | bytes):
        o = old.bytes() if isinstance(old, Thesis) else old
        n = new.bytes() if isinstance(new, Thesis) else new
        return self.c.post(
            "/api/compare", files={"old": ("old.docx", o, DOCX), "new": ("new.docx", n, DOCX)}
        )

    def diff(self, old: Thesis, new: Thesis) -> dict:
        r = self.compare(old, new)
        assert r.status_code == 200, r.text[:500]
        return r.json()


@pytest.fixture(scope="session")
def api(client):
    return Api(client)


def all_findings(report: dict, include_nc: bool = False) -> list[dict]:
    out = []
    for b in report["blocks"]:
        for rr in b["rule_results"]:
            for f in rr["findings"]:
                if include_nc or f["level"] != "not_checked":
                    out.append(f)
    return out


def of_rule(report: dict, rule: str) -> list[dict]:
    return [f for f in all_findings(report, True) if f["rule_id"] == rule]


def rule_result(report: dict, rule: str) -> dict | None:
    for b in report["blocks"]:
        for rr in b["rule_results"]:
            if rr["rule_id"] == rule:
                return rr
    return None


def levels(report: dict, rule: str) -> set[str]:
    return {f["level"] for f in of_rule(report, rule) if not f["not_run"]}


@pytest.fixture(scope="session")
def clean() -> Thesis:
    return Thesis()


@pytest.fixture(scope="session")
def clean_report(api, clean) -> dict:
    return api.report(clean)
