import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { validateSelection, formatElapsed, withAuthRetry, reportFromResponse, progressText } from "../js/upload_logic.js";
import { escapeJsonForScript, buildStandaloneHtml, reportFileName, stripModuleSyntax } from "../js/download.js";
import { toTable, ruleTables, buildExportPayload, cellText } from "../js/artifacts.js";

const golden = (n) => JSON.parse(readFileSync(new URL(`../../tests/golden/${n}.json`, import.meta.url)));
const docx = (name, size = 100) => ({ name, size });

test("validateSelection: режимы и слоты", () => {
  assert.equal(validateSelection("check", { file: docx("a.docx") }, {}).ok, true);
  const r = validateSelection("compare", { old: docx("a.docx"), new: docx("b.pdf") }, {});
  assert.equal(r.ok, false);
  assert.equal(r.errors.old, null);
  assert.ok(r.errors.new);
  assert.equal(validateSelection("compare", { old: docx("a.docx") }, {}).ok, false);
});

test("formatElapsed / progressText", () => {
  assert.equal(formatElapsed(42.9), "42 с");
  assert.equal(formatElapsed(75), "1 мин 15 с");
  assert.match(progressText("compare", 3, { compare_timeout_s: 180, check_timeout_s: 60 }), /сравнение.*до 180 с/);
});

test("withAuthRetry: повтор один раз после 401", async () => {
  let calls = 0;
  const action = async () => { if (++calls === 1) throw { status: 401 }; return "ok"; };
  assert.equal(await withAuthRetry(action, async () => true), "ok");
  assert.equal(calls, 2);
});

test("withAuthRetry: отказ от входа и не-401 пробрасываются", async () => {
  await assert.rejects(withAuthRetry(async () => { throw { status: 401 }; }, async () => false), { status: 401 });
  let asked = false;
  await assert.rejects(withAuthRetry(async () => { throw { status: 500 }; }, async () => { asked = true; return true; }), { status: 500 });
  assert.equal(asked, false);
  let n = 0;
  await assert.rejects(withAuthRetry(async () => { n++; throw { status: 401 }; }, async () => true), { status: 401 });
  assert.equal(n, 2);
});

test("reportFromResponse берёт new для сравнения", () => {
  const c = golden("compare");
  assert.equal(reportFromResponse("compare", c), c.new);
  assert.equal(reportFromResponse("check", { a: 1 }).a, 1);
});

test("escapeJsonForScript не оставляет '<' и сохраняет данные", () => {
  const rep = { quote: "</script><img onerror=x>", ls: "a b" };
  const out = escapeJsonForScript(rep);
  assert.ok(!out.includes("<"));
  assert.ok(!out.includes(" "));
  assert.deepEqual(JSON.parse(out), rep);
});

test("buildStandaloneHtml: самодостаточный, один блок данных, XSS-безопасен", () => {
  const rep = golden("check_findings");
  rep.file.name = "x</script><b>.docx";
  const viewerJs = readFileSync(new URL("../viewer.js", import.meta.url), "utf8");
  const logicJs = readFileSync(new URL("../viewer_logic.js", import.meta.url), "utf8");
  const artifactsJs = readFileSync(new URL("../js/artifacts.js", import.meta.url), "utf8");
  const html = buildStandaloneHtml(rep, { css: "body{}", logicJs, artifactsJs, viewerJs });
  assert.equal((html.match(/<script/g) || []).length, 2);
  assert.ok(!/\bimport\s.*from/.test(html.split('id="report-data"')[1]));
  assert.ok(!/^export\s/m.test(html));
  assert.ok(!html.includes('src="/'));
  assert.ok(!html.includes("<b>.docx"));
  // единый скрипт должен быть валидным классическим JS
  const script = html.split("<script>")[1].split("</script>")[0];
  assert.doesNotThrow(() => new Function(script));
});

test("stripModuleSyntax: многострочный import и export", () => {
  const out = stripModuleSyntax('import {\n a,\n b,\n} from "./x.js";\nexport function f() {}\nexport const Z = 1;');
  assert.ok(!out.includes("import") && !out.includes("export"));
  assert.ok(out.includes("function f") && out.includes("const Z"));
});

test("reportFileName", () => {
  assert.equal(reportFileName("Иванов.docx"), "Иванов_отчёт.html");
  assert.equal(reportFileName("a/b:c.DOCX"), "a_b_c_отчёт.html");
  assert.equal(reportFileName(""), "report_отчёт.html");
});

test("toTable: массив объектов, словарь, скаляры, пусто", () => {
  assert.deepEqual(toTable([{ a: 1, b: "x" }, { a: 2, c: true }]),
    { columns: ["a", "b", "c"], rows: [["1", "x", ""], ["2", "", "true"]] });
  assert.deepEqual(toTable({ "Введение": { pages: 3 } }), { columns: ["name", "pages"], rows: [["Введение", "3"]] });
  assert.deepEqual(toTable(["x", "y"]), { columns: ["Значение"], rows: [["x"], ["y"]] });
  assert.equal(toTable([]), null);
  assert.equal(toTable(null), null);
  assert.equal(toTable(5), null);
});

test("cellText: место читается человеком", () => {
  assert.equal(cellText({ section_path: ["Введение"], paragraph_idx: 4 }), "Введение; абзац 4");
});

test("ruleTables: только известные правила и ключи, отсутствие не ошибка", () => {
  assert.deepEqual(ruleTables({ rule_id: "INT-01", artifacts: {} }), []);
  assert.deepEqual(ruleTables({ rule_id: "XXX-01", artifacts: { elements: [1] } }), []);
  assert.deepEqual(ruleTables({ rule_id: "VOL-01", artifacts: { by_section: [{ title: "A", pages: 2 }], method: "layout" } }).map((t) => t.title), ["Объём по разделам"]);
  assert.deepEqual(ruleTables(undefined), []);
});

test("buildExportPayload по контракту", () => {
  const rep = golden("check_findings");
  const p = buildExportPayload(rep);
  assert.equal(p.file_name, rep.file.name);
  assert.equal(p.matrix, rep.matrix);
  assert.equal(p.checked_at, rep.checked_at);
});
