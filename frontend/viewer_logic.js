// Чистая логика viewer без DOM (юнит-тестируется в frontend/tests).

export const FILTER_KEYS = ["violation", "suspicion", "not_run", "not_checked"];

export const LEVEL_LABELS = {
  violation: "Нарушение",
  suspicion: "Подозрение",
  not_checked: "Не проверяется",
  not_run: "Проверка не выполнена",
};

/** Ключ фильтра для находки: not_run выделяется отдельно (уровень у него suspicion). */
export function findingKey(finding) {
  return finding.not_run ? "not_run" : finding.level;
}

export function levelLabel(finding) {
  return LEVEL_LABELS[findingKey(finding)] || finding.level;
}

/** Страница показывается только при layout.status = ok и известном номере. */
export function pageLabel(location, layout) {
  if (!layout || layout.status !== "ok") return null;
  if (!Number.isInteger(location.page) || location.page < 1) return null;
  return `≈ стр. ${location.page} (вёрстка LibreOffice)`;
}

/** Делит цитату на до/выделение/после. Некорректный highlight даёт цитату без выделения. */
export function splitQuote(quote, highlight) {
  const text = String(quote ?? "");
  if (!Array.isArray(highlight) || highlight.length !== 2) return { before: text, mark: "", after: "" };
  const [start, end] = highlight;
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || start >= text.length) {
    return { before: text, mark: "", after: "" };
  }
  const stop = Math.min(end, text.length);
  return { before: text.slice(0, start), mark: text.slice(start, stop), after: text.slice(stop) };
}

/** Блоки с применённым фильтром; пустые rule_results отбрасываются, passed — по флагу. */
export function filterBlocks(blocks, activeKeys, showPassed) {
  const active = new Set(activeKeys);
  const result = [];
  for (const block of blocks || []) {
    const rules = [];
    for (const rule of block.rule_results || []) {
      if (rule.outcome === "passed") {
        if (showPassed) rules.push({ ...rule, findings: [] });
        continue;
      }
      const findings = (rule.findings || []).filter((f) => active.has(findingKey(f)));
      const shownEmptyNotRun = rule.outcome === "not_run" && findings.length === 0 && active.has("not_run");
      if (findings.length || shownEmptyNotRun) rules.push({ ...rule, findings });
    }
    if (rules.length) result.push({ ...block, rule_results: rules });
  }
  return result;
}

/** Текст о неудачной/частичной вёрстке для шапки. */
export function layoutNote(layout) {
  if (!layout) return "";
  if (layout.status === "failed") {
    return `Вёрстка LibreOffice не получена${layout.reason ? `: ${layout.reason}` : ""}. Объём оценён по тексту.`;
  }
  if (layout.status === "partial") {
    const cov = typeof layout.coverage === "number" ? ` (охват ${Math.round(layout.coverage * 100)}%)` : "";
    return `Вёрстка получена частично${cov}. ${layout.disclaimer || ""}`.trim();
  }
  return layout.disclaimer || "";
}

export function volumeNote(volume) {
  if (!volume) return "";
  const pages = volume.pages_main == null ? "—" : String(volume.pages_main);
  const how = volume.method === "layout" ? "по вёрстке LibreOffice" : "оценка по тексту";
  return `Основная часть: ${pages} стр. (${how})`;
}
