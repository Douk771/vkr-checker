import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { splitQuote, pageLabel, filterBlocks, findingKey, levelLabel, layoutNote, FILTER_KEYS } from "../viewer_logic.js";

const golden = (n) => JSON.parse(readFileSync(new URL(`../../tests/golden/${n}.json`, import.meta.url), "utf8"));

test("splitQuote: валидный и некорректный highlight", () => {
  assert.deepEqual(splitQuote("Показатель", [0, 4]), { before: "", mark: "Пока", after: "затель" });
  assert.deepEqual(splitQuote("abc", [1, 99]), { before: "a", mark: "bc", after: "" });
  for (const bad of [null, [3, 3], [-1, 2], [5, 9], [1], ["a", 2]]) {
    assert.deepEqual(splitQuote("abc", bad), { before: "abc", mark: "", after: "" });
  }
});

test("pageLabel: только при layout.status=ok", () => {
  const loc = { page: 21 };
  assert.equal(pageLabel(loc, { status: "ok" }), "≈ стр. 21 (вёрстка LibreOffice)");
  assert.equal(pageLabel(loc, { status: "partial" }), null);
  assert.equal(pageLabel(loc, { status: "failed" }), null);
  assert.equal(pageLabel({ page: null }, { status: "ok" }), null);
});

test("findingKey: not_run выделяется из suspicion", () => {
  const f = { level: "suspicion", not_run: true };
  assert.equal(findingKey(f), "not_run");
  assert.equal(levelLabel(f), "Проверка не выполнена");
  assert.equal(levelLabel({ level: "violation", not_run: false }), "Нарушение");
});

test("filterBlocks на golden: фильтр уровней и passed", () => {
  const rep = golden("check_findings");
  const all = filterBlocks(rep.blocks, FILTER_KEYS, false);
  const count = (bs) => bs.flatMap((b) => b.rule_results).flatMap((r) => r.findings).length;
  const violationsOnly = filterBlocks(rep.blocks, ["violation"], false);
  assert.ok(count(violationsOnly) <= count(all));
  assert.ok(violationsOnly.flatMap((b) => b.rule_results).flatMap((r) => r.findings).every((f) => f.level === "violation" && !f.not_run));
  assert.deepEqual(filterBlocks(rep.blocks, [], false), []);
});

test("layoutNote: failed содержит причину, ok — оговорку", () => {
  const failed = golden("check_layout_failed").layout;
  assert.match(layoutNote(failed), /не получена/);
  assert.equal(layoutNote({ status: "ok", disclaimer: "D" }), "D");
});
