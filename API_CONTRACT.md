# API_CONTRACT: vkr-checker (MVP)

Версия 1.0, 2026-10-19. **Источник истины — [api/openapi.yaml](api/openapi.yaml) (OpenAPI 3.1).** Этот файл объясняет поведение, которое схема выразить не может. Если они расходятся, прав openapi.yaml, а этот файл нужно исправить. Модели отчёта описаны в ARCHITECTURE_CHECKS.md §1, §7 и §8, конфигурация — в ARCHITECTURE.md §2.

## 1. Общие правила

- Протокол: REST/JSON по HTTP, один origin. FastAPI отдаёт и API (`/api/*`), и статику фронтенда (`/`, `/app.js`, `/styles.css`, `/report_viewer.html`). CORS не нужен и не включается.
- Кодировка UTF-8. Все тексты для пользователя (`message`, `title`, `hint`) на русском. Даты в ISO 8601 UTC.
- Нумерация везде с 1: `paragraph_idx`, `table_idx`, `row`, `col`, `page`.
- Обработка синхронная: ответ содержит готовый отчёт. Очередей, job-id и хранилища нет. Сервер не сохраняет ни файлы, ни отчёты (решение заказчика §0 п.4).
- Детерминизм: при одинаковом входе ответ совпадает побайтно, кроме `checked_at`. На этом стоят golden-тесты.
- Сбой вёрстки LibreOffice **не является ошибкой HTTP**. Ответ 200, `layout.status = "failed"`, причина в `layout.reason`, объём получен оценкой (`volume.method = "estimate"`).
- Ошибка одного правила тоже не ошибка HTTP. Правило получает `outcome = "not_run"` и `skipped_reason`.
- В каждом ответе есть заголовок `X-Request-Id`. В ошибке он же продублирован в `error.request_id`. В логах только он, без содержимого работы.

## 2. Эндпоинты

| Метод и путь | Авторизация | Назначение |
|---|---|---|
| `GET /api/health` | нет | состояние, режим, `layout_available`, лимиты для UI |
| `POST /api/session` | нет | вход по общему паролю, ставит cookie |
| `DELETE /api/session` | нет | выход, стирает cookie |
| `POST /api/check` | да* | проверка одного .docx, возвращает `CheckReport` |
| `POST /api/compare` | да* | сравнение двух версий, возвращает `CompareReport` |
| `POST /api/export/matrix.xlsx` | да* | .xlsx матрицы из присланного JSON |

\* «да» означает только server-режим. В local-режиме авторизации нет.

### 2.1. `GET /api/health`
Ответ `Health`: `mode`, `auth_required`, `authenticated`, `layout_available`, `layout_engine` («LibreOffice 24.2…» | null), `limits.{max_upload_mb, check_timeout_s, compare_timeout_s}`. Фронтенд вызывает его при загрузке страницы и по ответу решает:
- если `auth_required && !authenticated`, показать форму пароля;
- если `!layout_available`, показать баннер «LibreOffice не найден: объём оценивается по тексту, часть проверок по страницам не выполняется»;
- лимит размера файла для проверки на клиенте до отправки берётся из `limits`.

Health используется и как HEALTHCHECK в Docker, поэтому он всегда 200, пока процесс жив.

### 2.2. `POST /api/session` / `DELETE /api/session`
Тело `{"password": "..."}`. Поведение описано в §3.

### 2.3. `POST /api/check`
- `multipart/form-data`, поле `file` (ровно одно). Имя файла в ответе — только basename, обрезанный до 200 символов.
- 200: `CheckReport`. Блоки идут в порядке SPEC §3.4. `blocks[].rule_results` содержат все правила реестра, включая `passed`, чтобы UI показал «пройдено».
- Ориентир по времени: ≤ 30 с (SPEC §5). Жёсткий таймаут `limits.check_timeout_s` (по умолчанию 90 с), после него ответ 503 `processing_timeout`.

### 2.4. `POST /api/compare`
- `multipart/form-data`, поля `old` и `new`. Каждый файл проходит те же проверки, что в `/api/check`. В ошибке `error.field` указывает, какой из двух файлов плохой.
- 200: `CompareReport`. В нём `new` — полный `CheckReport` новой версии, `old` — только `file`, `layout`, `summary` (полный отчёт по старой версии не возвращается, этого хватает для DIF-06), `diff` — `DiffReport` (DIF-01…06).
- Связь diff с отчётом: `ParagraphDiff.old_idx/new_idx` — это `paragraph_idx` соответствующей версии. `moved_out`/`moved_in` ссылаются на `Move.id` через `move_id`. Находки DIF-05 лежат в `diff.impact` с `block = "diff_impact"` и `rule_id` вида `DIF-05.1…DIF-05.6`. `locations[0]` — место правки, остальные — места без синхронизации.
- Если одинаковы `sha256` обоих файлов, ответ всё равно 200. Все разделы `unchanged`, в `new.warnings` запись «файлы идентичны».
- Ориентир ≤ 60 с, жёсткий таймаут `limits.compare_timeout_s` (по умолчанию 150 с).

### 2.5. `POST /api/export/matrix.xlsx`
- Тело `MatrixExportRequest`: `file_name`, `matrix` (ровно `CheckReport.matrix` из ответа) и необязательные `service_version`, `checked_at` для шапки листа.
- 200: бинарный .xlsx, `Content-Disposition: attachment; filename*=UTF-8''<file_name без .docx>_матрица.xlsx`. Формат листов описан в ARCHITECTURE_CHECKS.md §7.
- Невалидный JSON или несоответствие схеме дают 422 `validation_error`, в `field` путь до поля. Лимит тела 5 МБ.

### 2.6. Скачивание отчёта (UI-02, US-20) — без эндпоинта
HTML-отчёт собирает фронтенд: берёт `/report_viewer.html`, вшивает JSON ответа в `<script type="application/json" id="report-data">` и скачивает Blob `<имя>_отчёт.html`. Тот же viewer рендерит отчёт и на странице. Обратно на сервер отчёт не отправляется. Защита от XSS: при вшивании каждый символ `<` в JSON заменяется на юникод-эскейп (кодовая точка U+003C), а viewer вставляет тексты только через `textContent`, никогда через `innerHTML`.

## 3. Авторизация (server-режим, общий пароль)

- В local-режиме (`VKR_MODE=local`, bind 127.0.0.1) все эндпоинты открыты, `auth_required=false`. `POST /api/session` возвращает 204 без cookie.
- В server-режиме защищены `/api/check`, `/api/compare`, `/api/export/*`. Статика и `/api/health` открыты, но в статике нет данных.
- Запрос принимается, если выполнено одно из двух условий:
  1. есть cookie `vkr_session`, выданная `POST /api/session`: `HttpOnly; Secure; SameSite=Strict; Path=/api; Max-Age = VKR_SESSION_TTL_H·3600` (по умолчанию 12 ч);
  2. есть заголовок `Authorization: Bearer <VKR_PASSWORD>`. Он для скриптов и QA (schemathesis), фронтенд его не использует.
- Токен сессии без состояния на сервере: `<exp>.<hmac_sha256(K, exp)>`, где `K = HMAC(VKR_PASSWORD, boot_secret)`, а `boot_secret` — случайные 32 байта при старте. После рестарта сервиса или смены пароля все сессии становятся недействительны. Это осознанное решение: хранилища нет.
- Пароль сравнивается через `hmac.compare_digest`, в логи не пишется ни он, ни токен.
- Подбор пароля ограничен: не больше `VKR_LOGIN_RATE_PER_MIN` (по умолчанию 5) неудачных попыток в минуту на IP, сверх лимита ответ 429 `too_many_attempts` с `Retry-After`. Счётчик хранится в памяти процесса. IP берётся из `X-Forwarded-For` только при `VKR_TRUST_PROXY=1`.
- CSRF: cookie `SameSite=Strict` не уходит с чужих сайтов, CORS выключен (ответ чужому origin не читается). Отдельного CSRF-заголовка в MVP нет. Если появится вход с других доменов — пересмотреть.
- Без авторизации ответ 401 `auth_required`, при неверном пароле на `/api/session` — 401 `invalid_password`. Получив 401 на защищённом эндпоинте, фронтенд показывает форму пароля и повторяет запрос.
- TLS терминирует обратный прокси. Сервис в server-режиме без `VKR_PASSWORD` не стартует (ARCHITECTURE.md §2.1).

## 4. Лимиты

| Лимит | Значение по умолчанию | Переменная | Ошибка |
|---|---|---|---|
| размер одного .docx | 20 МБ | `VKR_MAX_UPLOAD_MB` | 413 `file_too_large` |
| тело запроса `/api/check` / `/api/compare` | 1×/2× лимита файла + 1 МБ | производное | 413 `file_too_large` |
| тело `/api/export/matrix.xlsx` | 5 МБ | `VKR_MAX_JSON_MB` | 413 `file_too_large` |
| распакованный размер / число записей zip | 200 МБ / 2000 | `VKR_MAX_UNZIPPED_MB` / `VKR_MAX_ZIP_ENTRIES` | 422 `docx_limits_exceeded` |
| одновременные проверки (check = 1, compare = 2 слота) | 2 слота | `VKR_MAX_CONCURRENT_JOBS` | ожидание слота ≤ 30 с, иначе 503 `server_busy` + `Retry-After` |
| таймаут check / compare | 90 / 150 с | `VKR_CHECK_TIMEOUT_S` / `VKR_COMPARE_TIMEOUT_S` | 503 `processing_timeout` |
| вёрстка одного документа | 20 с | `VKR_LAYOUT_TIMEOUT_S` | не ошибка: откат, `layout.status=failed` |

Размер проверяется потоково при приёме, без чтения всего тела в память. Прокси должен ставить такой же лимит (`client_max_body_size` ≥ 41 МБ). Новые переменные (`VKR_SESSION_TTL_H`, `VKR_LOGIN_RATE_PER_MIN`, `VKR_TRUST_PROXY`, `VKR_MAX_JSON_MB`, `VKR_MAX_CONCURRENT_JOBS`, `VKR_CHECK_TIMEOUT_S`, `VKR_COMPARE_TIMEOUT_S`) дополняют таблицу ARCHITECTURE.md §2.2.

## 5. Ошибки

Единый формат для всех кодов, кроме 2xx:
```json
{"error": {"code": "invalid_docx", "message": "Файл повреждён или не является документом Word (.docx).", "field": "new", "request_id": "…"}}
```
FastAPI-ответ по умолчанию `{"detail": …}` подменяется обработчиками в `web/errors.py`, включая `RequestValidationError`.

| HTTP | `code` | Когда | Что показывает UI (UI-01) |
|---|---|---|---|
| 400 | `missing_file` | нет поля `file`/`old`/`new` или файл пустой | «Выберите файл .docx» |
| 400 | `bad_request` | не multipart, лишние файлы | общее сообщение |
| 401 | `auth_required` | нет или истекла сессия | форма пароля |
| 401 | `invalid_password` | неверный пароль | «Неверный пароль» |
| 413 | `file_too_large` | превышен лимит из §4 | «Файл больше N МБ» |
| 415 | `unsupported_format` | сигнатура не zip (.doc, .pdf, .rtf) или zip без `word/document.xml` (.odt, .xlsx) | «Нужен .docx; сохраните документ в Word как .docx» |
| 422 | `invalid_docx` | zip/XML повреждён, документ зашифрован паролем, нет тела | `message` с сервера |
| 422 | `docx_limits_exceeded` | подозрение на zip-бомбу, слишком много записей | `message` с сервера |
| 422 | `validation_error` | тело export или `/api/session` не по схеме | общее сообщение |
| 429 | `too_many_attempts` | превышен лимит попыток входа | «Подождите N с» |
| 500 | `internal_error` | непойманная ошибка конвейера (парсинг упал целиком) | «Не удалось обработать файл, код запроса …» |
| 503 | `server_busy` | нет свободного слота | «Сервис занят, повторите через N с» |
| 503 | `processing_timeout` | превышен таймаут обработки | «Файл обрабатывался слишком долго» |

Тексты `message` не содержат трассировок, путей и фрагментов работы. UI показывает `message` как есть, а для 401/413/415/429/503 может подставлять свой текст.

## 6. Ключевые формы ответа (кратко; полностью — openapi.yaml)

- `CheckReport` = `schema_version "1.0"`, `service_version`, `checked_at`, `file{name,size_bytes,sha256}`, `layout{status,engine,page_count,coverage,reason,font_substitutions,disclaimer}`, `volume{method,pages_main,by_section,estimate_formula}`, `structure[StructureNode]`, `summary{violation,suspicion,not_checked,not_run,passed_rules,noise_warning}`, `blocks[{id,title,rule_results[RuleResult]}]`, `not_checked[NcItem]`, `matrix`, `warnings[]`.
- `Finding` — как в ARCHITECTURE_CHECKS.md §1. Для UI важно:
  - `not_run=true` показывается как «Проверка не выполнена» с уровнем `suspicion`;
  - при `count>1` в `locations` не больше 5 мест, полный список в `values.all_cells`;
  - `Location.page` показывается только при `layout.status="ok"`, с подписью «≈ по вёрстке LibreOffice».
- `values` и `artifacts` в схеме — свободные объекты (`additionalProperties: true`). Фронтенд обязан отрисовать находку только по `message`/`locations` и не должен зависеть от ключей `values`. Исключение — известные artifacts, которые UI рисует таблицами: INT-01 `elements`, VOL-01 `by_section`, TSK-01 `task_map`, CON-01 `numbers_index`. Если их нет, UI просто не показывает таблицу.
- Счётчики `summary` считаются по находкам после схлопывания: одна схлопнутая находка = 1. Пункты NC-01 входят в `not_checked`.
- Совместимость: изменение формы отчёта означает новую `schema_version` и правку openapi.yaml в том же PR. Новые необязательные поля допустимы без смены версии, и фронтенд игнорирует неизвестные поля.

## 7. Как проверяется соответствие (для QA и разработчиков)

- **Backend:** `tests/contract/test_openapi.py`. (1) Схема `app.openapi()`, сгенерированная FastAPI, сравнивается с api/openapi.yaml на уровне путей, методов, кодов ответов и имён компонентов (`openapi-spec-validator` + сравнение нормализованных JSON). (2) `schemathesis run api/openapi.yaml --base-url http://127.0.0.1:8000 --checks all` против запущенного сервиса (local-режим; для server-режима добавить `-H "Authorization: Bearer …"`). Для multipart синтетические .docx из `tests/fixtures/generated` подставляются через хук schemathesis.
- **Golden-ответы:** JSON отчётов синтетических работ валидируются по `#/components/schemas/CheckReport` и `CompareReport` (`jsonschema`, draft 2020-12).
- **Frontend:** разрабатывается против мок-сервера `prism mock api/openapi.yaml` плюс фикстур `tests/golden/*.json`, которые валидны по схеме. Это позволяет начинать параллельно с backend.
- Первая версия openapi.yaml пишется вручную (этот шаг). Pydantic-модели backend повторяют её (имена схем = имена классов), а не наоборот.
