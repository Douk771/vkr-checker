// F-20: сверка реального бэкенда с контрактом/golden.
// check:   node tools/check_real.mjs <base_url> <file.docx> [password]
// compare: node tools/check_real.mjs --compare <base_url> <old.docx> <new.docx> [password]
// Сверяется структура (ключи), не значения. Реальные .docx не коммитить.
import { readFileSync } from "node:fs";
import { basename } from "node:path";
import { FILTER_KEYS, filterBlocks } from "../viewer_logic.js";
import { sectionStats } from "../compare_logic.js";

const args = process.argv.slice(2);
const isCompare = args[0] === "--compare";
if (isCompare) args.shift();
const base = args[0] || "http://127.0.0.1:8000";
const files = isCompare ? [args[1], args[2]] : [args[1]];
const password = isCompare ? args[3] : args[2];
if (files.some((f) => !f)) { console.error(isCompare ? "нужны old.docx и new.docx" : "нужен путь к .docx"); process.exit(2); }

const goldenName = isCompare ? "compare.json" : "check_findings.json";
const golden = JSON.parse(readFileSync(new URL(`../../tests/golden/${goldenName}`, import.meta.url), "utf8"));

let cookie = "";
const health = await (await fetch(`${base}/api/health`)).json();
if (health.auth_required) {
  const r = await fetch(`${base}/api/session`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ password }) });
  if (!r.ok) { console.error("вход не удался", r.status); process.exit(1); }
  cookie = (r.headers.get("set-cookie") || "").split(";")[0];
}
const form = new FormData();
const part = (name, f) => form.append(name, new Blob([readFileSync(f)]), basename(f));
if (isCompare) { part("old", files[0]); part("new", files[1]); } else part("file", files[0]);
const res = await fetch(`${base}/api/${isCompare ? "compare" : "check"}`, { method: "POST", body: form, headers: cookie ? { cookie } : {} });
const rep = await res.json();
if (!res.ok) { console.error("ошибка API", res.status, JSON.stringify(rep.error || rep)); process.exit(1); }

const problems = [];
const diffKeys = (exp, got, path) => {
  for (const k of Object.keys(exp)) if (!(k in got)) problems.push(`нет поля ${path}${k}`);
  for (const k of Object.keys(got)) if (!(k in exp)) problems.push(`лишнее поле ${path}${k}`);
};
diffKeys(golden, rep, "");
if (isCompare) {
  if (rep.diff && golden.diff) diffKeys(golden.diff, rep.diff, "diff.");
  try { sectionStats(rep.diff?.sections); } catch (e) { problems.push(`compare_logic: ${e.message}`); }
  try { filterBlocks(rep.new?.blocks, FILTER_KEYS, true); } catch (e) { problems.push(`viewer_logic(new): ${e.message}`); }
} else {
  try { filterBlocks(rep.blocks, FILTER_KEYS, true); } catch (e) { problems.push(`viewer_logic: ${e.message}`); }
}
console.log(problems.length ? problems.join("\n") : `OK: структура совпадает с ${goldenName}`);
process.exit(problems.length ? 1 : 0);
