// Сборка самодостаточного HTML-отчёта (API_CONTRACT §2.6). Без сети и DOM — тестируется напрямую.

/** JSON для вставки в <script>: каждый "<" -> <, а также U+2028/2029. */
export function escapeJsonForScript(report) {
  return JSON.stringify(report)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

/** Превращает ES-модуль в фрагмент классического скрипта: убирает import и export. */
export function stripModuleSyntax(source) {
  return source
    .replace(/^\s*import\s+[\s\S]*?\sfrom\s+["'][^"']+["'];?\s*$/gm, "")
    .replace(/^export\s+(?=(async\s+)?(function|const|let|class)\b)/gm, "");
}

function escapeHtml(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** assets: { css, logicJs, artifactsJs, viewerJs } - исходные тексты файлов. */
export function buildStandaloneHtml(report, assets) {
  const code = [stripModuleSyntax(assets.logicJs), stripModuleSyntax(assets.artifactsJs), stripModuleSyntax(assets.viewerJs), "renderFromDocument();"].join("\n");
  if (/<\/script/i.test(code)) throw new Error("Код viewer содержит </script");
  const css = assets.css.replace(/<\/style/gi, "<\\/style");
  const title = `Отчёт о проверке ВКР: ${(report.file && report.file.name) || ""}`;
  return `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>
${css}
</style>
</head>
<body>
<div id="rv-root" role="main"></div>
<script type="application/json" id="report-data">${escapeJsonForScript(report)}</script>
<script>
${code}
</script>
</body>
</html>
`;
}

function safeBase(docxName) {
  return String(docxName || "").replace(/\.docx$/i, "").replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").trim() || "report";
}

/** "Курсовая.docx" -> "Курсовая_отчёт.docx" (сравнение -> "_сравнение.docx"). */
export function reportDocxFileName(docxName, compare) {
  return `${safeBase(docxName)}_${compare ? "сравнение" : "отчёт"}.docx`;
}

/** "Курсовая.docx" -> "Курсовая_отчёт.html"; символы, опасные для имени файла, заменяются. */
export function reportFileName(docxName) {
  const base = String(docxName || "").replace(/\.docx$/i, "").replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").trim();
  return `${base || "report"}_отчёт.html`;
}
