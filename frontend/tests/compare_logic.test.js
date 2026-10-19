import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  isCollapsedSection, sectionTitle, sectionStats, groupParagraphs, normalizeSegments, segmentsText,
  indexMoves, moveLabel, objectTitle, rowLabel, cellRef, dynamicsLine, diffSummary, isEmptyDiff,
} from "../compare_logic.js";

const golden = JSON.parse(readFileSync(new URL("../../tests/golden/compare.json", import.meta.url), "utf8"));
const diff = golden.diff;

test("unchanged section is collapsed, modified is not", () => {
  assert.equal(isCollapsedSection(diff.sections[0]), true);
  assert.equal(isCollapsedSection(diff.sections[1]), false);
  assert.deepEqual(sectionStats(diff.sections), { total: 4, collapsed: 1, changed: 3 });
});

test("unchanged status with a changed paragraph is not collapsed", () => {
  assert.equal(isCollapsedSection({ status: "unchanged", paragraphs: [{ status: "inserted" }] }), false);
});

test("section titles", () => {
  assert.equal(sectionTitle(diff.sections[2]), "Методы → Организация и методы");
  assert.equal(sectionTitle(diff.sections[3]), "Выводы по главе 1");
  assert.equal(sectionTitle({ status: "added", paragraphs: [] }), "(раздел без названия)");
});

test("groupParagraphs merges consecutive unchanged", () => {
  const g = groupParagraphs([{ status: "unchanged" }, { status: "unchanged" }, { status: "modified" }, { status: "unchanged" }]);
  assert.deepEqual(g.map((x) => x.kind), ["same", "para", "same"]);
  assert.equal(g[0].items.length, 2);
});

test("segments: unknown op becomes equal, null text safe, old/new text", () => {
  const seg = diff.sections[1].paragraphs[0].segments;
  assert.equal(segmentsText(seg, "old"), "Выборка составила 50 человек.");
  assert.equal(segmentsText(seg, "new"), "Выборка составила 60 человек.");
  assert.deepEqual(normalizeSegments([{ op: "x", text: null }]), [{ op: "equal", text: "" }]);
  assert.deepEqual(normalizeSegments(undefined), []);
});

test("moves linked by move_id", () => {
  const m = indexMoves(diff.moves).get(diff.sections[1].paragraphs[1].move_id);
  assert.equal(moveLabel(m), "из «Введение» в «Глава 1»");
  assert.equal(moveLabel(undefined), "");
});

test("object titles, rows, cells", () => {
  assert.equal(objectTitle(diff.tables[0]), "Таблица 2 → Таблица 3");
  assert.equal(objectTitle(diff.figures[0]), "Рисунок 1");
  assert.equal(rowLabel(diff.tables[0].rows[1]), "строка добавлена 5");
  assert.equal(cellRef(diff.tables[0].rows[0].cells[0]), "столбец 2: «3,4» → «3,6»");
});

test("dynamics line handles null counts", () => {
  assert.equal(dynamicsLine(diff.dynamics.fixed[0]), "2 → 0, стало меньше");
  assert.equal(dynamicsLine(diff.dynamics.new[0]), "0 → 1, стало больше");
  assert.equal(dynamicsLine({ count_old: null, count_new: null, trend: null }), "0 → 0");
});

test("summary and empty diff", () => {
  const s = diffSummary(diff);
  assert.deepEqual(s, { sectionsChanged: 3, moves: 1, numbers: 1, tables: 1, figures: 1, impact: 1 });
  assert.equal(isEmptyDiff(diff), false);
  assert.equal(isEmptyDiff({}), true);
  assert.equal(isEmptyDiff({ sections: [{ status: "unchanged", paragraphs: [] }], tables: [{ status: "unchanged", flags: [], rows: [] }] }), true);
});
