# ruff: noqa: E501
"""E2E против реального контейнера с LibreOffice (SPEC §0 п.1: пагинация по факту вёрстки).

Запуск (контейнеры поднимает QA на отдельных портах, не на общем стенде):
  docker run -d --name qa-vkr -p 127.0.0.1:18765:8000 vkr-checker:<tag>
  docker run -d --name qa-vkr-to -p 127.0.0.1:18766:8000 -e VKR_LAYOUT_TIMEOUT_S=1 vkr-checker:<tag>
  VKR_E2E_URL=http://127.0.0.1:18765 VKR_E2E_URL_TIMEOUT=http://127.0.0.1:18766 pytest tests/functional/test_f_layout_e2e.py
Без VKR_E2E_URL тесты пропускаются (в unit/CI-окружении без LibreOffice их нет смысла гонять).
"""

import os
import time

import httpx
import pytest

from tests.functional.thesis import NB, Thesis, p, table

URL = os.environ.get("VKR_E2E_URL")
URL_TO = os.environ.get("VKR_E2E_URL_TIMEOUT")
pytestmark = pytest.mark.skipif(not URL, reason="нужен VKR_E2E_URL (контейнер с LibreOffice)")


def post(url, t: Thesis, timeout=200):
    r = httpx.post(
        url + "/api/check",
        files={"file": ("w.docx", t.bytes(), "application/octet-stream")},
        timeout=timeout,
    )
    assert r.status_code == 200, r.text[:300]
    return r.json()


def finds(rep, rule):
    return [
        f
        for b in rep["blocks"]
        for rr in b["rule_results"]
        for f in rr["findings"]
        if f["rule_id"] == rule
    ]


def test_health_reports_layout_available():
    h = httpx.get(URL + "/api/health").json()
    assert h["layout_available"] and "LibreOffice" in (h["layout_engine"] or "")


def test_layout_ok_and_disclaimer_present():
    rep = post(URL, Thesis(pages=70))
    lay = rep["layout"]
    assert lay["status"] == "ok" and lay["page_count"] and lay["coverage"] == 1.0
    assert (
        "LibreOffice" in lay["disclaimer"] and "±" in lay["disclaimer"]
    )  # оговорка про расхождение с Word
    assert rep["volume"]["method"] == "layout"


def test_volume_by_layout_in_range_has_no_finding():
    rep = post(URL, Thesis(pages=70))
    assert 60 <= rep["volume"]["pages_main"] <= 85
    assert not finds(rep, "VOL-01")
    assert {s["title"] for s in rep["volume"]["by_section"]} >= {"ВВЕДЕНИЕ"}


@pytest.mark.parametrize("pages", [20, 150])
def test_volume_by_layout_out_of_range_is_suspicion(pages):
    rep = post(URL, Thesis(pages=pages))
    fs = finds(rep, "VOL-01")
    assert fs and {f["level"] for f in fs} == {"suspicion"}
    assert rep["volume"]["method"] == "layout"


def _true_pages(t: Thesis) -> dict[str, int]:
    """Независимая от продукта пагинация: тот же LibreOffice в контейнере + поиск заголовков в PDF."""
    import pathlib
    import subprocess
    import tempfile

    import pypdfium2 as pdfium

    name = os.environ.get("VKR_E2E_CONTAINER", "qa-cycle001-vkr")
    with tempfile.TemporaryDirectory() as d:
        src = pathlib.Path(d) / "w.docx"
        src.write_bytes(t.bytes())
        run = lambda *a, **k: subprocess.run(a, capture_output=True, timeout=120, check=True, **k)  # noqa: E731
        run("docker", "exec", name, "mkdir", "-p", "/tmp/qa")
        run(
            "docker", "exec", "-i", name, "sh", "-c", "cat > /tmp/qa/w.docx", input=src.read_bytes()
        )
        run(
            "docker",
            "exec",
            name,
            "soffice",
            "--headless",
            "-env:UserInstallation=file:///tmp/qa/prof",
            "--convert-to",
            "pdf",
            "--outdir",
            "/tmp/qa",
            "/tmp/qa/w.docx",
        )
        (pathlib.Path(d) / "w.pdf").write_bytes(
            run("docker", "exec", name, "cat", "/tmp/qa/w.pdf").stdout
        )
        run("docker", "exec", name, "rm", "-rf", "/tmp/qa")
        pdf = pdfium.PdfDocument(str(pathlib.Path(d) / "w.pdf"))
        texts = [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
    pages = {}
    for b in t.blocks:
        if b.get("tag") == "toc":
            title = b["t"].split(" ........")[0]
            hits = [
                i + 1
                for i, tx in enumerate(texts)
                if title in tx.replace("\r", "").replace("\n", " ")
            ]
            hits = [h for h in hits if h > 2]  # пропускаем страницу самого оглавления
            if hits:
                pages[title] = hits[0]
    return pages


def _toc_with_true_pages(t: Thesis) -> Thesis:
    pages = _true_pages(t)
    out = t.copy()
    for b in out.blocks:
        if b.get("tag") == "toc":
            title = b["t"].split(" ........")[0]
            if title in pages:
                b["t"] = f"{title} ........ {pages[title]}"
    return out


def test_str06_wrong_toc_page_numbers_are_suspicion_with_page_in_location():
    rep = post(URL, Thesis(pages=70))
    fs = finds(rep, "STR-06")
    assert fs and {f["level"] for f in fs} == {"suspicion"}
    assert all(f["locations"][0]["page"] for f in fs)


def test_str06_correct_toc_page_numbers_pass():
    t = _toc_with_true_pages(Thesis(pages=70))
    rep = post(URL, t)
    bad = [f["message"] for f in finds(rep, "STR-06")]
    assert not bad, bad


def test_clean_work_with_layout_has_no_violations_or_suspicions_after_toc_fixed():
    t = _toc_with_true_pages(Thesis(pages=70))
    rep = post(URL, t)
    left = [
        (f["rule_id"], f["message"][:90])
        for b in rep["blocks"]
        for rr in b["rule_results"]
        for f in rr["findings"]
        if f["level"] != "not_checked"
    ]
    assert not left, left


def test_tbl10_long_table_by_layout_is_suspicion():
    rows = [["Показатель", "Группа 1", "Группа 2"]] + [
        [f"Параметр номер {i}", f"{i},1", f"{i},2"] for i in range(1, 60)
    ]
    t = (
        Thesis(pages=70)
        .insert_after("Гипотеза о том, что учебная", table("Таблица 3 – Длинная таблица", rows))
        .sub("1 рисунок и 2 таблицы", "1 рисунок и 3 таблицы")
        .insert_after("Гипотеза о том, что учебная", p("См. табл. 3 и приложение А."))
    )
    rep = post(URL, t)
    fs = finds(rep, "TBL-10")
    assert fs and fs[0]["level"] in ("violation", "suspicion")


def test_tbl12_short_table_split_across_pages_is_reported():
    """Подбираем число коротких абзацев так, чтобы 4-строчная таблица легла на границу страниц."""
    hit = None
    for k in range(0, 28):
        pad = [p(f"Короткая строка {chr(1040 + k % 30)}.", False) for _ in range(k)]
        t = Thesis(pages=40).insert_before("Таблица 2 – Сравнение групп", *pad)
        rep = post(URL, t)
        fs = finds(rep, "TBL-12")
        if any(f["level"] != "not_checked" for f in fs):
            hit = fs
            break
    assert hit, "за 28 попыток таблица ни разу не легла на границу страниц или TBL-12 её не заметил"


def test_layout_timeout_falls_back_to_text_estimate():
    if not URL_TO:
        pytest.skip("нужен VKR_E2E_URL_TIMEOUT")
    rep = post(URL_TO, Thesis(pages=500))  # заведомо дольше 1 с вёрстки
    assert rep["layout"]["status"] == "failed" and rep["layout"]["reason"]
    assert rep["volume"]["method"] == "estimate" and rep["volume"]["estimate_formula"]
    st = {rr["rule_id"]: rr["outcome"] for b in rep["blocks"] for rr in b["rule_results"]}
    assert st.get("STR-06") == "not_checked" and st.get("TBL-12") == "not_checked"
    assert not any(loc.get("page") for f in finds(rep, "VOL-01") for loc in f["locations"])


def test_performance_150_pages_check_under_30s():
    t0 = time.time()
    post(URL, Thesis(pages=150))
    assert time.time() - t0 <= 30


def test_no_uploaded_files_remain_in_container_tmp():
    import shutil
    import subprocess

    if not shutil.which("docker"):
        pytest.skip("нет docker CLI")
    name = os.environ.get("VKR_E2E_CONTAINER", "qa-cycle001-vkr")
    post(URL, Thesis(pages=20))
    httpx.post(URL + "/api/check", files={"file": ("bad.docx", b"%PDF-1.7 x", "x")})
    out = subprocess.run(
        [
            "docker",
            "exec",
            name,
            "sh",
            "-c",
            "find /tmp -type f | grep -v -E '^/tmp/(app|uv-[0-9a-f]+[.]lock$)' | head -20",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.stdout.strip() == "", out.stdout


def test_performance_150_pages_compare_under_60s():
    old = Thesis(pages=150)
    new = old.sub(
        "Объект исследования: учебная мотивация", "Объект исследования: адаптационная мотивация"
    )
    t0 = time.time()
    r = httpx.post(
        URL + "/api/compare",
        files={"old": ("o.docx", old.bytes(), "x"), "new": ("n.docx", new.bytes(), "x")},
        timeout=200,
    )
    assert r.status_code == 200 and time.time() - t0 <= 60


def test_compare_with_layout_adds_pages_to_locations():
    old = Thesis(pages=70)
    new = old.sub(f"n{NB}={NB}120", f"n{NB}={NB}118", within="ВВЕДЕНИЕ")
    r = httpx.post(
        URL + "/api/compare",
        files={"old": ("o.docx", old.bytes(), "x"), "new": ("n.docx", new.bytes(), "x")},
        timeout=200,
    )
    d = r.json()
    assert d["new"]["layout"]["status"] == "ok" and d["old"]["layout"]["status"] == "ok"
    assert any(c["loc_new"] and c["loc_new"].get("page") for c in d["diff"]["number_changes"])
