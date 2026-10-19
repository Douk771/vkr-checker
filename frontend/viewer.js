// Рендер CheckReport. Любой текст из отчёта попадает в DOM только через textContent.
import {
  FILTER_KEYS, LEVEL_LABELS, findingKey, levelLabel, pageLabel, splitQuote,
  filterBlocks, layoutNote, volumeNote,
} from "./viewer_logic.js";

function el(tag, { cls, text, attrs } = {}, children = []) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  for (const c of children) if (c) node.append(c);
  return node;
}

function renderLocation(loc, layout) {
  const li = el("li", { cls: "loc" });
  const path = (loc.section_path || []).join(" › ");
  const parts = [];
  if (path) parts.push(path);
  if (loc.paragraph_idx != null) parts.push(`абзац ${loc.paragraph_idx}`);
  if (loc.table) {
    const t = loc.table;
    let s = t.number_label || `таблица ${t.table_idx}`;
    if (t.row != null) s += `, строка ${t.row}`;
    if (t.col != null) s += `, столбец ${t.col}`;
    parts.push(s);
  }
  const page = pageLabel(loc, layout);
  if (page) parts.push(page);
  li.append(el("span", { cls: "loc__path", text: parts.join("; ") }));
  if (loc.quote) {
    const q = splitQuote(loc.quote, loc.highlight);
    const quote = el("blockquote", { cls: "loc__quote" });
    quote.append(document.createTextNode(q.before));
    if (q.mark) quote.append(el("mark", { text: q.mark }));
    quote.append(document.createTextNode(q.after));
    li.append(quote);
  }
  return li;
}

export function renderFinding(f, layout) {
  const key = findingKey(f);
  const head = el("div", { cls: "finding__head" }, [
    el("span", { cls: `badge badge--${key}`, text: levelLabel(f) }),
    f.count > 1 ? el("span", { cls: "finding__count", text: `×${f.count}` }) : null,
    el("span", { cls: "finding__rule", text: f.rule_id }),
  ]);
  const node = el("li", { cls: `finding finding--${key}` }, [head, el("p", { cls: "finding__msg", text: f.message })]);
  if ((f.locations || []).length) {
    const ul = el("ul", { cls: "locs" });
    for (const loc of f.locations) ul.append(renderLocation(loc, layout));
    node.append(ul);
  }
  if (f.hint) node.append(el("p", { cls: "finding__hint", text: `Подсказка: ${f.hint}` }));
  return node;
}

function renderRule(rule, layout) {
  const outcomeText = { passed: "пройдено", findings: "", not_run: "проверка не выполнена", not_checked: "не проверяется" }[rule.outcome] || "";
  const sec = el("section", { cls: "rule" }, [
    el("h4", { cls: "rule__title" }, [
      document.createTextNode(`${rule.rule_id} ${rule.title}`),
      outcomeText ? el("span", { cls: "rule__outcome", text: ` — ${outcomeText}` }) : null,
    ]),
  ]);
  if (rule.outcome === "not_run" && rule.skipped_reason) {
    sec.append(el("p", { cls: "muted", text: rule.skipped_reason }));
  }
  if (rule.findings.length) {
    const ul = el("ul", { cls: "findings" });
    for (const f of rule.findings) ul.append(renderFinding(f, layout));
    sec.append(ul);
  }
  return sec;
}

function renderStructure(nodes) {
  const ul = el("ul", { cls: "tree" });
  for (const n of nodes || []) {
    const label = [n.number, n.title].filter(Boolean).join(" ");
    const li = el("li", {}, [
      el("span", { text: label }),
      el("span", { cls: "muted", text: ` (${n.kind}, ${n.detection}, ${Math.round((n.confidence ?? 0) * 100)}%)` }),
    ]);
    if ((n.children || []).length) li.append(renderStructure(n.children));
    ul.append(li);
  }
  return ul;
}

function renderHeader(r) {
  const header = el("header", { cls: "rv-header" }, [
    el("h1", { text: `Отчёт о проверке: ${r.file.name}` }),
    el("p", { cls: "muted", text: `Версия сервиса ${r.service_version}; проверено ${r.checked_at}` }),
    el("p", { text: volumeNote(r.volume) }),
  ]);
  const note = layoutNote(r.layout);
  if (note) header.append(el("p", { cls: `note note--${r.layout.status}`, text: note }));
  for (const w of r.warnings || []) header.append(el("p", { cls: "note", text: w }));
  return header;
}

function renderSummary(r) {
  const s = r.summary;
  const items = [
    ["violation", s.violation], ["suspicion", s.suspicion],
    ["not_run", s.not_run], ["not_checked", s.not_checked],
  ];
  const ul = el("ul", { cls: "summary" });
  for (const [k, n] of items) {
    ul.append(el("li", {}, [el("span", { cls: `badge badge--${k}`, text: LEVEL_LABELS[k] }), el("strong", { text: ` ${n}` })]));
  }
  const box = el("section", { cls: "rv-summary", attrs: { "aria-label": "Сводка" } }, [ul]);
  box.append(el("p", { cls: "muted", text: `Пройдено правил: ${s.passed_rules.length}` }));
  if (s.noise_warning) box.append(el("p", { cls: "note", text: s.noise_warning }));
  return box;
}

function renderNotChecked(items) {
  if (!items || !items.length) return null;
  const ul = el("ul", { cls: "nc" });
  for (const it of items) {
    const li = el("li", {}, [el("strong", { text: `${it.id} ${it.title}` }), el("span", { cls: "muted", text: ` — ${it.source}` })]);
    if (it.hint) li.append(el("p", { text: it.hint }));
    ul.append(li);
  }
  return el("section", { attrs: { id: "not-checked" } }, [el("h2", { text: "Не проверяется автоматически" }), ul]);
}

export function renderReport(report, root) {
  const filters = new Set(["violation", "suspicion", "not_run"]);
  let showPassed = false;
  root.replaceChildren();

  const results = el("div", { attrs: { id: "rv-blocks" } });
  const redraw = () => {
    results.replaceChildren();
    const blocks = filterBlocks(report.blocks, filters, showPassed);
    if (!blocks.length) {
      results.append(el("p", { cls: "empty", text: "Нет находок с выбранными фильтрами." }));
    }
    for (const b of blocks) {
      const sec = el("section", { cls: "block" }, [el("h2", { text: b.title })]);
      for (const rule of b.rule_results) sec.append(renderRule(rule, report.layout));
      results.append(sec);
    }
  };

  const bar = el("fieldset", { cls: "filters" }, [el("legend", { text: "Показывать" })]);
  const addToggle = (labelText, checked, onChange) => {
    const input = el("input", { attrs: { type: "checkbox" } });
    input.checked = checked;
    input.addEventListener("change", () => { onChange(input.checked); redraw(); });
    bar.append(el("label", { cls: "filters__item" }, [input, document.createTextNode(` ${labelText}`)]));
  };
  for (const k of FILTER_KEYS) {
    addToggle(LEVEL_LABELS[k], filters.has(k), (on) => (on ? filters.add(k) : filters.delete(k)));
  }
  addToggle("Пройденные правила", false, (on) => { showPassed = on; });

  const structure = el("details", { cls: "structure" }, [
    el("summary", { text: "Распознанная структура" }),
    report.structure.length ? renderStructure(report.structure) : el("p", { cls: "muted", text: "Структура не распознана." }),
  ]);

  root.append(renderHeader(report), renderSummary(report), bar, results, structure, renderNotChecked(report.not_checked));
  redraw();
}

/** Для report_viewer.html: читает JSON из <script id="report-data">. */
export function renderFromDocument(doc = document) {
  const root = doc.getElementById("rv-root");
  const data = doc.getElementById("report-data");
  if (!data || !data.textContent.trim()) {
    root.textContent = "Данные отчёта не найдены.";
    return;
  }
  try {
    renderReport(JSON.parse(data.textContent), root);
  } catch {
    root.textContent = "Не удалось прочитать данные отчёта.";
  }
}
