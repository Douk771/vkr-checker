// Известные artifacts (API_CONTRACT §2): приводим свободную структуру к простой таблице.
// Формат значений контрактом не зафиксирован, поэтому разбор терпим к форме данных.

export const KNOWN_ARTIFACTS = {
  "INT-01": [{ key: "elements", title: "Элементы введения" }],
  "VOL-01": [{ key: "by_section", title: "Объём по разделам" }],
  "TSK-01": [{ key: "task_map", title: "Соответствие задач и выводов" }],
  "CON-01": [{ key: "numbers_index", title: "Числа в тексте" }],
};

function isLocation(v) {
  return v && typeof v === "object" && !Array.isArray(v) && ("section_path" in v || "paragraph_idx" in v);
}

/** Значение ячейки -> строка. Объекты-места читаются как «раздел; абзац N». */
export function cellText(v) {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(cellText).filter(Boolean).join("; ");
  if (isLocation(v)) {
    const parts = [];
    const path = (v.section_path || []).join(" › ");
    if (path) parts.push(path);
    if (v.paragraph_idx != null) parts.push(`абзац ${v.paragraph_idx}`);
    return parts.join("; ");
  }
  if (typeof v === "object") {
    return Object.entries(v).map(([k, x]) => `${k}: ${cellText(x)}`).join(", ");
  }
  return "";
}

/** value -> {columns:[string], rows:[[string]]} или null, если показывать нечего. */
export function toTable(value) {
  if (value == null) return null;
  let records;
  if (Array.isArray(value)) {
    records = value;
  } else if (typeof value === "object") {
    records = Object.entries(value).map(([k, v]) =>
      v && typeof v === "object" && !Array.isArray(v) && !isLocation(v) ? { name: k, ...v } : { name: k, value: v });
  } else {
    return null;
  }
  if (!records.length) return null;
  if (records.every((r) => r === null || typeof r !== "object" || Array.isArray(r))) {
    return { columns: ["Значение"], rows: records.map((r) => [cellText(r)]) };
  }
  const columns = [];
  for (const r of records) {
    if (r && typeof r === "object") for (const k of Object.keys(r)) if (!columns.includes(k)) columns.push(k);
  }
  const rows = records.map((r) => columns.map((c) => cellText(r && typeof r === "object" ? r[c] : "")));
  return { columns, rows };
}

/** Таблицы правила: [{title, table}], только для известных ключей и непустых данных. */
export function ruleTables(rule) {
  const spec = KNOWN_ARTIFACTS[rule && rule.rule_id];
  const art = rule && rule.artifacts;
  if (!spec || !art || typeof art !== "object") return [];
  const out = [];
  for (const { key, title } of spec) {
    const table = toTable(art[key]);
    if (table) out.push({ title, table });
  }
  return out;
}

export const CELL_STATUS_LABELS = { auto: "найдено", gap: "пробел", "n/a": "не требуется" };
export const MATRIX_COLUMNS = [
  ["theory", "Теория"], ["instrument", "Инструмент"], ["calculation", "Расчёт"],
  ["result", "Результат"], ["conclusion", "Вывод"],
];
export const ROW_KIND_LABELS = { hypothesis_part: "Гипотеза", defense_position: "Положение", task: "Задача" };

/** Тело запроса POST /api/export/matrix.xlsx. */
export function buildExportPayload(report) {
  return {
    file_name: String(report.file.name).slice(0, 200),
    service_version: report.service_version,
    checked_at: report.checked_at,
    matrix: report.matrix,
  };
}
