// Логика экрана загрузки без DOM (F-03).
import { validateDocx } from "./limits.js";

export const MODES = { check: "check", compare: "compare" };

/** Проверка выбранных файлов для режима. Возвращает {slotName: текст ошибки|null} и ok. */
export function validateSelection(mode, files, limits) {
  const slots = mode === MODES.compare ? ["old", "new"] : ["file"];
  const errors = {};
  let ok = true;
  for (const s of slots) {
    errors[s] = validateDocx(files[s], limits);
    if (errors[s]) ok = false;
  }
  return { ok, errors, slots };
}

/** Из FileList/DataTransfer берёт первый файл; больше одного - не ошибка, лишние игнорируются. */
export function firstFile(list) {
  return list && list.length ? list[0] : null;
}

/** "75" -> "1 мин 15 с"; меньше минуты - "42 с". */
export function formatElapsed(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  return s < 60 ? `${s} с` : `${Math.floor(s / 60)} мин ${s % 60} с`;
}

export function progressText(mode, elapsedS, limits) {
  const ref = mode === MODES.compare ? limits.compare_timeout_s : limits.check_timeout_s;
  return `Идёт ${mode === MODES.compare ? "сравнение" : "проверка"}: ${formatElapsed(elapsedS)}. ` +
    `Ориентир по времени: до ${ref} с.`;
}

/**
 * Выполняет action; при 401 просит войти (requestLogin) и повторяет ровно один раз.
 * Если requestLogin вернул false (вход отменён) - пробрасывает исходную ошибку.
 */
export async function withAuthRetry(action, requestLogin) {
  try {
    return await action();
  } catch (e) {
    if (e && e.status === 401 && (await requestLogin())) return action();
    throw e;
  }
}

export function isAbort(e) {
  return !!e && e.name === "AbortError";
}

/** Для CompareReport берём new-отчёт: дифф рисуется отдельной задачей. */
export function reportFromResponse(mode, data) {
  return mode === MODES.compare ? data.new : data;
}
