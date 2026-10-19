// Разбор ошибок API (API_CONTRACT §5) и тексты для пользователя (UI-01).

export class ApiError extends Error {
  constructor({ status, code, message, field = null, requestId = null, retryAfter = null }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.field = field;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

/** Преобразует ответ с ошибкой в ApiError. Устойчив к не-JSON телу (прокси, 502). */
export async function parseErrorResponse(response) {
  const headerId = response.headers.get("X-Request-Id");
  const retry = parseInt(response.headers.get("Retry-After") || "", 10);
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const err = body && typeof body === "object" ? body.error : null;
  if (err && typeof err === "object") {
    return new ApiError({
      status: response.status,
      code: err.code || "unknown",
      message: err.message || "",
      field: err.field ?? null,
      requestId: err.request_id || headerId,
      retryAfter: Number.isFinite(retry) ? retry : null,
    });
  }
  return new ApiError({
    status: response.status,
    code: "unknown",
    message: "",
    requestId: headerId,
    retryAfter: Number.isFinite(retry) ? retry : null,
  });
}

/** Текст для UI по таблице API_CONTRACT §5. maxUploadMb нужен для file_too_large. */
export function userMessage(err, { maxUploadMb = null } = {}) {
  if (!(err instanceof ApiError)) {
    return "Нет связи с сервисом. Проверьте, что он запущен, и повторите.";
  }
  const wait = err.retryAfter;
  switch (err.code) {
    case "missing_file":
      return "Выберите файл .docx";
    case "auth_required":
      return "Нужно войти по паролю";
    case "invalid_password":
      return "Неверный пароль";
    case "file_too_large":
      return maxUploadMb ? `Файл больше ${maxUploadMb} МБ` : "Файл слишком большой";
    case "unsupported_format":
      return "Нужен .docx; сохраните документ в Word как .docx";
    case "invalid_docx":
    case "docx_limits_exceeded":
      return err.message || "Файл не удалось прочитать как документ Word (.docx).";
    case "too_many_attempts":
      return wait ? `Подождите ${wait} с` : "Слишком много попыток, подождите немного";
    case "server_busy":
      return wait ? `Сервис занят, повторите через ${wait} с` : "Сервис занят, повторите позже";
    case "processing_timeout":
      return "Файл обрабатывался слишком долго";
    case "internal_error":
      return withRequestId("Не удалось обработать файл", err.requestId);
    case "validation_error":
    case "bad_request":
      return err.message || "Некорректный запрос";
    default:
      return withRequestId(err.message || "Неожиданная ошибка сервиса", err.requestId);
  }
}

function withRequestId(text, requestId) {
  return requestId ? `${text}, код запроса ${requestId}` : text;
}
