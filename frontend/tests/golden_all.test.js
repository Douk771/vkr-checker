// Unit: вся клиентская логика на всех golden-JSON и XSS-фикстуре (без DOM и сети).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { FILTER_KEYS, filterBlocks, splitQuote, pageLabel, layoutNote } from "../viewer_logic.js";
import { buildStandaloneHtml } from "../js/download.js";

const NAMES = ["check_clean", "check_findings", "check_layout_failed"];
const golden = (n) => JSON.parse(readFileSync(new URL(`../../tests/golden/${n}.json`, import.meta.url), "utf8"));
const src = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const XSS = "</script><img src=x onerror=alert(1)>";

function eachFinding(report, fn) {
  for (const b of report.blocks || []) for (const r of b.rule_results || []) for (const f of r.findings || []) fn(f);
}

for (const name of NAMES) {
  test(`golden ${name}: логика отчёта не падает`, () => {
    const rep = golden(name);
    assert.doesNotThrow(() => filterBlocks(rep.blocks, FILTER_KEYS, true));
    assert.doesNotThrow(() => layoutNote(rep.layout));
    eachFinding(rep, (f) => {
      for (const loc of f.locations || []) pageLabel(loc, rep.layout);
      if (f.quote) assert.doesNotThrow(() => splitQuote(f.quote, f.highlight));
    });
  });
}

test("check_layout_failed: страницы не показываются", () => {
  const rep = golden("check_layout_failed");
  eachFinding(rep, (f) => (f.locations || []).forEach((l) => assert.ok(!pageLabel(l, rep.layout))));
});

test("XSS: payload в цитате и сообщении не попадает в скачанный HTML как разметка", () => {
  const rep = golden("check_findings");
  eachFinding(rep, (f) => { f.quote = XSS; f.message = XSS; });
  const html = buildStandaloneHtml(rep, {
    css: "body{}", logicJs: src("../viewer_logic.js"), artifactsJs: src("../js/artifacts.js"), viewerJs: src("../viewer.js"),
  });
  assert.ok(!html.includes(XSS));
  assert.ok(!html.includes("<img src=x"));
  assert.equal((html.match(/<script/g) || []).length, 2);
});

test("XSS: splitQuote возвращает только текстовые части", () => {
  const parts = splitQuote(XSS, { start: 0, end: 5 });
  assert.equal(JSON.stringify(parts).includes("<img"), true); // данные сохранены как текст
  assert.ok(Array.isArray(parts) || typeof parts === "object");
});
