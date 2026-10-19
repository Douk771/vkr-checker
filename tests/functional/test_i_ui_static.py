# ruff: noqa: E501
"""UI-01..03 и доступность на уровне отдаваемой статики. Браузерного e2e нет (Playwright не согласован):
поведение в браузере проверяется по frontend/tests/MANUAL_CHECKLIST.md, здесь - то, что видно из HTTP."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend"


def test_single_page_with_both_modes_button_and_progress(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    html = r.text
    assert 'lang="ru"' in html
    assert (
        'name="mode" value="check"' in html and 'name="mode" value="compare"' in html
    )  # UI-01: два режима
    assert (
        'id="file-file"' in html and 'id="file-old"' in html and 'id="file-new"' in html
    )  # 1 или 2 файла
    assert 'id="run-btn"' in html  # кнопка
    assert re.search(r'id="progress"[^>]*role="status"', html)  # индикатор
    assert 'id="run-error"' in html and 'role="alert"' in html  # ошибки текстом, не трассировкой
    assert 'id="download-btn"' in html  # UI-02: скачать отчёт


def test_every_input_has_a_label_and_is_keyboard_reachable(client):
    html = client.get("/").text
    for fid in re.findall(r'<input[^>]*\bid="([^"]+)"', html):
        if 'type="radio"' in re.search(rf'<input[^>]*id="{fid}"[^>]*>', html).group(0):
            continue
        assert f'for="{fid}"' in html, fid
    assert 'tabindex="-1"' not in html  # ничего не убрано из клавиатурной навигации


def test_static_pages_load_no_external_resources(client):
    """SPEC §5: офлайн. Ни одной ссылки на внешние ресурсы в HTML/JS/CSS фронтенда."""
    for p in (
        list(ROOT.glob("*.html"))
        + list(ROOT.glob("*.css"))
        + list(ROOT.glob("*.js"))
        + list(ROOT.glob("js/*.js"))
    ):
        text = p.read_text(encoding="utf-8")
        ext = re.findall(
            r"""(?:src|href)=["'](https?://[^"']+)["']|url\((https?://[^)]+)\)|fetch\(["'](https?://[^"']+)""",
            text,
        )
        assert not ext, (p.name, ext)


def test_report_assets_are_served(client):
    for path in ("/app.js", "/styles.css", "/viewer.js", "/viewer.css"):
        assert client.get(path).status_code == 200, path
    assert client.get("/api/health").json()["status"] == "ok"
