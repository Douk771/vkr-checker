// Решения по ответу /api/health (API_CONTRACT §2.1).

export const LAYOUT_BANNER_TEXT =
  "LibreOffice не найден: объём оценивается по тексту, часть проверок по страницам не выполняется.";

/** Чистая функция: что показать на старте. */
export function interpretHealth(health) {
  return {
    needLogin: Boolean(health.auth_required && !health.authenticated),
    showLayoutBanner: !health.layout_available,
    limits: health.limits,
    layoutEngine: health.layout_engine || null,
  };
}
