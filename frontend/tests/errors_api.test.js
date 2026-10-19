import test from "node:test";
import assert from "node:assert/strict";
import { ApiError, userMessage } from "../js/errors.js";
import { createApi } from "../js/api.js";

const jsonResponse = (status, body, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

test("API: ошибка разбирается в ApiError с request_id и Retry-After", async () => {
  const api = createApi({
    fetchImpl: async () =>
      jsonResponse(503, { error: { code: "server_busy", message: "x", request_id: "r1" } }, { "Retry-After": "7" }),
  });
  await assert.rejects(api.check(new File(["a"], "a.docx")), (e) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.code, "server_busy");
    assert.equal(e.requestId, "r1");
    assert.equal(e.retryAfter, 7);
    assert.equal(userMessage(e), "Сервис занят, повторите через 7 с");
    return true;
  });
});

test("API: не-JSON тело ошибки не ломает разбор, request_id берётся из заголовка", async () => {
  const api = createApi({
    fetchImpl: async () => new Response("<html>502</html>", { status: 502, headers: { "X-Request-Id": "h9" } }),
  });
  await assert.rejects(api.getHealth(), (e) => e.status === 502 && e.code === "unknown" && e.requestId === "h9");
});

test("API: сетевой сбой даёт code=network, AbortError пробрасывается как есть", async () => {
  const net = createApi({ fetchImpl: async () => { throw new TypeError("fail"); } });
  await assert.rejects(net.getHealth(), (e) => e.code === "network");
  const abort = createApi({ fetchImpl: async () => { throw new DOMException("x", "AbortError"); } });
  await assert.rejects(abort.getHealth(), (e) => e.name === "AbortError");
});

test("API: compare шлёт поля old и new", async () => {
  let form;
  const api = createApi({ fetchImpl: async (_u, init) => { form = init.body; return jsonResponse(200, {}); } });
  await api.compare(new File(["1"], "o.docx"), new File(["2"], "n.docx"));
  assert.equal(form.get("old").name, "o.docx");
  assert.equal(form.get("new").name, "n.docx");
});

test("тексты ошибок по таблице контракта", () => {
  const mk = (code, extra = {}) => new ApiError({ status: 400, code, message: "серверный текст", ...extra });
  assert.equal(userMessage(mk("file_too_large"), { maxUploadMb: 20 }), "Файл больше 20 МБ");
  assert.equal(userMessage(mk("invalid_password")), "Неверный пароль");
  assert.equal(userMessage(mk("invalid_docx")), "серверный текст");
  assert.equal(userMessage(mk("too_many_attempts", { retryAfter: 30 })), "Подождите 30 с");
  assert.equal(userMessage(mk("internal_error", { requestId: "abc" })), "Не удалось обработать файл, код запроса abc");
  assert.match(userMessage(new Error("x")), /Нет связи/);
});
