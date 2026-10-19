// UI загрузки (F-03) и показ отчёта со скачиванием (F-14). Логика - в upload_logic.js.
import { userMessage } from "./errors.js";
import { validateDocx } from "./limits.js";
import { MODES, validateSelection, firstFile, progressText, withAuthRetry, isAbort, reportFromResponse } from "./upload_logic.js";
import { buildStandaloneHtml, reportFileName } from "./download.js";
import { buildExportPayload } from "./artifacts.js";
import { renderReport } from "/viewer.js";

const $ = (id) => document.getElementById(id);
const LABELS = { check: "Проверить", compare: "Сравнить" };

export function initUpload(state, { requestLogin, cancelLoginWait }) {
  const form = $("upload-form");
  const files = {};
  let mode = MODES.check;
  let controller = null;
  let timer = null;
  let lastReport = null;

  const slotEl = (slot) => form.querySelector(`[data-slot="${slot}"]`);
  const errEl = (slot) => form.querySelector(`[data-error="${slot}"]`);

  function showErrors(errors) {
    for (const [slot, text] of Object.entries(errors)) {
      errEl(slot).textContent = text || "";
      errEl(slot).hidden = !text;
    }
  }

  function setMode(next) {
    mode = next;
    for (const s of ["file", "old", "new"]) slotEl(s).hidden = (next === MODES.compare) === (s === "file");
    $("run-btn").textContent = LABELS[next];
    showErrors({ file: "", old: "", new: "" });
    $("run-error").hidden = true;
  }

  function setFile(slot, file) {
    files[slot] = file;
    showErrors({ [slot]: file ? validateDocx(file, state.limits) : "" });
  }

  for (const radio of document.querySelectorAll('input[name="mode"]')) {
    radio.addEventListener("change", () => radio.checked && setMode(radio.value));
  }
  for (const slot of ["file", "old", "new"]) {
    const box = slotEl(slot);
    const input = box.querySelector("input[type=file]");
    input.addEventListener("change", () => setFile(slot, firstFile(input.files)));
    box.addEventListener("dragover", (e) => { e.preventDefault(); box.classList.add("drop--over"); });
    box.addEventListener("dragleave", () => box.classList.remove("drop--over"));
    box.addEventListener("drop", (e) => {
      e.preventDefault();
      box.classList.remove("drop--over");
      const f = firstFile(e.dataTransfer && e.dataTransfer.files);
      if (f) setFile(slot, f);
    });
  }

  function setBusy(busy) {
    $("run-btn").disabled = busy;
    $("cancel-btn").hidden = !busy;
    for (const i of form.querySelectorAll("input[type=file]")) i.disabled = busy;
    $("progress").hidden = !busy;
    clearInterval(timer);
    if (busy) {
      const started = Date.now();
      const tick = () => { $("progress").textContent = progressText(mode, (Date.now() - started) / 1000, state.limits); };
      tick();
      timer = setInterval(tick, 1000);
    }
  }

  async function run(event) {
    event.preventDefault();
    $("run-error").hidden = true;
    const sel = validateSelection(mode, files, state.limits);
    showErrors(sel.errors);
    if (!sel.ok) return;

    controller = new AbortController();
    const { signal } = controller;
    const action = () => (mode === MODES.compare
      ? state.api.compare(files.old, files.new, { signal })
      : state.api.check(files.file, { signal }));
    setBusy(true);
    try {
      const data = await withAuthRetry(action, () => requestLogin(signal));
      showReport(reportFromResponse(mode, data));
    } catch (e) {
      if (isAbort(e)) {
        $("run-error").textContent = "Отменено";
      } else {
        $("run-error").textContent = userMessage(e);
      }
      $("run-error").hidden = false;
    } finally {
      setBusy(false);
      controller = null;
    }
  }

  function showReport(report) {
    lastReport = report;
    $("result").hidden = false;
    $("download-status").textContent = "";
    renderReport(report, $("rv-root"), {
      onExportMatrix: async () => {
        try {
          const blob = await state.api.exportMatrix(buildExportPayload(report));
          saveBlob(blob, `${report.file.name.replace(/\.docx$/i, "")}_матрица.xlsx`);
        } catch (e) {
          const err = new Error(userMessage(e));
          err.userMessage = err.message;
          throw err;
        }
      },
    });
    $("result").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function download() {
    if (!lastReport) return;
    const status = $("download-status");
    $("download-btn").disabled = true;
    status.textContent = "Формируется…";
    try {
      const [css, logicJs, artifactsJs, viewerJs] = await Promise.all(
        ["/viewer.css", "/viewer_logic.js", "/js/artifacts.js", "/viewer.js"].map(async (u) => {
          const r = await fetch(u);
          if (!r.ok) throw new Error(u);
          return r.text();
        }));
      const html = buildStandaloneHtml(lastReport, { css, logicJs, artifactsJs, viewerJs });
      saveBlob(new Blob([html], { type: "text/html;charset=utf-8" }), reportFileName(lastReport.file.name));
      status.textContent = "";
    } catch {
      status.textContent = "Не удалось собрать файл отчёта. Попробуйте ещё раз.";
    } finally {
      $("download-btn").disabled = false;
    }
  }

  function saveBlob(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  form.addEventListener("submit", run);
  $("cancel-btn").addEventListener("click", () => { if (controller) controller.abort(); cancelLoginWait(); });
  $("download-btn").addEventListener("click", download);
}
