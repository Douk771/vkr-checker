// Клиентская проверка файла до отправки (сервер всё равно проверяет повторно).

const DEFAULT_MAX_MB = 20;

/** Возвращает текст ошибки или null, если файл годится. */
export function validateDocx(file, limits) {
  if (!file) return "Выберите файл .docx";
  const name = String(file.name || "");
  if (!/\.docx$/i.test(name)) {
    return "Нужен .docx; сохраните документ в Word как .docx";
  }
  if (!file.size) return "Выберите файл .docx";
  const maxMb = (limits && limits.max_upload_mb) || DEFAULT_MAX_MB;
  if (file.size > maxMb * 1024 * 1024) return `Файл больше ${maxMb} МБ`;
  return null;
}
