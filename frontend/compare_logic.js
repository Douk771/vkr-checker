// Чистая логика отчёта сравнения (CompareReport.diff). Без DOM.

export const SECTION_LABELS = {
  unchanged: "без изменений", modified: "изменён", renamed: "переименован", added: "добавлен", removed: "удалён",
};
export const PARA_LABELS = {
  unchanged: "без изменений", modified: "изменён", inserted: "добавлен", deleted: "удалён",
  moved_out: "перенесён отсюда", moved_in: "перенесён сюда",
};
export const OBJECT_LABELS = { unchanged: "без изменений", modified: "изменена", added: "добавлена", removed: "удалена" };
export const ROW_LABELS = { added: "строка добавлена", removed: "строка удалена", modified: "строка изменена" };
export const FLAG_LABELS = { renumbered: "изменён номер", retitled: "изменён заголовок" };
export const SEGMENT_MARK = { equal: "", ins: "[+", del: "[−" };
export const TREND_LABELS = { less: "стало меньше", more: "стало больше", same: "без изменений", null: "" };

/** Раздел сворачивается, если сам и все абзацы без изменений. */
export function isCollapsedSection(s) {
  return s.status === "unchanged" && (s.paragraphs || []).every((p) => p.status === "unchanged");
}

export function sectionTitle(s) {
  if (s.status === "renamed") return `${s.old_title || "—"} → ${s.new_title || "—"}`;
  return s.new_title || s.old_title || "(раздел без названия)";
}

/** Сколько разделов свёрнуто и сколько показано. */
export function sectionStats(sections) {
  const list = sections || [];
  const collapsed = list.filter(isCollapsedSection).length;
  return { total: list.length, collapsed, changed: list.length - collapsed };
}

/** Абзацы в подряд идущих unchanged объединяются в счётчик, чтобы не раздувать отчёт. */
export function groupParagraphs(paragraphs) {
  const out = [];
  for (const p of paragraphs || []) {
    const last = out[out.length - 1];
    if (p.status === "unchanged" && last && last.kind === "same") last.items.push(p);
    else if (p.status === "unchanged") out.push({ kind: "same", items: [p] });
    else out.push({ kind: "para", para: p });
  }
  return out;
}

/** Сегменты -> безопасный список {op,text}; неизвестный op трактуется как equal. */
export function normalizeSegments(segments) {
  return (segments || []).map((s) => ({ op: s.op === "ins" || s.op === "del" ? s.op : "equal", text: String(s.text ?? "") }));
}

/** Текст абзаца целиком по сегментам: для режима "после" (без del) или "до" (без ins). */
export function segmentsText(segments, side) {
  const skip = side === "old" ? "ins" : "del";
  return normalizeSegments(segments).filter((s) => s.op !== skip).map((s) => s.text).join("");
}

/** Связка перенесённых абзацев по move_id: id -> Move. */
export function indexMoves(moves) {
  const map = new Map();
  for (const m of moves || []) map.set(m.id, m);
  return map;
}

export function moveLabel(move) {
  if (!move) return "";
  return `из «${move.from_section}» в «${move.to_section}»`;
}

export function cellRef(c) {
  return `столбец ${c.col}: «${c.old}» → «${c.new}»`;
}

export function objectTitle(o) {
  const a = o.old_label, b = o.new_label;
  if (a && b && a !== b) return `${a} → ${b}`;
  return b || a || "(без подписи)";
}

export function rowLabel(r) {
  const n = r.new_row ?? r.old_row;
  return `${ROW_LABELS[r.status] || r.status}${n != null ? ` ${n}` : ""}`;
}

export function dynamicsLine(item) {
  const a = item.count_old ?? 0, b = item.count_new ?? 0;
  const trend = TREND_LABELS[item.trend == null ? "null" : item.trend] || "";
  return `${a} → ${b}${trend ? `, ${trend}` : ""}`;
}

export function diffSummary(diff) {
  const d = diff || {};
  const st = sectionStats(d.sections);
  return {
    sectionsChanged: st.changed,
    moves: (d.moves || []).length,
    numbers: (d.number_changes || []).length,
    tables: (d.tables || []).filter((t) => t.status !== "unchanged").length,
    figures: (d.figures || []).filter((t) => t.status !== "unchanged").length,
    impact: (d.impact || []).length,
  };
}

export function isEmptyDiff(diff) {
  const s = diffSummary(diff);
  return Object.values(s).every((n) => n === 0);
}
