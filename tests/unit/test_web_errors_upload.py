import asyncio
import io
import json

import pytest
from starlette.datastructures import UploadFile

from vkr_checker.web.errors import ERRORS, ApiError, error_response
from vkr_checker.web.middleware import BodyLimitMiddleware, RequestContextMiddleware
from vkr_checker.web.upload import _save, safe_basename

CONTRACT_CODES = {
    "bad_request", "missing_file", "auth_required", "invalid_password", "file_too_large",
    "unsupported_format", "invalid_docx", "docx_limits_exceeded", "validation_error",
    "too_many_attempts", "server_busy", "processing_timeout", "internal_error",
}  # fmt: skip


def test_all_13_contract_codes_defined_with_http_status():
    assert set(ERRORS) == CONTRACT_CODES
    assert {c: ERRORS[c][0] for c in ("missing_file", "file_too_large", "unsupported_format")} == {
        "missing_file": 400,
        "file_too_large": 413,
        "unsupported_format": 415,
    }


def test_unknown_error_code_rejected():
    with pytest.raises(ValueError):
        ApiError("nope")


def test_error_response_format_and_headers():
    resp = error_response(ApiError("server_busy", retry_after=7, field="new"), "abc123")
    body = json.loads(resp.body)
    assert body == {
        "error": {
            "code": "server_busy",
            "message": ERRORS["server_busy"][1],
            "field": "new",
            "request_id": "abc123",
        }
    }
    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "7"
    assert resp.headers["x-request-id"] == "abc123"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("работа.docx", "работа.docx"),
        ("C:\\Users\\x\\работа.docx", "работа.docx"),
        ("/etc/passwd", "passwd"),
        ("../../a.docx", "a.docx"),
        ("", "document.docx"),
        (None, "document.docx"),
        ("a\x00b\n.docx", "ab.docx"),
        ("x" * 500 + ".docx", ("x" * 500 + ".docx")[:200]),
    ],
)
def test_safe_basename(raw, expected):
    assert safe_basename(raw) == expected


def test_save_writes_file_and_reports_size(tmp_path):
    up = UploadFile(io.BytesIO(b"PK" + b"a" * 100), filename="x.docx")
    saved = _save(up, "file", tmp_path, max_bytes=1000)
    assert saved.size == 102
    assert saved.path.read_bytes().startswith(b"PK")
    assert saved.name == "x.docx"


def test_save_rejects_too_large_with_field(tmp_path):
    up = UploadFile(io.BytesIO(b"a" * 2_100_000), filename="x.docx")
    with pytest.raises(ApiError) as exc:
        _save(up, "old", tmp_path, max_bytes=2 * 1024 * 1024)
    assert (exc.value.code, exc.value.field) == ("file_too_large", "old")


def test_save_rejects_empty_file(tmp_path):
    with pytest.raises(ApiError) as exc:
        _save(UploadFile(io.BytesIO(b""), filename="x.docx"), "file", tmp_path, 10)
    assert exc.value.code == "missing_file"
    assert not (tmp_path / "file.docx").exists()


async def _drive(app, scope, chunks):
    """Прогоняет ASGI-приложение с заданным телом; возвращает (status, headers, body)."""
    messages = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
        for i, c in enumerate(chunks)
    ]
    sent = []

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), body


def _scope(method="POST", path="/api/check", headers=()):
    return {"type": "http", "method": method, "path": path, "headers": list(headers)}


async def _consume_app(scope, receive, send):
    while True:
        msg = await receive()
        if not msg.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def test_body_limit_by_declared_content_length():
    app = BodyLimitMiddleware(_consume_app, {("POST", "/api/check"): (10, "Файл больше")})
    scope = _scope(headers=[(b"content-length", b"11")])
    status, _, body = asyncio.run(_drive(app, scope, [b"x"]))
    assert status == 413
    assert json.loads(body)["error"]["code"] == "file_too_large"


def test_body_limit_counts_streamed_bytes_without_content_length():
    app = BodyLimitMiddleware(_consume_app, {("POST", "/api/check"): (10, "Файл больше")})
    with pytest.raises(ApiError) as exc:  # в приложении его превратит обработчик ApiError
        asyncio.run(_drive(app, _scope(), [b"x" * 6, b"x" * 6]))
    assert exc.value.code == "file_too_large"


def test_body_limit_passes_small_and_unlisted_paths():
    app = BodyLimitMiddleware(_consume_app, {("POST", "/api/check"): (10, "m")})
    assert asyncio.run(_drive(app, _scope(), [b"12345"]))[0] == 200
    assert asyncio.run(_drive(app, _scope(path="/api/other"), [b"x" * 99]))[0] == 200


def test_request_context_hides_unhandled_exception():
    async def boom(scope, receive, send):
        raise RuntimeError("секрет из текста работы")

    status, headers, body = asyncio.run(_drive(RequestContextMiddleware(boom), _scope(), [b""]))
    assert status == 500
    assert "секрет".encode() not in body
    assert json.loads(body)["error"]["code"] == "internal_error"
    assert json.loads(body)["error"]["request_id"] == headers[b"x-request-id"].decode()
