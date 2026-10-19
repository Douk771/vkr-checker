// Точка входа UI-01. Загрузка файлов и отчёты подключаются в F-03/F-14.
import { createApi } from "/js/api.js";
import { userMessage } from "/js/errors.js";
import { interpretHealth, LAYOUT_BANNER_TEXT } from "/js/health.js";

const api = createApi();
const $ = (id) => document.getElementById(id);

export const state = { health: null, limits: null, api };

function show(id, on) { $(id).hidden = !on; }

function applyHealth(health) {
  const view = interpretHealth(health);
  state.health = health;
  state.limits = view.limits;

  show("loading", false);
  show("startup-error", false);

  $("layout-banner").textContent = LAYOUT_BANNER_TEXT;
  show("layout-banner", view.showLayoutBanner);

  const info = $("engine-info");
  info.textContent = view.layoutEngine ? `Вёрстка: ${view.layoutEngine}` : "";
  info.hidden = !view.layoutEngine;

  show("login-panel", view.needLogin);
  show("workspace", !view.needLogin);
  $("limits-info").textContent =
    `Файл .docx до ${view.limits.max_upload_mb} МБ. ` +
    `Ориентир по времени: проверка до ${view.limits.check_timeout_s} с, сравнение до ${view.limits.compare_timeout_s} с.`;
  if (view.needLogin) $("password").focus();
}

async function start() {
  show("loading", true);
  show("startup-error", false);
  try {
    applyHealth(await api.getHealth());
  } catch (e) {
    show("loading", false);
    $("startup-error-text").textContent = userMessage(e);
    show("startup-error", true);
  }
}

async function onLogin(event) {
  event.preventDefault();
  const error = $("login-error");
  const password = $("password").value;
  error.hidden = true;
  if (!password) {
    error.textContent = "Введите пароль";
    error.hidden = false;
    return;
  }
  $("login-submit").disabled = true;
  try {
    await api.login(password);
    $("password").value = "";
    applyHealth(await api.getHealth());
  } catch (e) {
    error.textContent = userMessage(e);
    error.hidden = false;
  } finally {
    $("login-submit").disabled = false;
  }
}

$("login-form").addEventListener("submit", onLogin);
$("startup-retry").addEventListener("click", start);
start();
