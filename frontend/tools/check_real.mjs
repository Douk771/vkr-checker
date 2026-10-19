// F-20: сверка реального бэкенда с контрактом/golden.
// Использование: node tools/check_real.mjs <base_url> <file.docx> [password]
// Реальные .docx не коммитить.
import { readFileSync } from "node:fs";
import { basename } from "node:path";
import { FILTER_KEYS, filterBlocks } from "../viewer_logic.js";

const [base = "http://127.0.0.1:8000", file, password] = process.argv.slice(2);
if (!file) { console.error("нужен путь к .docx"); process.exit(2); }
const golden = JSON.parse(readFileSync(new URL("../../tests/golden/check_findings.json", import.meta.url), "utf8"));

let cookie = "";
const health = await (await fetch(`${base}/api/health`)).json();
if (health.auth_required) {
  const r = await fetch(`${base}/api/session`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ password }) });
  if (!r.ok) { console.error("вход не удался", r.status); process.exit(1); }
  cookie = (r.headers.get("set-cookie") || "").split(";")[0];
}
const form = new FormData();
form.append("file", new Blob([readFileSync(file)]), basename(file));
const res = await fetch(`${base}/api/check`, { method: "POST", body: form, headers: cookie ? { cookie } : {} });
const rep = await res.json();
if (!res.ok) { console.error("ошибка API", res.status, JSON.stringify(rep.error || rep)); process.exit(1); }

const problems = [];
for (const k of Object.keys(golden)) if (!(k in rep)) problems.push(`нет поля верхнего уровня: ${k}`);
for (const k of Object.keys(rep)) if (!(k in golden)) problems.push(`лишнее поле верхнего уровня: ${k}`);
try { filterBlocks(rep.blocks, FILTER_KEYS, true); } catch (e) { problems.push(`viewer_logic: ${e.message}`); }
console.log(problems.length ? problems.join("\n") : "OK: структура совпадает с golden");
process.exit(problems.length ? 1 : 0);
