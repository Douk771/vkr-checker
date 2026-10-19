# ruff: noqa: E501
"""E2E: устойчивость процесса при работе вёрстки. Каждый тест поднимает СВОЙ одноразовый контейнер
(уникальное имя, свободный порт на 127.0.0.1) и убирает его - общий стенд не затрагивается.

  VKR_E2E_IMAGE=vkr-checker:<tag> pytest tests/functional/test_h_crash_e2e.py
"""

import concurrent.futures as cf
import os
import shutil
import socket
import subprocess
import time
import uuid

import httpx
import pytest

from tests.functional.thesis import Thesis

IMAGE = os.environ.get("VKR_E2E_IMAGE")
pytestmark = pytest.mark.skipif(
    not (IMAGE and shutil.which("docker")), reason="нужны VKR_E2E_IMAGE и docker"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def box():
    name = f"qa-vkr-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    subprocess.run(
        ["docker", "run", "-d", "--name", name, "-p", f"127.0.0.1:{port}:8000", IMAGE],
        check=True,
        capture_output=True,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if httpx.get(url + "/api/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        yield name, url
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def alive(name: str) -> bool:
    out = subprocess.run(
        ["docker", "inspect", name, "--format", "{{.State.Status}}"], capture_output=True, text=True
    )
    return out.stdout.strip() == "running"


def test_single_check_with_layout_keeps_process_alive(box):
    name, url = box
    raw = Thesis(pages=70).bytes()
    r = httpx.post(url + "/api/check", files={"file": ("w.docx", raw, "x")}, timeout=120)
    assert r.status_code == 200 and r.json()["layout"]["status"] == "ok"
    assert alive(name)


def test_compare_with_layout_does_not_kill_the_server(box):
    name, url = box
    raw = Thesis(pages=20).bytes()
    try:
        r = httpx.post(
            url + "/api/compare",
            files={"old": ("o.docx", raw, "x"), "new": ("n.docx", raw, "x")},
            timeout=120,
        )
        status = r.status_code
    except httpx.HTTPError:
        status = None
    time.sleep(1)
    assert alive(name), "процесс сервиса завершился"
    assert status == 200


def test_two_parallel_checks_do_not_kill_the_server(box):
    name, url = box
    raw = Thesis(pages=70).bytes()

    def one(_):
        try:
            return httpx.post(
                url + "/api/check", files={"file": ("w.docx", raw, "x")}, timeout=120
            ).status_code
        except httpx.HTTPError:
            return None

    with cf.ThreadPoolExecutor(4) as ex:
        codes = list(ex.map(one, range(4)))
    time.sleep(1)
    assert alive(name), f"процесс сервиса завершился, ответы: {codes}"
    assert all(c in (200, 503) for c in codes), codes
