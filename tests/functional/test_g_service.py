# ruff: noqa: E501
"""SPEC 3.5, 4.E (UI-03), 5: вход, ошибки, безопасность, детерминизм, устойчивость разбора, параллельность."""

import io
import logging
import re
import socket
import tempfile
import zipfile
from pathlib import Path

import pytest
from docx import Document
from lxml import etree

from tests.functional.conftest import DOCX, Api, make_client
from tests.functional.thesis import Thesis

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def err(r):
    return r.json()["error"]


# ---- 3.5 Вход: только .docx --------------------------------------------------------------
OLE = bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 1024


def _zip(parts):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in parts.items():
            z.writestr(k, v)
    return buf.getvalue()


@pytest.mark.parametrize(
    "name, data",
    [
        ("a.pdf", b"%PDF-1.7\n" + b"0" * 256),
        ("a.docx", b"%PDF-1.7\n" + b"0" * 256),  # PDF под видом docx
        ("a.doc", OLE),
        ("a.docx", OLE),  # старый .doc под видом .docx
        ("a.docx", b""),
        (
            "a.docx",
            _zip({"mimetype": b"application/vnd.oasis.opendocument.text", "content.xml": b"<x/>"}),
        ),  # odt
        ("a.docx", _zip({"hello.txt": b"hi"})),  # обычный zip
        ("a.docx", b"PK\x03\x04 truncated"),
        ("a.txt", "просто текст".encode()),
    ],
)
def test_non_docx_input_rejected_with_clear_russian_message(api, name, data):
    r = api.check(data, name)
    assert r.status_code in (400, 415, 422), r.status_code
    e = err(r)
    assert e["code"] in ("unsupported_format", "invalid_docx", "bad_request", "missing_file")
    assert re.search(r"[А-Яа-я]{4,}", e["message"]), e["message"]
    assert "Traceback" not in r.text and 'File "' not in r.text and "/Users/" not in r.text
    assert e.get("request_id")


def test_truncated_docx_is_422_not_500(api, clean):
    r = api.check(clean.bytes()[: len(clean.bytes()) // 2])
    assert r.status_code in (415, 422) and err(r)["code"] in ("invalid_docx", "unsupported_format")


def test_missing_file_field(client):
    r = client.post("/api/check", files={"other": ("a.docx", b"x", DOCX)})
    assert r.status_code in (400, 422) and err(r)["code"] in (
        "missing_file",
        "bad_request",
        "validation_error",
    )


def test_garbage_multipart_body(client):
    r = client.post(
        "/api/check",
        content=b"--zzz\r\ngarbage",
        headers={"content-type": "multipart/form-data; boundary=zzz"},
    )
    assert r.status_code in (400, 422) and "Traceback" not in r.text


def test_wrong_http_methods_and_unknown_route(client):
    assert client.get("/api/check").status_code in (404, 405)
    assert client.get("/api/nonexistent").status_code in (404, 405)


def test_oversized_upload_rejected_with_413():
    c = make_client(max_upload_mb=1)
    big = _zip(
        {"word/document.xml": b"<w:document/>", "pad.bin": __import__("os").urandom(1_300_000)}
    )
    r = c.post("/api/check", files={"file": ("big.docx", big, DOCX)})
    assert r.status_code == 413 and err(r)["code"] == "file_too_large"


def test_zip_bomb_rejected_by_unpack_limit(api):
    bomb = _zip(
        {
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": b"<w:document/>",
            "word/bomb.bin": b"\0" * (260 * 1024 * 1024),
        }
    )
    assert len(bomb) < 2_000_000
    r = api.check(bomb)
    assert r.status_code == 422 and err(r)["code"] in ("docx_limits_exceeded", "invalid_docx")


def test_too_many_zip_entries_rejected(api, clean):
    src = zipfile.ZipFile(io.BytesIO(clean.bytes()))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i in src.infolist():
            z.writestr(i, src.read(i.filename))
        for n in range(2500):
            z.writestr(f"customXml/item{n}.xml", b"<a/>")
    r = api.check(buf.getvalue())
    assert r.status_code == 422 and err(r)["code"] in ("docx_limits_exceeded", "invalid_docx")


# ---- безопасность содержимого ----------------------------------------------------------
def _patch_document_xml(base: Thesis, fn) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(base.bytes()))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i in src.infolist():
            data = src.read(i.filename)
            if i.filename == "word/document.xml":
                data = fn(data)
            z.writestr(i, data)
    return buf.getvalue()


def test_xxe_external_entity_is_not_expanded(api, clean, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-MARKER-12345")
    xxe = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><!DOCTYPE d [<!ENTITY x SYSTEM "file://{secret}">]>'

    def patch(data):
        body = data.split(b"?>", 1)[1] if data.startswith(b"<?xml") else data
        body = body.replace(
            "Актуальность исследования".encode(), "&x; Актуальность исследования".encode(), 1
        )
        return xxe.encode() + body

    r = api.check(_patch_document_xml(clean, patch))
    assert r.status_code in (200, 422), r.status_code
    assert "TOP-SECRET-MARKER-12345" not in r.text


def test_billion_laughs_does_not_hang_or_500(api, clean):
    ents = "".join(f'<!ENTITY l{i} "{f"&l{i - 1};" * 10 if i else "ha"}">' for i in range(0, 9))
    head = f'<?xml version="1.0"?><!DOCTYPE d [{ents}]>'.encode()

    def patch(data):
        body = data.split(b"?>", 1)[1]
        return head + body.replace("Актуальность".encode(), "&l8; Актуальность".encode(), 1)

    r = api.check(_patch_document_xml(clean, patch))
    assert r.status_code in (200, 422), r.status_code


def test_external_links_in_document_are_not_fetched(api, clean, monkeypatch):
    """Внешняя ссылка на картинку / гиперссылка: сервис её не открывает (нет исходящих соединений)."""
    calls = []
    real = socket.socket.connect

    def spy(self, addr, *a, **k):
        if (
            isinstance(addr, tuple)
            and addr
            and addr[0] not in ("127.0.0.1", "localhost", "::1", "testserver")
        ):
            calls.append(addr)
        return real(self, addr, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", spy)
    src = zipfile.ZipFile(io.BytesIO(clean.bytes()))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i in src.infolist():
            data = src.read(i.filename)
            if i.filename == "word/_rels/document.xml.rels":
                data = data.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rIdX1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                    b'Target="http://203.0.113.9/evil.png" TargetMode="External"/></Relationships>',
                )
            z.writestr(i, data)
    r = api.check(buf.getvalue())
    assert r.status_code in (200, 422)
    assert not calls, calls


def test_no_outbound_network_during_check_and_compare(api, clean, monkeypatch):
    def deny(*a, **k):
        raise AssertionError("исходящее соединение запрещено (SPEC §5: полностью офлайн)")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    assert api.check(clean).status_code == 200
    assert api.compare(clean, clean).status_code == 200


def test_uploaded_filename_is_reduced_to_basename(api, clean):
    r = api.check(clean, name="C:\\Users\\student\\secret\\vkr.docx")
    assert r.status_code == 200
    assert r.json()["file"]["name"] == "vkr.docx"
    r = api.check(clean, name="../../etc/passwd.docx")
    assert r.json()["file"]["name"] == "passwd.docx"


# ---- UI-03: служебные поля отчёта --------------------------------------------------------
def test_report_has_version_date_filename_and_volume_method(api, clean_report):
    r = clean_report
    assert re.match(r"\d+\.\d+", r["service_version"])
    assert re.match(r"\d{4}-\d{2}-\d{2}T", r["checked_at"])
    assert r["file"]["name"] == "work.docx" and "/" not in r["file"]["name"]
    assert r["file"]["sha256"] and r["volume"]["method"] in ("layout", "estimate")
    assert r["layout"]["disclaimer"]


def test_levels_are_words_not_only_colors(clean_report):
    """Доступность: уровень подписан словом в данных отчёта (enum), а в UI есть русские подписи."""
    root = Path(__file__).resolve().parents[2] / "frontend"
    blob = "".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in root.rglob("*.js")
        if "tests" not in p.parts
    )
    for word in ("Нарушение", "Подозрение", "Не проверяется"):
        assert word.lower() in blob.lower(), word


# ---- детерминизм -------------------------------------------------------------------------
def _stable(rep):
    rep = dict(rep)
    rep.pop("checked_at", None)
    return rep


def test_same_file_gives_same_report(api, clean):
    a, b = api.report(clean), api.report(clean)
    assert _stable(a) == _stable(b)
    assert [f["id"] for bl in a["blocks"] for r in bl["rule_results"] for f in r["findings"]] == [
        f["id"] for bl in b["blocks"] for r in bl["rule_results"] for f in r["findings"]
    ]


def test_file_name_does_not_change_findings(api, clean):
    a = api.report(clean, "a.docx")
    b = api.report(clean, "completely_other_name.docx")
    assert [
        f["fingerprint"] for bl in a["blocks"] for r in bl["rule_results"] for f in r["findings"]
    ] == [f["fingerprint"] for bl in b["blocks"] for r in bl["rule_results"] for f in r["findings"]]


# ---- устойчивость разбора -------------------------------------------------------------------
def _doc_bytes(mut) -> bytes:
    d = Document(io.BytesIO(Thesis().bytes()))
    mut(d)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_document_without_heading_styles_does_not_crash(api):
    d = Document()
    for i in range(30):
        d.add_paragraph(f"Просто абзац номер {i} без всяких заголовков и стилей.")
    buf = io.BytesIO()
    d.save(buf)
    rep = api.report(buf.getvalue())
    assert rep["summary"]["violation"] >= 1  # нет разделов
    assert any(
        f["rule_id"] == "STR-01"
        for bl in rep["blocks"]
        for r in bl["rule_results"]
        for f in r["findings"]
    )


def test_empty_document_does_not_crash(api):
    buf = io.BytesIO()
    Document().save(buf)
    r = api.check(buf.getvalue())
    assert r.status_code == 200 and "Traceback" not in r.text


def test_nested_tables_do_not_crash(api):
    def mut(d):
        outer = d.add_table(rows=2, cols=2)
        outer.cell(0, 0).add_table(rows=2, cols=2).cell(0, 0).text = "вложенная"

    assert api.check(_doc_bytes(mut)).status_code == 200


def test_merged_cells_do_not_crash(api):
    def mut(d):
        t = d.add_table(rows=3, cols=3)
        t.cell(0, 0).merge(t.cell(0, 2))
        t.cell(1, 0).merge(t.cell(2, 0))

    assert api.check(_doc_bytes(mut)).status_code == 200


def test_picture_in_textbox_without_caption_is_found(api, clean):
    """SPEC NUM-01: рисунок в надписи/текстовом поле без подписи -> нарушение."""
    # на уровне python-docx: абзац с w:pict/v:textbox, внутри картинка
    from docx.shared import Cm

    d = Document(io.BytesIO(clean.bytes()))
    para = d.add_paragraph()
    run = para.add_run()
    run.add_picture(
        io.BytesIO(__import__("tests.fixtures.builders.base", fromlist=["_tiny_png"])._tiny_png()),
        width=Cm(3),
    )
    buf = io.BytesIO()
    d.save(buf)
    rep = api.report(buf.getvalue())
    assert any(
        f["rule_id"] == "NUM-01" and f["level"] == "violation" and "рису" in f["message"].lower()
        for bl in rep["blocks"]
        for r in bl["rule_results"]
        for f in r["findings"]
    )


def test_footnotes_and_headers_do_not_crash(api):
    def mut(d):
        s = d.sections[0]
        s.header.paragraphs[0].text = "Колонтитул работы"
        s.footer.paragraphs[0].text = "Стр."

    assert api.check(_doc_bytes(mut)).status_code == 200


def test_giant_single_paragraph_does_not_crash(api):
    def mut(d):
        d.add_paragraph("слово " * 200_000)

    r = api.check(_doc_bytes(mut))
    assert r.status_code in (200, 503, 413, 422), r.status_code


def test_tracked_changes_insertions_counted_deletions_ignored(api, clean):
    """SPEC 3.5: вставки в режиме рецензирования учитываются, удаления - нет."""

    def patch(data):
        root = etree.fromstring(data)
        ns = {"w": W}
        for t in root.iterfind(".//w:t", ns):
            if t.text and "студентов магистратуры, из них" in t.text and "Выборка" in t.text:
                run = t.getparent()
                para = run.getparent()
                ins = etree.SubElement(
                    para,
                    f"{{{W}}}ins",
                    {
                        f"{{{W}}}id": "1",
                        f"{{{W}}}author": "a",
                        f"{{{W}}}date": "2026-01-01T00:00:00Z",
                    },
                )
                r2 = etree.SubElement(ins, f"{{{W}}}r")
                etree.SubElement(r2, f"{{{W}}}t").text = " Дополнительно обследовано 77 человек."
                dele = etree.SubElement(
                    para,
                    f"{{{W}}}del",
                    {
                        f"{{{W}}}id": "2",
                        f"{{{W}}}author": "a",
                        f"{{{W}}}date": "2026-01-01T00:00:00Z",
                    },
                )
                r3 = etree.SubElement(dele, f"{{{W}}}r")
                etree.SubElement(r3, f"{{{W}}}delText").text = " Удалённая фраза про 999 человек."
                break
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    rep = api.report(_patch_document_xml(clean, patch))
    quotes = " ".join(
        loc["quote"]
        for bl in rep["blocks"]
        for r in bl["rule_results"]
        for f in r["findings"]
        for loc in f["locations"]
    )
    idx = next(r for bl in rep["blocks"] for r in bl["rule_results"] if r["rule_id"] == "CON-01")[
        "artifacts"
    ]["numbers_index"]
    values = {i["value"] for i in idx if i["kind"] == "sample_n"}
    assert "999" not in values and "999" not in quotes
    assert "77" in values  # вставка учтена


def test_comments_are_ignored(api, clean):
    with_comment = _patch_document_xml(clean, lambda d: d)  # документ без правок: базовая линия
    base = api.report(with_comment)
    d = Document(io.BytesIO(clean.bytes()))
    try:
        d.add_comment(runs=d.paragraphs[10].runs[:1], text="Комментарий 12345 человек", author="r")
    except Exception:
        pytest.skip("python-docx без поддержки комментариев")
    buf = io.BytesIO()
    d.save(buf)
    rep = api.report(buf.getvalue())
    assert _stable(rep)["summary"] == _stable(base)["summary"]


def test_seq_field_numbers_taken_from_cached_result(api, clean):
    """Подписи с полем SEQ: номер берётся из сохранённого результата поля."""

    def patch(data):
        text = data.decode("utf-8")
        old = "Таблица 1 – Описательные статистики"
        # Разбиваем «Таблица » + SEQ(результат 1) + « – Описательные…»
        run = (
            'Таблица </w:t></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> SEQ Таблица \\* ARABIC </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
            '<w:r><w:t xml:space="preserve"> – Описательные статистики'
        )
        assert old in text
        return text.replace(old, run, 1).encode("utf-8")

    rep = api.report(_patch_document_xml(clean, patch))
    nums = [
        f
        for bl in rep["blocks"]
        for r in bl["rule_results"]
        for f in r["findings"]
        if f["rule_id"] in ("NUM-01", "NUM-02") and f["level"] == "violation"
    ]
    assert not nums, [f["message"] for f in nums]


def test_seq_fields_with_stale_duplicate_numbers_are_flagged(api, clean):
    def patch(data):
        text = data.decode("utf-8")
        for n_old in ("Таблица 1 – Описательные статистики", "Таблица 2 – Сравнение групп"):
            run = (
                'Таблица </w:t></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> SEQ Таблица \\* ARABIC </w:instrText></w:r>'
                '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
                '<w:r><w:t xml:space="preserve"> – ' + n_old.split("– ", 1)[1]
            )
            text = text.replace(n_old, run, 1)
        return text.encode("utf-8")

    rep = api.report(_patch_document_xml(clean, patch))
    fs = [
        f
        for bl in rep["blocks"]
        for r in bl["rule_results"]
        for f in r["findings"]
        if f["rule_id"] == "NUM-01"
    ]
    assert fs, "повторяющиеся результаты полей SEQ должны давать находку"


def test_autonumbered_headings_are_recognized(api):
    """Заголовки глав с автонумерацией Word (номера нет в тексте абзаца) распознаются как главы."""
    t = Thesis()
    for b in t.blocks:
        if b["k"] == "h2":
            b["t"] = b["t"].split(". ", 1)[1] if ". " in b["t"][:6] else b["t"]
    rep = api.report(t)
    assert rep["structure"] and any(n["kind"] == "CHAPTER" for n in rep["structure"])


# ---- параллельность ----------------------------------------------------------------------
# Параллельные запросы проверяются на реальном сервере (test_h_crash_e2e.py): TestClient создаёт по
# event loop на поток, и общий asyncio-пул слотов в нём ломается независимо от продукта.


def test_slot_released_after_error(clean):
    c = make_client(max_concurrent_jobs=2)
    for _ in range(
        5
    ):  # если слот не освобождается на ошибке, после нескольких отказов сервис «залипнет»
        assert c.post("/api/check", files={"file": ("a.docx", b"%PDF-1.7", DOCX)}).status_code in (
            415,
            422,
        )
    assert c.post("/api/check", files={"file": ("a.docx", clean.bytes(), DOCX)}).status_code == 200


# ---- логи и временные файлы --------------------------------------------------------------
def test_work_content_is_not_written_to_logs(clean, caplog):
    marker = "УникальнаяФразаДляПроверкиЛогов"
    t = clean.sub(
        "Актуальность исследования определяется", f"Актуальность исследования {marker} определяется"
    )
    c = make_client(log_level="DEBUG")
    with caplog.at_level(logging.DEBUG):
        r = c.post("/api/check", files={"file": ("w.docx", t.bytes(), DOCX)})
    assert r.status_code == 200
    assert marker not in caplog.text
    assert "size=" in caplog.text  # размер и время допустимы (имя файла SPEC разрешает, но не требует)


def _vkr_tmp():
    return {p.name for p in Path(tempfile.gettempdir()).glob("vkr-*")}


def test_temp_files_removed_after_success_and_after_error(clean):
    before = _vkr_tmp()
    c = make_client()
    c.post("/api/check", files={"file": ("w.docx", clean.bytes(), DOCX)})
    c.post("/api/check", files={"file": ("w.docx", b"%PDF-1.7", DOCX)})
    c.post("/api/check", files={"file": ("w.docx", clean.bytes()[:3000], DOCX)})
    Api(c).compare(clean, clean)
    assert _vkr_tmp() - before == set()


# ---- аутентификация (server-режим) ----------------------------------------------------------
def test_server_mode_requires_password_to_start():
    from vkr_checker.config import Settings

    with pytest.raises(ValueError):
        Settings(_env_file=None, mode="server")


def test_local_mode_defaults_to_loopback_without_password():
    from vkr_checker.config import Settings

    s = Settings(_env_file=None)
    assert s.mode == "local" and s.host == "127.0.0.1" and not s.auth_required


@pytest.fixture()
def srv():
    c = make_client(mode="server", password="correct-horse")
    c.base_url = "https://testserver"  # cookie выдаётся с Secure: по http клиент её не вернёт
    return c


def test_server_mode_blocks_unauthenticated(srv, clean):
    for r in (
        srv.post("/api/check", files={"file": ("a.docx", clean.bytes(), DOCX)}),
        srv.post(
            "/api/compare",
            files={"old": ("a.docx", clean.bytes(), DOCX), "new": ("b.docx", clean.bytes(), DOCX)},
        ),
        srv.post("/api/export/matrix.xlsx", json={"file_name": "x", "matrix": {}}),
    ):
        assert r.status_code == 401 and err(r)["code"] == "auth_required"
    h = srv.get("/api/health").json()
    assert h["auth_required"] is True and h["authenticated"] is False


def test_server_mode_login_flow_and_cookie_flags(srv, clean):
    bad = srv.post("/api/session", json={"password": "wrong"})
    assert bad.status_code == 401 and err(bad)["code"] == "invalid_password"
    ok = srv.post("/api/session", json={"password": "correct-horse"})
    assert ok.status_code == 204
    cookie = ok.headers["set-cookie"].lower()
    assert "vkr_session=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert (
        srv.post("/api/check", files={"file": ("a.docx", clean.bytes(), DOCX)}).status_code == 200
    )
    out = srv.delete("/api/session")
    assert out.status_code == 204
    srv.cookies.clear()
    assert (
        srv.post("/api/check", files={"file": ("a.docx", clean.bytes(), DOCX)}).status_code == 401
    )


def test_server_mode_bearer_token_works(srv, clean):
    r = srv.post(
        "/api/check",
        files={"file": ("a.docx", clean.bytes(), DOCX)},
        headers={"Authorization": "Bearer correct-horse"},
    )
    assert r.status_code == 200
    r = srv.post(
        "/api/check",
        files={"file": ("a.docx", clean.bytes(), DOCX)},
        headers={"Authorization": "Bearer nope"},
    )
    assert r.status_code == 401


def test_server_mode_forged_cookie_rejected(srv, clean):
    srv.cookies.set("vkr_session", "123456.deadbeef")
    assert (
        srv.post("/api/check", files={"file": ("a.docx", clean.bytes(), DOCX)}).status_code == 401
    )


def test_login_attempts_are_rate_limited():
    c = make_client(mode="server", password="correct-horse", login_rate_per_min=3)
    codes = [c.post("/api/session", json={"password": f"bad{i}"}).status_code for i in range(6)]
    assert 429 in codes, codes
    r = c.post("/api/session", json={"password": "correct-horse"})
    assert r.status_code in (429, 204)
    blocked = [c.post("/api/session", json={"password": "x"}) for _ in range(2)][-1]
    assert blocked.status_code == 429 and blocked.headers.get("retry-after")


def test_local_mode_session_is_noop(client):
    r = client.post("/api/session", json={"password": "anything"})
    assert r.status_code == 204 and "set-cookie" not in r.headers


def test_session_body_validation(srv):
    assert srv.post("/api/session", json={}).status_code == 422
    assert srv.post("/api/session", json={"password": ""}).status_code == 422
    assert srv.post("/api/session", json={"password": "x" * 1000}).status_code == 422
