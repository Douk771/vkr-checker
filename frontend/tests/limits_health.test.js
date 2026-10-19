import test from "node:test";
import assert from "node:assert/strict";
import { validateDocx } from "../js/limits.js";
import { interpretHealth } from "../js/health.js";

const MB = 1024 * 1024;
const limits = { max_upload_mb: 20 };

test("validateDocx: расширение, пустой файл, размер", () => {
  assert.equal(validateDocx({ name: "a.docx", size: 5 }, limits), null);
  assert.equal(validateDocx({ name: "A.DOCX", size: 5 }, limits), null);
  assert.match(validateDocx({ name: "a.doc", size: 5 }, limits), /Нужен \.docx/);
  assert.match(validateDocx({ name: "a.docx.pdf", size: 5 }, limits), /Нужен \.docx/);
  assert.match(validateDocx({ name: "a.docx", size: 0 }, limits), /Выберите/);
  assert.equal(validateDocx({ name: "a.docx", size: 20 * MB }, limits), null);
  assert.equal(validateDocx({ name: "a.docx", size: 20 * MB + 1 }, limits), "Файл больше 20 МБ");
  assert.equal(validateDocx({ name: "a.docx", size: 30 * MB }, { max_upload_mb: 50 }), null);
  assert.match(validateDocx(null, limits), /Выберите/);
});

test("interpretHealth: пароль и баннер LibreOffice", () => {
  const base = { auth_required: false, authenticated: false, layout_available: true, layout_engine: "LibreOffice 24.2", limits };
  assert.equal(interpretHealth(base).needLogin, false);
  assert.equal(interpretHealth({ ...base, auth_required: true }).needLogin, true);
  assert.equal(interpretHealth({ ...base, auth_required: true, authenticated: true }).needLogin, false);
  assert.equal(interpretHealth(base).showLayoutBanner, false);
  assert.equal(interpretHealth({ ...base, layout_available: false, layout_engine: null }).showLayoutBanner, true);
});
