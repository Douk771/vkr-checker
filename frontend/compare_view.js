// Рендер CompareReport.diff. Любой текст из отчёта попадает в DOM только через textContent.
import {
  SECTION_LABELS, PARA_LABELS, OBJECT_LABELS, FLAG_LABELS, isCollapsedSection, sectionTitle, sectionStats,
  groupParagraphs, normalizeSegments, indexMoves, moveLabel, cellRef, objectTitle, rowLabel, dynamicsLine,
  diffSummary, isEmptyDiff,
} from "./compare_logic.js";
import { renderFinding, renderReport } from "./viewer.js";
import { pageLabel } from "./viewer_logic.js";

function el(tag, { cls, text, attrs } = {}, children = []) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  for (const c of children) if (c) node.append(c);
  return node;
}

function renderSegments(segments, tag = "p") {
  const p = el(tag, { cls: "diff__text" });
  for (const s of normalizeSegments(segments)) {
    if (s.op === "equal") p.append(document.createTextNode(s.text));
    else p.append(el(s.op, { cls: `seg seg--${s.op}`, text: s.text, attrs: { "data-mark": s.op === "ins" ? "добавлено" : "удалено" } }));
  }
  return p;
}

function paraNode(p, moves) {
  const hasSeg = (p.segments || []).length > 0;
  const li = el("li", { cls: `para para--${p.status}` });
  const idx = [p.old_idx != null ? `было ${p.old_idx}` : null, p.new_idx != null ? `стало ${p.new_idx}` : null].filter(Boolean).join(", ");
  li.append(el("span", { cls: "badge badge--diff", text: PARA_LABELS[p.status] || p.status }));
  if (idx) li.append(el("span", { cls: "muted", text: ` абзац: ${idx}` }));
  if (p.move_id) {
    const m = moves.get(p.move_id);
    li.append(el("span", { cls: "muted", text: m ? ` (${moveLabel(m)}, связка ${p.move_id})` : ` (связка ${p.move_id})` }));
  }
  if (hasSeg) li.append(renderSegments(p.segments));
  else if (p.text) li.append(el("p", { cls: `diff__text${p.status === "deleted" ? " seg--del" : ""}`, text: p.text }));
  return li;
}

function sectionNode(s, moves) {
  const det = el("details", { cls: `dsec dsec--${s.status}` });
  if (s.status !== "unchanged") det.open = true;
  det.append(el("summary", {}, [
    el("span", { cls: "badge badge--diff", text: SECTION_LABELS[s.status] || s.status }),
    document.createTextNode(` ${sectionTitle(s)}`),
    s.status === "renamed" && s.rename_basis ? el("span", { cls: "muted", text: ` (по ${s.rename_basis === "title" ? "названию" : "содержанию"})` }) : null,
  ]));
  const ul = el("ul", { cls: "paras" });
  for (const g of groupParagraphs(s.paragraphs)) {
    if (g.kind === "para") ul.append(paraNode(g.para, moves));
    else ul.append(el("li", { cls: "muted", text: `Без изменений: ${g.items.length} абз.` }));
  }
  if (ul.children.length) det.append(ul);
  else det.append(el("p", { cls: "muted", text: "Изменений абзацев нет." }));
  return det;
}

function renderSections(diff, moves) {
  const sec = el("section", { attrs: { id: "cmp-sections" } }, [el("h2", { text: "Изменения по разделам" })]);
  const list = diff.sections || [];
  if (!list.length) { sec.append(el("p", { cls: "empty", text: "Разделы не сопоставлены." })); return sec; }
  const st = sectionStats(list);
  sec.append(el("p", { cls: "muted", text: `Разделов: ${st.total}; изменено: ${st.changed}; без изменений: ${st.collapsed}.` }));
  const collapsed = list.filter(isCollapsedSection);
  for (const s of list) if (!isCollapsedSection(s)) sec.append(sectionNode(s, moves));
  if (collapsed.length) {
    const d = el("details", { cls: "dsec dsec--unchanged-group" }, [el("summary", { text: `Разделы без изменений (${collapsed.length})` })]);
    const ul = el("ul", { cls: "paras" });
    for (const s of collapsed) ul.append(el("li", { text: sectionTitle(s) }));
    d.append(ul);
    sec.append(d);
  }
  return sec;
}

function renderMoves(diff) {
  const list = diff.moves || [];
  if (!list.length) return null;
  const sec = el("section", { attrs: { id: "cmp-moves" } }, [el("h2", { text: "Перенесённые фрагменты" })]);
  const ul = el("ul", { cls: "paras" });
  for (const m of list) {
    ul.append(el("li", { cls: "para" }, [
      el("span", { cls: "badge badge--diff", text: `связка ${m.id}` }),
      el("span", { cls: "muted", text: ` ${moveLabel(m)}; абзацы было ${m.old_idx.join(", ")}, стало ${m.new_idx.join(", ")}` }),
      renderSegments(m.segments),
    ]));
  }
  sec.append(ul);
  return sec;
}

function renderNumbers(diff, layout) {
  const list = diff.number_changes || [];
  const sec = el("section", { attrs: { id: "cmp-numbers" } }, [el("h2", { text: "Изменения чисел" })]);
  if (!list.length) { sec.append(el("p", { cls: "empty", text: "Изменений чисел не найдено." })); return sec; }
  const body = list.map((n) => {
    const loc = n.loc_new || n.loc_old;
    const place = loc ? [(loc.section_path || []).join(" › "), pageLabel(loc, layout)].filter(Boolean).join("; ") : "";
    return el("tr", {}, [el("td", { text: n.old }), el("td", { text: n.new }), el("td", { text: n.kind || "" }), el("td", { text: n.context }), el("td", { text: place })]);
  });
  const head = el("tr", {}, ["Было", "Стало", "Тип", "Контекст", "Место"].map((t) => el("th", { text: t, attrs: { scope: "col" } })));
  sec.append(el("div", { cls: "table-wrap" }, [el("table", { cls: "data" }, [el("thead", {}, [head]), el("tbody", {}, body)])]));
  return sec;
}

function renderObjects(title, id, list, emptyText) {
  const sec = el("section", { attrs: { id } }, [el("h2", { text: title })]);
  const changed = (list || []).filter((o) => o.status !== "unchanged");
  if (!changed.length) { sec.append(el("p", { cls: "empty", text: emptyText })); return sec; }
  const ul = el("ul", { cls: "paras" });
  for (const o of changed) {
    const li = el("li", { cls: "para" }, [
      el("span", { cls: "badge badge--diff", text: OBJECT_LABELS[o.status] || o.status }),
      el("strong", { text: ` ${objectTitle(o)}` }),
      ...(o.flags || []).map((f) => el("span", { cls: "muted", text: ` · ${FLAG_LABELS[f] || f}` })),
    ]);
    if ((o.rows || []).length) {
      const rl = el("ul", { cls: "rows" });
      for (const r of o.rows) {
        const cells = (r.cells || []).map(cellRef).join("; ");
        rl.append(el("li", { text: cells ? `${rowLabel(r)} — ${cells}` : rowLabel(r) }));
      }
      li.append(rl);
    }
    ul.append(li);
  }
  sec.append(ul);
  return sec;
}

function renderImpact(diff, layout) {
  const sec = el("section", { attrs: { id: "cmp-impact" } }, [el("h2", { text: "Влияние изменений на выводы" })]);
  const list = diff.impact || [];
  if (!list.length) { sec.append(el("p", { cls: "empty", text: "Расхождений с выводами не найдено." })); return sec; }
  const ul = el("ul", { cls: "findings" });
  for (const f of list) ul.append(renderFinding(f, layout));
  sec.append(ul);
  return sec;
}

function renderDynamics(diff) {
  const d = diff.dynamics;
  if (!d) return null;
  const groups = [["fixed", "Исправлено"], ["new", "Появилось"], ["remaining", "Осталось"]];
  const sec = el("section", { attrs: { id: "cmp-dynamics" } }, [el("h2", { text: "Динамика замечаний" })]);
  if (groups.every(([k]) => !(d[k] || []).length)) { sec.append(el("p", { cls: "empty", text: "Замечаний для сравнения нет." })); return sec; }
  for (const [k, title] of groups) {
    const items = d[k] || [];
    const det = el("details", { cls: "artifact" }, [el("summary", { text: `${title}: ${items.length}` })]);
    if (items.length) {
      const ul = el("ul", { cls: "paras" });
      for (const it of items) {
        ul.append(el("li", {}, [el("strong", { text: `${it.rule_id} ${it.title}` }), el("span", { cls: "muted", text: ` — ${dynamicsLine(it)}` }), el("div", { text: it.message })]));
      }
      det.append(ul);
      det.open = k !== "remaining";
    }
    sec.append(det);
  }
  return sec;
}

function renderOldInfo(old) {
  if (!old) return null;
  const s = old.summary || {};
  return el("p", { cls: "muted", text: `Старая версия: ${old.file.name}; нарушений ${s.violation ?? 0}, подозрений ${s.suspicion ?? 0}.` });
}

export function renderCompareDiff(compare, root) {
  root.replaceChildren();
  const diff = compare.diff || {};
  const sum = diffSummary(diff);
  const head = el("header", { cls: "rv-header" }, [
    el("h1", { text: `Сравнение версий: ${compare.old.file.name} → ${compare.new.file.name}` }),
    renderOldInfo(compare.old),
    el("p", { text: `Изменено разделов: ${sum.sectionsChanged}; переносов: ${sum.moves}; изменений чисел: ${sum.numbers}; таблиц: ${sum.tables}; рисунков: ${sum.figures}.` }),
  ]);
  root.append(head);
  if (isEmptyDiff(diff)) root.append(el("p", { cls: "empty", text: "Различий между версиями не найдено." }));
  const layout = compare.new.layout;
  for (const n of [renderSections(diff, indexMoves(diff.moves)), renderMoves(diff), renderNumbers(diff, layout),
    renderObjects("Таблицы", "cmp-tables", diff.tables, "Изменений таблиц нет."),
    renderObjects("Рисунки", "cmp-figures", diff.figures, "Изменений рисунков нет."),
    renderImpact(diff, layout), renderDynamics(diff)]) if (n) root.append(n);
}

/** Сначала дифф, затем полный отчёт новой версии тем же рендером. */
export function renderCompare(compare, diffRoot, reportRoot, opts) {
  renderCompareDiff(compare, diffRoot);
  renderReport(compare.new, reportRoot, opts);
}
