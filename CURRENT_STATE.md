Актуально по состоянию на коммит: 5c768b0302304ebd991cdb7d063157b1fb969142, дата: 2026-10-20 (ветка `cycle/001-vkr-checker-mvp`)

# CURRENT_STATE: vkr-checker

Режим составления: полное сканирование (первый цикл, cycle/001). Описание составлено по коду, а не по документации. Там, где код и документы расходятся, это указано явно.

## 1. Назначение

Сервис детерминированной проверки (без LLM) магистерской ВКР (37.04.01 Психология) в формате `.docx` на соответствие методичке и чек-листу, а также сравнение двух версий работы. Веб-UI плюс HTTP API, один процесс. Режимы: `local` (без пароля, 127.0.0.1) и `server` (общий пароль).

## 2. Стек (по факту из файлов)

| Слой | Что используется | Источник |
|---|---|---|
| Язык backend | Python >=3.10 (ruff target py310; в Docker и CI 3.12) | `pyproject.toml`, `Dockerfile`, `.github/workflows/ci.yml` |
| Веб | FastAPI >=0.110, uvicorn >=0.29, python-multipart, Starlette StaticFiles (раздаёт `frontend/` с `/`) | `pyproject.toml`, `src/vkr_checker/main.py` |
| Модели и настройки | pydantic v2 (>=2.6), pydantic-settings (env-префикс `VKR_`, `.env`) | `config.py`, `report/schema.py` |
| Разбор .docx | python-docx >=1.1, lxml >=5.0 (безопасный парсер, свой обход XML) | `docx/` |
| Вёрстка (страницы) | внешний LibreOffice `soffice` (subprocess, конвертация в PDF) + pypdfium2 >=4.30 для текста PDF | `layout/soffice.py`, `layout/pdftext.py` |
| NLP | pymorphy3 + pymorphy3-dicts-ru, rapidfuzz | `nlp/`, `checks/facts/` |
| Экспорт | openpyxl (xlsx матрицы) | `matrix/xlsx.py` |
| Сборка пакета | hatchling, CLI-скрипт `vkr-checker = vkr_checker.main:run` | `pyproject.toml` |
| Менеджер пакетов | pip (`pip install -e ".[dev]"`) локально и в CI; `uv` в Dockerfile. **`uv.lock` отсутствует**: Dockerfile ставит по `pyproject.toml` без замка | `Dockerfile` |
| Dev-зависимости | pytest >=8, ruff >=0.4, jsonschema >=4.20, pyyaml >=6, httpx >=0.27 | `pyproject.toml [dev]` |
| Frontend | чистый JS (ES-модули, без фреймворка и без сборки), HTML/CSS. В `package.json` нет зависимостей, нет lock-файла | `frontend/` |
| Тесты frontend | встроенный `node --test` (Node 20 в CI) | `frontend/package.json` |
| СУБД | **нет**. Состояние не хранится: файлы обрабатываются во временном каталоге и удаляются; сессии stateless (HMAC-токен); rate limit входа в памяти процесса | `web/routes.py`, `web/auth.py` |
| Внешние сервисы | **нет** сетевых интеграций. Единственная внешняя зависимость среды выполнения — бинарник LibreOffice (необязателен: без него откат на оценку объёма) | `layout/soffice.py`, `pipeline.py` |
| Контейнер | `python:3.12-slim-bookworm` + `libreoffice-writer-nogui`, шрифты Liberation/Carlito/Caladea/DejaVu; non-root uid 10001; compose: read-only rootfs, tmpfs `/tmp`, cap_drop ALL, порт только на 127.0.0.1 | `Dockerfile`, `docker-compose.yml` |

Версия сервиса: `0.1.0` (`src/vkr_checker/__init__.py`), версия контракта API: `1.0.0` (`api/openapi.yaml`), `schema_version` отчёта: `"1.0"`.

## 3. Структура репозитория

```
src/vkr_checker/          backend (около 13 тыс. строк Python)
  main.py                 точка входа: create_app() + run() (uvicorn); монтирует frontend/ на "/"
  config.py               Settings (VKR_*), валидация режима
  thresholds.py           ВСЕ пороги эвристик (dataclass Thresholds, DEFAULT_THRESHOLDS)
  pipeline.py             CheckPipeline: check() / compare() / analyze() — оркестрация
  web/                    HTTP-слой (инфраструктура): routes, auth, errors, middleware, slots, upload, ports
  docx/                   разбор .docx: package (zip-лимиты, сигнатуры), xmlutil (безопасный lxml), reader,
                          styles/styleprops (каскад форматирования), numbering (автонумерация),
                          revisions/fields (рецензирование, поля SEQ), tableprops, drawings
  model/                  внутренняя модель документа (document.py, frozen dataclasses), location.py,
                          finding.py (Pydantic-модели Finding/RuleResult = схемы openapi)
  structure/              распознавание структуры: detector, patterns, toc, captions, bibliography, appendices
  layout/                 soffice (запуск LO), pdftext (pypdfium2), align (привязка к страницам),
                          estimate (оценка объёма), fonts, outcome (откат)
  nlp/                    предложения со смещениями, pymorphy3 с кэшем, нормализация, lexicons/methods.py
  checks/                 бизнес-логика проверок: base (Rule/Need/CheckContext), engine, registry,
                          модули правил (см. §4), facts/ (слой извлечения фактов из текста)
  diff/                   сравнение версий DIF-01..06: sections, paragraphs, words, moves, numbers,
                          tables, figures, impact*, dynamics, compare (сборка CompareReport)
  matrix/                 матрица связности MAT-01: build, cells, xlsx
  report/                 schema.py (все Pydantic-модели API), build.py (сборка CheckReport), collapse.py
frontend/                 UI: index.html + app.js (точка входа), js/ (api, upload, errors, health, limits,
                          artifacts, download), viewer*.js/css (отчёт), compare_*.js (сравнение),
                          report_viewer.html (шаблон скачиваемого офлайн-отчёта), dev_server.mjs,
                          tools/check_real.mjs, tests/
api/openapi.yaml          контракт API (OpenAPI 3.1, ручной, «источник истины»)
tests/                    unit/ (38 файлов), contract/, functional/, golden/*.json, fixtures/
scripts/                  build_fixtures.py, profile_pipeline.py, measure_layout.py, calibrate.py
```

Бизнес-логика: `checks/`, `checks/facts/`, `diff/`, `matrix/`, `structure/`, `nlp/`. Инфраструктура: `web/`, `main.py`, `config.py`, `layout/soffice.py`, `docx/package.py`, `Dockerfile`.

Конвейер (`pipeline.py`): `DocxPackage.open` (лимиты) -> параллельно: `read_document` + `analyze_structure` и `SofficeRunner.convert_to_pdf` -> `compute_layout` (или откат) -> `CheckContext.build` -> `run_rules(all_rules())` -> `build_matrix` (сбой матрицы не роняет проверку, `failed_matrix()`) -> `assemble_check_report`. `compare` гоняет `analyze` для двух файлов в 2 потоках, затем `build_compare_report`. HTTP-слой (`web/routes._run_job`): приём файлов во временный каталог, слоты (`SlotPool`, check = 1, compare = 2), выполнение в executor, таймаут -> 503, слот и каталог освобождаются только по фактическому завершению потока.

## 4. Что реализовано

Все задачи из `ARCHITECTURE_TASKS.md` (B-01..B-73, F-01..F-20, X-01/X-02) закрыты коммитами (см. `git log`). Набор правил, зарегистрированных в `checks/registry.py` (явный список модулей, порядок выполнения по `rule_id`):

| Блок | Правила | Модуль |
|---|---|---|
| structure | STR-01..06, PAGE-01 | `checks/structure.py` |
| tables | TBL-01..05, 07..09 | `checks/tables_format.py` |
| tables | TBL-06 | `checks/typography.py` |
| tables | TBL-10..12 | `checks/tables_place.py` |
| volume | VOL-01 | `checks/volume.py` |
| numbering | NUM-01..03 | `checks/numbering.py` |
| — | BIB-01 | `checks/bibliography.py` |
| intro | INT-01 | `checks/intro.py` |
| consistency | CON-01..04 | `checks/consistency.py` |
| methods | MET-01..04 | `checks/methods.py` |
| hypothesis | HYP-01 | `checks/hypothesis.py` (+ `checks/facts/hypothesis.py`) |
| wording | LEX-01..03 | `checks/lexical.py` |
| tasks | TSK-01 | `checks/tasks.py` |
| not_checked | NC-01 (список того, что кодом не проверяется) | `checks/not_checked.py` |
| diff_impact | DIF-05.1..6 (только в compare) | `diff/impact*.py` |

Сравнение версий: DIF-01 (разделы/абзацы/пословно), DIF-02 (перемещения), DIF-03 (числа), DIF-04 (таблицы/рисунки), DIF-05 (последствия правок), DIF-06 (динамика замечаний) — `diff/`. Матрица MAT-01 и экспорт xlsx — `matrix/`. Server-режим с авторизацией реализован в коде, но по решению заказчика (`ARCHITECTURE_TASKS.md` §8, п.6) в MVP разворачивается только local.

Заглушки / мёртвый код: TODO/FIXME в `src/`, `frontend/`, `tests/`, `scripts/` не найдено. `PENDING_PATHS` в `tests/contract/test_openapi.py` пуст (все эндпоинты из openapi реализованы). Слово «заглушка» в `diff/impact_base.py` относится к минимальному объекту-правилу `DifRule` для `new_finding`, а не к нереализованной функциональности. Прежняя заглушка API на golden-JSON удалена (коммит c48b042).

«Выглядит завершённым, но автотестов нет»:
- DOM-рендеринг и взаимодействие UI (`frontend/app.js`, `js/upload.js`, `viewer.js`, `compare_view.js`): unit-тестами покрыта только логика (`*_logic.js`, api/errors/limits/health/artifacts/download), сам интерфейс проверяется ручным чек-листом `frontend/tests/MANUAL_CHECKLIST.md` (Playwright не согласован). `tests/functional/test_i_ui_static.py` проверяет только статическую разметку `GET /`.
- Поведение с реальной вёрсткой LibreOffice (страницы, STR-06, TBL-10/12, производительность) покрыто только e2e-тестами, которые без контейнера пропускаются (в CI не выполняются).
- `scripts/*` (calibrate, profile, measure_layout) тестов не имеют; `build_fixtures` покрыт косвенно через `test_fixture_builders.py`.
- Пороги в `thresholds.py` — стартовые, на реальных работах не откалиброваны (калибровка только на синтетике; реальные работы заказчик прогоняет `calibrate.py` локально).

## 5. Модель данных

БД нет. Две модели:

1. **Внутренняя модель документа** (`model/document.py`, frozen/slots dataclasses): `Document` -> `Paragraph` (`ParaFormat`, `RunInfo`, `Valued` с origin), `Table`/`Row`/`Cell`/`CellRef`, `Image`, `Caption`, `Section`, `Toc`/`TocEntry`, `BibEntry`, `Appendix`, `FieldRef`, `PageSetup`, `Layout`, `DocMeta`. `Location` (`model/location.py`, `make_location`).
2. **Модели API/отчёта** (Pydantic, `model/finding.py` + `report/schema.py`, имена классов = имена схем openapi; `extra="ignore"`):
   - `Finding` (id 12 hex, `rule_id` `^[A-Z]{2,4}-\d{2}(\.\d+)?$`, `block`, `level` violation/suspicion/not_checked, `not_run`, `source` M/CH, `message`, `values`, `locations[]`, `count`, `hint`, `method`, `fingerprint`, `origin`), `RuleResult` (outcome passed/findings/not_run/not_checked, `artifacts`), `Location` (section_path, paragraph_idx, table, quote, highlight, page).
   - `CheckReport`: schema_version, service_version, checked_at, file, layout (ok/partial/failed), volume (layout/estimate), structure (дерево), summary, blocks[], not_checked[] (NC-01.N), matrix, warnings.
   - `CompareReport`: old (file, layout, summary), new (полный CheckReport), diff (`DiffReport`: sections, moves, number_changes, tables, figures, impact, dynamics fixed/new/remaining).
   - `Matrix`: rows (`hypothesis_part`/`defense_position`/`task`) x cells theory/instrument/calculation/result/conclusion (auto/gap/n/a), stats.
   - `Health`, `LoginRequest` (extra=forbid), `MatrixExportRequest`, `ErrorResponse{error:{code,message,field,request_id}}`; коды ошибок — Literal `ERROR_CODES` в `report/schema.py`.

## 6. API (по коду: `web/routes.py`, `web/auth.py`)

| Метод и путь | Авторизация | Вход | Ответ |
|---|---|---|---|
| `GET /api/health` | нет | — | `Health` (режим, auth_required, authenticated, layout_available, limits) |
| `POST /api/session` | — | JSON `{password}` (тело до 64 КБ) | 204 + cookie `vkr_session` (HttpOnly, Secure, SameSite=Strict, path=/api); 401/422/429 (rate limit по IP). В local-режиме всегда 204 |
| `DELETE /api/session` | — | — | 204, удаляет cookie |
| `POST /api/check` | в server-режиме | multipart `file` | `CheckReport`; 400/401/413/415/422/500/503 |
| `POST /api/compare` | в server-режиме | multipart `old`, `new` | `CompareReport`; те же коды |
| `POST /api/export/matrix.xlsx` | в server-режиме | JSON `MatrixExportRequest` (до `VKR_MAX_JSON_MB`) | xlsx, `Content-Disposition` UTF-8 |
| `GET /` и статика | нет | — | файлы `frontend/` (StaticFiles, html=True) |

Авторизация: cookie или `Authorization: Bearer <VKR_PASSWORD>` (для скриптов/QA; фронтенд использует только cookie, `credentials: "same-origin"`). Токен `<exp>.<hmac>`, ключ зависит от случайного boot_secret: рестарт процесса обнуляет все сессии. Middleware: `RequestContextMiddleware` (X-Request-Id), `BodyLimitMiddleware` (лимиты тела по пути). Соответствие кода `api/openapi.yaml` проверяется тестом `tests/contract/test_openapi.py`.

## 7. Тестирование, CI, деплой (по конфигам; ничего не запускалось)

- **Python-тесты: pytest** (`[tool.pytest.ini_options] testpaths=["tests"]`, `pythonpath=["src","."]`). Команда: `pytest` (в CI `pytest -q`). Состав: `tests/unit/` (38 файлов), `tests/contract/` (openapi vs модели, golden-JSON по jsonschema, отчёты реального конвейера), `tests/functional/`. Примерно 640 тест-функций суммарно. Синтетические `.docx` генерируются лениво (`tests/conftest.py`, кэш в `tests/fixtures/generated/<hash>/`, каталог в `.gitignore`).
- **Функциональный набор (для базового прогона QA): `tests/functional/`, pytest.**
  - Без внешнего окружения (FastAPI `TestClient`, local-режим, без LibreOffice, без сети): `pytest tests/functional` — выполняются test_a, b, c, d, e, g, i; test_f и test_h автоматически пропускаются (skipif).
  - E2E с LibreOffice против поднятого контейнера: `VKR_E2E_URL=http://127.0.0.1:<port> VKR_E2E_URL_TIMEOUT=http://127.0.0.1:<port2> pytest tests/functional/test_f_layout_e2e.py` (контейнер с `VKR_LAYOUT_TIMEOUT_S=1` для второго URL; инструкция в шапке файла; один тест дополнительно использует `docker exec` в контейнер с именем из `VKR_E2E_CONTAINER`, по умолчанию `qa-cycle001-vkr`).
  - E2E устойчивости: `VKR_E2E_IMAGE=vkr-checker:<tag> pytest tests/functional/test_h_crash_e2e.py` — тест сам поднимает и удаляет одноразовые docker-контейнеры на свободных портах 127.0.0.1.
- **Frontend: `node --test`**, команда `npm test` в `frontend/` (`node --test tests/*.test.js`). Дополнительно: `npm run mock` (prism mock по openapi, скачивается через `npx`, нужна сеть), `npm run dev` (dev-сервер на 127.0.0.1:8000 с прокси на мок), `npm run check:real` (`tools/check_real.mjs`, сверка с реальным backend, есть режим `--compare`).
- **Контрактные проверки вне pytest:** schemathesis упоминается в `API_CONTRACT.md` §7 как ручной прогон против запущенного сервиса; в зависимостях и в CI его нет (в рабочей копии есть игнорируемый `.schemathesis/` с кэшем падений локального прогона, см. §10).
- **Линтер:** ruff (`line-length=100`, правила E, F, I, B, UP), `ruff check .`.
- **CI:** `.github/workflows/ci.yml`, GitHub Actions, на любой push и pull_request. Job `test`: Python 3.12, `pip install -e ".[dev]"`, `ruff check .`, `pytest -q`, Node 20, `npm test` в `frontend/`. Job `docker`: `docker build -t vkr-checker:ci .` (только сборка, без запуска и без публикации образа). В CI e2e test_f/test_h пропускаются.
- **Деплой:** автоматического деплоя нет. Способы запуска — `vkr-checker` (локально), `docker compose up --build` (порт на хосте `VKR_HOST_PORT`, по умолчанию 8000, для параллельных циклов 8000+NNN), healthcheck в Dockerfile на `/api/health`.
- **Ветки:** `master`, `develop`, `cycle/001-vkr-checker-mvp` (локально и в origin).

## 8. Конвенции проекта

- Язык: комментарии, docstring, сообщения пользователю и коммиты — на русском. Docstring модуля ссылается на раздел архитектуры (`ARCHITECTURE.md §N`, `ARCHITECTURE_CHECKS.md §N`).
- Python: `from __future__ import annotations` везде; совместимость с 3.10 (явные `# noqa: UP017/UP042`, без `StrEnum`, `datetime.now(timezone.utc)`); ruff, длина строки 100; `# fmt: skip` точечно.
- Внутренние структуры — frozen dataclasses (`slots=True` в модели); на границе API — Pydantic v2, имена классов совпадают с именами схем в `api/openapi.yaml`. Контракт первичен: сначала правится `openapi.yaml`, модели повторяют его.
- Правила проверок: класс с атрибутами `id`, `title`, `block`, `source=Source("M"|"CH", ...)`, `default_level`, `needs=frozenset({Need...})`, `priority`, методом `run(ctx) -> RuleResult`; регистрация декоратором `@register`; новый модуль с правилами нужно вписать в `RULE_MODULES` в `checks/registry.py` (автосканирования нет). Находки создаются через `new_finding(...)`, результат — `result_of(...)`. Движок сам ставит not_run/not_checked по `needs`, присваивает стабильные id.
- Все числовые пороги — только в `thresholds.py`, передаются через `ctx.th`.
- Ошибки HTTP — через `ApiError(code, ...)` (`web/errors.py`) с кодами из `ERROR_CODES`; ошибки входного файла — `DocxError`/`InputFileError`. В лог не пишется содержимое работ, только тип исключения.
- HTTP-слой без бизнес-логики; тяжёлая работа в потоках executor.
- Frontend: ES-модули без сборщика, абсолютные импорты `/js/...`; логика отделена от DOM в `*_logic.js` (тестируемые чистые функции); весь сетевой обмен через `createApi()` в `js/api.js` (fetch, `credentials: "same-origin"`); ошибки — `ApiError`/`userMessage` из `js/errors.js`; вывод текста работы только через `textContent` (XSS), без внешних ресурсов.
- Тесты: синтетические `.docx` только через генераторы (`tests/fixtures/builders/`, `tests/functional/thesis.py` — блоки + мутации); реальные работы в репозиторий не попадают (`.gitignore`: `*.docx`, `*.pdf`, `local_corpus/`).

## 9. Существующая документация и тест-кейсы

| Что | Путь | Формат | Структура |
|---|---|---|---|
| Краткая продуктовая документация | `/README.md` | markdown | Возможности; Запуск (Local / Server / Docker); Переменные окружения (таблица); Тесты и утилиты; Оговорки |
| CHANGELOG | **не найден** (нет файла, нет `docs/`, релизов/тегов в git нет; история только в `git log`) | — | — |
| Развёрнутая пользовательская документация (гайды, FAQ, онбординг) | **не найдена**. Внутри приложения справочного раздела нет; в каждом отчёте есть блок «Не проверяется кодом» (NC-01) и оговорки о вёрстке | — | — |
| Документация API | `/api/openapi.yaml` (OpenAPI 3.1.0, ручной, источник истины) и `/API_CONTRACT.md` (markdown: общие правила, эндпоинты §2.1-2.6, авторизация, лимиты, ошибки, формы ответа, как проверяется соответствие). Postman-коллекции нет. Примеры ответов — `tests/golden/*.json` | YAML / markdown / JSON | — |
| Описания тест-кейсов | `/TEST_CASES.md` | markdown, одна таблица | Сквозные ID TC-001..TC-072, новые кейсы в конец; колонки: ID, Критерий SPEC, Кейс, Шаги, Ожидание, Файл (test_a..test_i), Статус |
| Ручной чек-лист UI | `/frontend/tests/MANUAL_CHECKLIST.md` | markdown, нумерованный список | 10 пунктов (старт, вход, баннер LO, загрузка, отчёт, XSS, офлайн-отчёт, матрица, сравнение, печать/фокус) |
| Документы цикла 001 (лежат в корне, не архивированы) | `/SPEC.md`, `/ARCHITECTURE.md`, `/ARCHITECTURE_CHECKS.md`, `/ARCHITECTURE_TASKS.md`, `/API_CONTRACT.md` | markdown | SPEC — требования и критерии приёмки по блокам 4.A-4.E; ARCHITECTURE* — устройство, реестр правил, задачи и риски. Соглашения об архиве `docs/history/` в README нет, каталога `docs/` нет |
| Исходные требования заказчика | `требования вкр.pdf`, `рекомендации и чек лист.md` | PDF / markdown | лежат локально, в `.gitignore`, в репозитории их нет |

## 10. Рискованные и хрупкие места

- **Нет `uv.lock` и других lock-файлов:** зависимости заданы только нижними границами (`>=`), Docker и CI ставят последние версии; сборка невоспроизводима.
- **Эвристики на синтетике:** CON/HYP/TSK/MET/LEX и пороги `thresholds.py` откалиброваны только на сгенерированных `.docx`; `ARCHITECTURE_TASKS.md` §7 сам оценивает шум на реальных работах как «высокая вероятность / высокое влияние». HYP-01 переделывался в 6 коммитах подряд по замечаниям ревью/QA (распознавание статуса гипотезы по оборотам речи) — самый «нервный» участок.
- **Крупные и центральные модули:** `checks/structure.py` (452 строки), `checks/tables_format.py` (423), `docx/styles.py` (368, каскад стилей таблиц — риск ложных TBL-01/02/05 по `ARCHITECTURE_TASKS.md`), `checks/consistency.py` (352), `checks/numbering.py` (338). От `docx/reader.py`, `docx/styles.py`, `structure/detector.py` зависят все правила.
- **Вёрстка LibreOffice:** пагинация отличается от Word (допуск ±2 стр.); поведение с реальным LO проверяется только e2e, которые в CI не выполняются. PDFium не потокобезопасен — все вызовы сериализованы глобальным `_PDFIUM_LOCK` (`layout/pdftext.py`), была отдельная правка Q0. В `TEST_CASES.md` у TC-071 в колонке «Ожидание» записано «compare - падение процесса» при статусе OK — формулировка неоднозначна, из документа нельзя понять, исправлено ли.
- **Безопасность/сессии:** cookie ставится с `Secure=True`; в server-режиме по plain HTTP (без HTTPS-прокси) браузер её не сохранит. HTTPS-прокси по решению заказчика отложен. Сессии и rate limit живут в памяти одного процесса (рестарт сбрасывает сессии; при нескольких репликах лимит не общий).
- **Pre-commit-проверка на `*.docx`/`*.pdf`**, заявленная в `ARCHITECTURE_TASKS.md` §7 как мера против утечки данных, в репозитории не настроена: защита только через `.gitignore`.
- **Schemathesis:** в рабочей копии есть игнорируемый `.schemathesis/default/cache/crashes/` (последние записи 2026-10-20 03:58, base_url 127.0.0.1:8765) с падениями проверок `allow_header_conformance`, `unsupported_method`, `positive_data_acceptance`, `not_a_server_error` для `POST /api/check`, `/api/compare`, `/api/export/matrix.xlsx`, `/api/session`. Исправлены ли они после этого прогона, по репозиторию не видно; schemathesis в CI нет.
- **Расхождение документации и кода:** README пишет `pytest # unit + contract`, но `testpaths=["tests"]` включает и `tests/functional/` (без e2e). `API_CONTRACT.md` §7 упоминает `openapi-spec-validator`, а в зависимостях и тестах его нет: используются `jsonschema` + `pyyaml`.
- **UI без автотестов DOM** (см. §4): регрессии интерфейса ловятся только ручным чек-листом.
- `ruff` в CI запускается по всему репозиторию; в функциональных тестах стоит `# ruff: noqa: E501` на файл.
