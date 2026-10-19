# ARCHITECTURE: vkr-checker (MVP)

Версия 1.0, 2026-10-19. Основа: SPEC.md v1.0 с блоком «Решения заказчика» (§0). Ссылки на правила даны по ID из SPEC (STR-01, TBL-03 …), без пересказа.

## Оглавление архитектуры

| Файл | Что внутри |
|---|---|
| ARCHITECTURE.md (этот) | стек, развёртывание, структура репозитория, модель документа, парсинг .docx, распознавание структуры, пагинация LibreOffice |
| [ARCHITECTURE_CHECKS.md](ARCHITECTURE_CHECKS.md) | движок проверок, модель находки, реестр правил SPEC → модуль/подход, пороги, сравнение версий (DIF), матрица (MAT), отчёт |
| [API_CONTRACT.md](API_CONTRACT.md) + [api/openapi.yaml](api/openapi.yaml) | HTTP-контракт; openapi.yaml — источник истины для backend, frontend и QA |
| [ARCHITECTURE_TASKS.md](ARCHITECTURE_TASKS.md) | задачи backend/frontend, параллельность, порядок, риски |

Разделы этого файла: 1. Стек · 2. Развёртывание и конфигурация · 3. Структура репозитория · 4. Конвейер обработки запроса · 5. Модель документа · 6. Парсинг .docx · 7. Распознавание структуры · 8. Пагинация через LibreOffice · 9. Безопасность и данные.

---

## 1. Стек и обоснование

| Слой | Выбор | Почему |
|---|---|---|
| Язык | Python 3.12 | задан заказчиком; лучшая экосистема для .docx и русской морфологии |
| HTTP | FastAPI + uvicorn | минимум кода, автогенерация и валидация по Pydantic, OpenAPI-совместимость (QA сверяет с api/openapi.yaml) |
| Модели | Pydantic v2 (API, отчёт), `dataclasses(slots=True)` (внутренняя модель документа) | Pydantic — граница API; dataclass быстрее для ~1500 абзацев × 2 версии |
| Конфиг | pydantic-settings, переменные окружения `VKR_*` | один источник, без файлов с секретами в репо |
| .docx | python-docx (открытие пакета, части, стили) + lxml напрямую по `w:` XML | python-docx не даёт эффективного форматирования, автонумерации, полей, рецензирования — это пишем сами поверх lxml (§6) |
| Вёрстка | LibreOffice headless (`soffice --convert-to pdf`), обязательная зависимость | решение заказчика §0 п.1 |
| Текст PDF | pypdfium2 (Apache/BSD) | быстрый постраничный текст; PyMuPDF не берём — AGPL мешает возможной продаже как сервиса |
| Сравнение строк | rapidfuzz (близость, перемещения), difflib (пословный diff) | C-скорость для поиска перемещений; difflib — стабильный детерминированный diff |
| Морфология | pymorphy3 + pymorphy3-dicts-ru | леммы и словоформы офлайн |
| Отчёт | JSON (источник истины) → самодостаточный HTML: шаблон `report_viewer.html` с встроенными CSS/JS, JSON вшит в `<script type="application/json">` | один рендерер отчёта на фронтенде и для показа, и для скачивания; файл открывается без сети |
| Матрица | .xlsx через openpyxl | редактируется и в Excel, и в LibreOffice Calc; таблица 6 столбцов удобнее в табличном редакторе |
| Фронтенд | статические HTML + vanilla JS (ES2020) + CSS, без сборки, раздаются FastAPI `StaticFiles` | одна страница (UI-01), нет node-тулчейна в развёртывании |
| Тесты | pytest, синтетические .docx генерируются кодом (python-docx + lxml-патчи) в `tests/fixtures/builders` | §0 п.5: только синтетика; QA контракта — schemathesis по openapi.yaml |
| Упаковка | uv (pyproject.toml + uv.lock), Docker | воспроизводимые зависимости; запуск одной-двумя командами (US-21) |

LLM нет. Точка подключения будущего модуля моделей — общий протокол проверки (ARCHITECTURE_CHECKS.md), не HTTP.

## 2. Развёртывание и конфигурация

### 2.1. Режимы
- **local** (по умолчанию): bind `127.0.0.1:8000`, без пароля.
- **server**: включается явно `VKR_MODE=server`; без `VKR_PASSWORD` процесс не стартует (fail fast). Bind `0.0.0.0`, TLS — на обратном прокси (Caddy/nginx), сервис сам TLS не терминирует. Авторизация — см. API_CONTRACT.md (общий пароль, сравнение `hmac.compare_digest`).

### 2.2. Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `VKR_MODE` | `local` | `local` / `server` |
| `VKR_HOST` / `VKR_PORT` | `127.0.0.1` / `8000` | в server-режиме host по умолчанию `0.0.0.0` |
| `VKR_PASSWORD` | — | обязателен в server |
| `VKR_SOFFICE_PATH` | автопоиск | `soffice` в PATH; macOS: `/Applications/LibreOffice.app/Contents/MacOS/soffice` |
| `VKR_LAYOUT_TIMEOUT_S` | `20` | таймаут вёрстки одного документа |
| `VKR_LAYOUT_CONCURRENCY` | `2` | максимум одновременных soffice (сравнение = 2 документа) |
| `VKR_MAX_UPLOAD_MB` | `20` | лимит файла |
| `VKR_MAX_UNZIPPED_MB` / `VKR_MAX_ZIP_ENTRIES` | `200` / `2000` | защита от zip-бомб |
| `VKR_LOG_LEVEL` | `INFO` | содержимое работ не логируется никогда |
| `VKR_SESSION_TTL_H` | см. API_CONTRACT | срок жизни cookie-сессии (server) |
| `VKR_LOGIN_RATE_PER_MIN` | `5` | лимит попыток входа с одного IP |
| `VKR_TRUST_PROXY` | `false` | доверять X-Forwarded-For за прокси |
| `VKR_MAX_JSON_MB` | см. API_CONTRACT | лимит JSON-тела (экспорт матрицы) |
| `VKR_MAX_CONCURRENT_JOBS` | `2` | слоты обработки (сравнение занимает оба) |
| `VKR_CHECK_TIMEOUT_S` / `VKR_COMPARE_TIMEOUT_S` | `90` / `150` | жёсткие таймауты запроса |

### 2.3. Docker (основной способ, одинаков для local и server)
```
FROM python:3.12-slim-bookworm
RUN apt-get install --no-install-recommends libreoffice-writer-nogui \
      fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core
# Liberation Serif/Sans метрически совместимы с Times New Roman/Arial,
# Carlito/Caladea — с Calibri/Cambria: без них вёрстка «уезжает» на десятки страниц.
COPY uv.lock pyproject.toml → uv sync --frozen --no-dev
COPY src/ frontend/
USER app (не root), HOME=/tmp/app, read-only rootfs допустим (tmpfs на /tmp)
HEALTHCHECK → GET /api/health
CMD ["vkr-checker"]   # entry point читает VKR_*
```
- `docker-compose.yml`: порт `127.0.0.1:8000:8000` (local), tmpfs `/tmp`, без томов для данных.
- Локальный запуск: `docker compose up` → http://127.0.0.1:8000. Без Docker: `brew install --cask libreoffice` (или пакет ОС) + `uv run vkr-checker`.
- На старте: проверка `soffice --version` (результат в `/api/health`: `layout_available`). Если LibreOffice нет — сервис работает, но вёрстка всегда в откате (§8.5) и это видно в отчёте и health.
- Шрифты: если в документе указан шрифт, которого нет в системе (`fc-list`), в отчёт попадает оговорка «шрифт X заменён при вёрстке, страницы могут расходиться». Опционально для точности — ttf-mscorefonts-installer (contrib) или своя папка шрифтов `VKR_EXTRA_FONTS_DIR`; в образ по умолчанию не входят (лицензия).

## 3. Структура репозитория

```
pyproject.toml  uv.lock  Dockerfile  docker-compose.yml  .gitignore  .dockerignore  README.md
api/openapi.yaml                  # контракт (шаг 3)
src/vkr_checker/
  __init__.py                     # __version__ (в отчёте, UI-03)
  main.py                         # create_app(), CLI entry `vkr-checker`
  config.py                       # Settings (VKR_*)
  thresholds.py                   # ВСЕ пороги эвристик в одном месте (§5 SPEC «Точность»)
  web/        routes.py auth.py upload.py errors.py   # HTTP-слой, без бизнес-логики
  pipeline.py                     # оркестрация §4: temp dir → parse ‖ layout → checks → report
  model/      document.py location.py               # модель §5 (finding.py — шаг 2)
  docx/       package.py   # безопасное открытие zip, лимиты, отказ от внешних связей
              xmlutil.py   # namespaces, итерация по телу с учётом mc:AlternateContent
              revisions.py # принятие рецензирования
              styles.py    # движок эффективного форматирования
              numbering.py # восстановление автонумерации
              fields.py    # SEQ/REF/TOC/PAGEREF: инструкция + сохранённый результат
              reader.py    # XML → плоский поток блоков (Paragraph/Table/Image)
  structure/  detector.py patterns.py toc.py captions.py bibliography.py appendices.py
  layout/     soffice.py   # запуск, изоляция профиля, таймаут, kill
              pdftext.py   # pypdfium2 → текст по страницам
              align.py     # привязка абзацев/таблиц/заголовков к страницам
              estimate.py  # откат: оценка объёма по тексту
  nlp/        normalize.py morph.py                 # общие утилиты текста (шаг 2 расширит)
  checks/  diff/  matrix/  report/                  # см. ARCHITECTURE_CHECKS.md
frontend/   index.html app.js styles.css report_viewer.html
tests/      unit/ integration/ contract/ fixtures/builders/ golden/
scripts/    build_fixtures.py  calibrate.py         # calibrate гоняет local_corpus/ и печатает статистику
local_corpus/                     # реальные ВКР для калибровки — в .gitignore, никогда не коммитить
```
`.gitignore` (обязательно с первого коммита): `*.pdf`, `рекомендации и чек лист.md`, `local_corpus/`, `/*.docx`, `tests/fixtures/generated/`, `.env`. Фикстуры .docx генерируются при тестах, в репо — только генераторы.

Правило зависимостей слоёв: `web → pipeline → {structure, layout, checks, diff, matrix, report} → model, docx, nlp`. `model` ни от чего не зависит. Проверки не читают XML напрямую — только модель документа.

## 4. Конвейер обработки запроса

```
upload → TemporaryDirectory (0700) ──┬─ docx.package: лимиты, zip-проверка
                                     ├─ поток A: reader → structure → Document (без страниц)
                                     └─ поток B: sanitized copy → soffice → PDF → pdftext
               join: layout.align(Document, PdfPages) → Document.layout | откат (§8.5)
               → checks → Report(JSON) → ответ;  finally: rmtree(temp), закрыть soffice
```
- A и B идут параллельно (B — subprocess, A — CPU в потоке), чтобы уложиться в 30 с (SPEC §5): бюджет ориентировочно parse ≤ 5 с, вёрстка ≤ 20 с (параллельно), проверки ≤ 5 с.
- Сравнение версий: два конвейера параллельно (семафор `VKR_LAYOUT_CONCURRENCY`), затем diff (бюджет 60 с).
- Обработка синхронна в рамках одного HTTP-запроса; очередей и хранилища нет (1–2 пользователя, SPEC §5). Сервер не хранит ни файлы, ни отчёты: скачивание строится из JSON, который присылает клиент (подробности — API_CONTRACT.md).
- Детерминизм: никаких итераций по `set`/`dict` без сортировки при выводе, стабильные ID находок, время проверки — единственное поле, зависящее от запуска.

## 5. Внутренняя модель документа (`model/document.py`)

Иммутабельные после построения dataclass-ы. Индексы — целые, стабильные для одного файла.

```
Document
  meta: filename (без пути), sha256 (для DIF-06), parsed_at, warnings[]        # предупреждения парсинга
  page_setup: [PageSetup(section_idx, margin_left_cm, margin_right_cm, text_width_cm, …)]  # PAGE-01, TBL-03
  blocks: list[Block]            # плоский поток тела в порядке документа: Paragraph | Table
  paragraphs: list[Paragraph]    # все абзацы тела (вне таблиц), индекс = Paragraph.idx
  tables: list[Table]            # все таблицы, включая вложенные (parent_table_idx)
  images: list[Image]
  captions: list[Caption]
  sections: list[Section]        # дерево логических разделов (корни — уровень 1)
  toc: Toc | None
  bibliography: list[BibEntry]
  appendices: list[Appendix]
  fields: list[FieldRef]         # SEQ/REF/PAGEREF с инструкцией и результатом
  layout: Layout | None          # §8; None = откат
```

**Paragraph**: `idx` (сквозной номер абзаца тела, с 1 — то, что видит пользователь, SPEC §3.3); `text` (видимый текст после принятия правок, с результатами полей; без автономера); `num_label` (восстановленный автономер, напр. «1.1.» / «3)», или None); `full_text` = `num_label + " " + text`; `style_id`, `style_name`; `outline_level` (0–8 | None, из pPr или стиля); `fmt: ParaFormat` (эффективные значения, §6.3); `runs: list[RunInfo]` (текст + эффективные bold/italic/size/font — для эвристик заголовков и шрифтовых оговорок); `container`: `body | table_cell | textbox | footnote`; `cell: CellRef | None` (table_idx, row, col) для абзацев ячеек; `page_break_before: bool` (явный `w:br type=page` в конце предыдущего абзаца, `pageBreakBefore`, `sectPr` nextPage/oddPage); `section_id`.

Абзацы ячеек и надписей хранятся в своих объектах (`Table.cells[].paragraphs`, `Image.textbox_paragraphs`) и **не получают** сквозной `idx` тела, чтобы номер совпадал с подсчётом «абзац N» при поиске в Word; их место задаётся `CellRef`. Сноски и колонтитулы в MVP не входят ни в текст, ни в подсчёты (SPEC §6 п.4), надписи — входят только для поиска рисунков и подписей.

**ParaFormat** (всё в EMU/twips → нормализовано в см и pt; `None` = не задано нигде, применяется значение по умолчанию Word): `first_line_cm`, `hanging_cm`, `left_cm`, `right_cm`, `line_spacing` + `line_rule` (`auto|exact|atLeast`), `space_before_pt`, `space_after_pt`, `align` (`left|center|right|both|…`), `v_align` (для ячеек), `keep_next`, `keep_lines`, `page_break_before`. Каждое значение несёт `origin` (`defaults|table_style|para_style|direct`) — нужно для подсказок («отступ пришёл из стиля „Обычный“»).

**Table**: `idx` (порядковый номер в документе, с 1); `anchor_block` (позиция в `blocks`); `prev_paragraph_idx`/`next_paragraph_idx`; `rows: list[Row(height_twips, height_rule, cant_split, cells)]`; `cells: Cell(row, col, grid_span, v_merge, width, paragraphs, text)`; `grid_cols_cm[]`; `width_cm`, `width_type` (`dxa|pct|auto`), `layout_type` (`fixed|autofit`); `style_id`, `style_exists: bool` (TBL-09); `caption_idx | None`; `parent_table_idx | None`; `section_id`.

**Image**: `idx`, `paragraph_idx` (ближайший абзац тела), `kind` (`picture|chart|smartart|shape_group`), `in_textbox`, `textbox_paragraphs[]`, `caption_idx | None`.

**Caption**: `kind` (`table|figure`), `label_text` («Таблица»/«Табл.»/«Рисунок»/«Рис.»), `number` (строка: «3», «2.1», «А.1»), `number_parts: tuple[str,…]`, `number_source` (`text|seq_field|autonum`), `seq_field_stale_suspect: bool`, `title`, `paragraph_idx` или (`textbox`, `image_idx`), `target` (table_idx | image_idx | None), `in_appendix: bool`.

**Section** (логический раздел): `id`, `kind` (`TITLE|TOC|INTRO|CHAPTER|SUBSECTION|CHAPTER_CONCLUSIONS|CONCLUSION|BIBLIOGRAPHY|APPENDIX|UNKNOWN`), `title` (как в тексте), `number` («1», «2.1» | None), `level`, `heading_paragraph_idx | None` (None у TITLE), `start_idx`/`end_idx` (диапазон абзацев тела включительно), `parent_id`, `children[]`, `role_hint` (`theoretical|empirical|None` для глав), `detection` (`style|pattern|heuristic`) + `confidence` (0–1).

**Toc**: `source` (`toc_field|toc_styles|text_pattern`), `entries: [TocEntry(text, number, level, page_text, page_num, paragraph_idx, resolved_section_id | None)]`.

**BibEntry**: `number` (из автонумерации или текста), `text`, `paragraph_idx`. **Appendix**: `label` («Приложение 1»/«Приложение А»), `key` («1»/«А»), `title`, `section_id`, `starts_new_page: bool`.

**Location** (`model/location.py`, общий тип для находок, diff и матрицы):
```
Location
  section_path: list[str]        # ["Глава 2", "2.1 Организация и методы исследования"]
  paragraph_idx: int | None      # сквозной номер абзаца тела
  table: TableRef | None         # number_label («Таблица 3» | «таблица №5 без подписи»), table_idx, row, col (с 1)
  quote: str                     # ~100 символов вокруг находки
  highlight: (start, end) | None # смещения внутри quote
  page: int | None               # номер страницы по вёрстке LibreOffice (только если layout есть); информационно
```
Построение — единственной функцией `make_location(doc, paragraph_idx | cell_ref, char_span)`, чтобы цитаты и пути были одинаковы во всех проверках. `page` — расширение SPEC §3.3: показывается с пометкой «по вёрстке LibreOffice, ±1–2 стр.».

## 6. Парсинг .docx (`docx/`)

### 6.1. Открытие и обход
- `package.py`: проверка расширения и сигнатуры zip; `zipfile.infolist()` — сумма `file_size` ≤ лимита, число записей ≤ лимита, нет абсолютных путей и `..`; наличие `word/document.xml`. Иначе — ошибка «файл не является корректным .docx» (код — API_CONTRACT.md). `.doc/.odt/.pdf` отклоняются по сигнатуре, не по имени.
- XML разбирается lxml с `resolve_entities=False, no_network=True, huge_tree=False`.
- Обход тела `w:body` в порядке документа: `w:p`, `w:tbl` (рекурсивно для вложенных), `w:sdt` (раскрываем содержимое — в нём часто оглавление), `mc:AlternateContent` → только `mc:Choice` (иначе двойной подсчёт рисунков), `w:txbxContent` внутри `wps:txbx`/`v:textbox` → абзацы надписи привязываются к содержащему абзацу.

### 6.2. Рецензирование и поля (`revisions.py`, `fields.py`)
- Правки считаются принятыми (SPEC §3.5): текст из `w:ins`, `w:moveTo` берётся; `w:del`, `w:moveFrom`, `w:delText` пропускаются; `w:pPrChange`/`w:rPrChange` игнорируются (действует новое форматирование). Комментарии (`commentRangeStart`, `commentReference`) пропускаются.
- Поля: `w:fldSimple` и составные `fldChar begin → instrText → separate → результат → end` (с вложенностью). В текст абзаца идёт **сохранённый результат**; инструкция (`SEQ Таблица`, `REF _Ref…`, `PAGEREF`, `TOC \o`) сохраняется в `FieldRef` с позицией. Поля не пересчитываются.
- `SEQ`: номер = результат поля. Повтор одного номера у нескольких SEQ одной последовательности → `seq_field_stale_suspect` (SPEC §3.5).

### 6.3. Эффективное форматирование (`styles.py`, SPEC §6 п.2)
Порядок наложения для свойства абзаца в ячейке (поздний перекрывает ранний):
1. `w:docDefaults` (`pPrDefault`, `rPrDefault`);
2. стиль таблицы: базовый `tblPr/pPr/rPr` по цепочке `basedOn`, затем условные `tblStylePr` в порядке Word: `wholeTable → band1/2Vert → band1/2Horz → firstCol/lastCol → firstRow/lastRow → угловые`, с учётом `tblLook` (какие условия включены) и `cnfStyle` ячейки/строки;
3. стиль абзаца по цепочке `basedOn` (от корня к листу); если `pStyle` не задан — стиль по умолчанию (`w:default="1"`, обычно «Обычный»);
4. прямое `w:pPr` абзаца.
Для свойств текста дополнительно: стиль символа (`rStyle`) и прямое `w:rPr`. Особенности, которые нужно учесть: `w:ind` с атрибутами `firstLine`/`hanging`/`firstLineChars` (chars → через размер шрифта); `start/end` как синонимы `left/right`; `w:contextualSpacing`; спецзначение `auto` в spacing. Результат кэшируется по `(style_id, table_style_id, cnf_mask)`; прямое форматирование накладывается поверх кэша. Модуль покрывается отдельными юнит-тестами на XML-фрагментах — это главный технический риск TBL-01/02/05/08.

### 6.4. Автонумерация (`numbering.py`, SPEC §6 п.3)
- Источник `numPr` (numId, ilvl): прямое у абзаца или из стиля (цепочка `basedOn`; стили заголовков часто несут нумерацию).
- `numbering.xml`: `w:num` → `abstractNumId` + `lvlOverride/startOverride`; `w:abstractNum/w:lvl`: `start`, `numFmt` (`decimal`, `russianLower/Upper`, `lowerLetter`, `upperRoman`, `bullet`, `none`), `lvlText` («%1.%2.»), `lvlRestart`, `isLgl`; `numStyleLink/styleLink`.
- Счётчики ведутся по `abstractNumId` в порядке документа (как Word: разные `numId` над одним abstractNum продолжают счёт, если нет `startOverride`); сброс более глубоких уровней при выходе на верхний. `bullet` → `num_label` = None, но флаг `is_list_item=True`.
- Известное расхождение с Word возможно на экзотике (`w:legacy`, списки в полях); в таких случаях метка ставится по лучшей догадке, а в `meta.warnings` — запись.

### 6.5. Таблицы, рисунки, разметка страниц
- Сетка таблицы: `w:tblGrid/w:gridCol` → `grid_cols_cm`; объединения `gridSpan`/`vMerge` сохраняются, логическая ячейка — по началу объединения.
- Ширина текста страницы: из `sectPr` раздела, в котором стоит таблица: `pgSz.w − pgMar.left − pgMar.right` (+ `gutter`). Последний `sectPr` — в `w:body`, промежуточные — в `pPr` последнего абзаца раздела.
- Рисунки: `w:drawing` с `pic:pic` (`a:blip`), `c:chart`, `dgm:` (SmartArt), группы `wpg:`; VML `v:imagedata`. Внешние изображения (`r:link`, `TargetMode="External"`) не загружаются, учитываются как рисунок.

## 7. Распознавание структуры (`structure/`, SPEC §0 п.3, §6 п.5)

Стратегия «стили → текстовые шаблоны → эвристики»; каждый найденный заголовок несёт `detection` и `confidence`. Все регулярки и словари — в `patterns.py` (пересказ, без дословных фрагментов методички).

1. **Кандидаты в заголовки.** (а) `outline_level` из pPr/стиля или имя стиля `Heading N`/`Заголовок N` (по `w:name` и `w:styleId`, в т.ч. локализованные); (б) шаблоны в `full_text`: `^ГЛАВА\s+(\d+|[IVX]+)\.?`, `^\d+\.\s+\S`, `^\d+\.\d+\.?\s+\S`, названия разделов уровня 1 (ВВЕДЕНИЕ, ЗАКЛЮЧЕНИЕ, СПИСОК … ЛИТЕРАТУРЫ / БИБЛИОГРАФИЧЕСКИЙ СПИСОК, ОГЛАВЛЕНИЕ/СОДЕРЖАНИЕ, ПРИЛОЖЕНИЕ X, ВЫВОДЫ …); (в) эвристика: короткий абзац (< 150 симв., без точки в конце), весь bold или CAPS, выравнивание по центру/разрыв страницы перед ним. (в) используется, только если (а) и (б) дали < 3 заголовков уровня 1.
2. **Классификация уровня 1** по словарю имён → `INTRO`, `CONCLUSION`, `BIBLIOGRAPHY`, `TOC`, `APPENDIX`; всё с «ГЛАВА N» или номером «N.» между введением и заключением — `CHAPTER`. `role_hint`: ключевые основы «теорет…»/«эмпирич…»/«экспериментальн…» в названии, иначе по порядку (первая — теоретическая, вторая — эмпирическая).
3. **Подразделы** — заголовки «N.M» внутри главы; номер берётся из текста или `num_label`. «Выводы …» в конце главы → `CHAPTER_CONCLUSIONS` (как подраздел или как блок абзацев, начинающийся с «Выводы»).
4. **Титульный лист** — абзацы до первого из {оглавление, введение}; если их нет → `TITLE` отсутствует (STR-01 даст подозрение).
5. **Оглавление** (`toc.py`): по приоритету — поле `TOC` (диапазон между `fldChar begin/end` или `w:sdt` с `docPartGallery=Table of Contents`); абзацы стилей `TOC N`/`Оглавление N`; абзацы после заголовка «Оглавление/Содержание» вида `текст [….·\t]+ \d+$` до начала введения. Записи сопоставляются с `Section` по нормализованному тексту (rapidfuzz `token_set_ratio`, порог в `thresholds.py`) → `resolved_section_id`. Абзацы оглавления не считаются заголовками разделов.
6. **Подписи** (`captions.py`): абзац (тела или надписи), начинающийся с `Таблица|Табл.|Рисунок|Рис.` + номер (из текста, SEQ или автонумерации). Привязка: подпись таблицы — ближайший абзац **перед** таблицей (допускается 1 промежуточный пустой/«Продолжение…»), подпись рисунка — абзац **после** рисунка (или внутри той же надписи); при неоднозначности — ближайший объект. `in_appendix` — по разделу.
7. **Литература** (`bibliography.py`): элементы списка (автонумерация или «N.» в тексте) внутри `BIBLIOGRAPHY`.
8. **Приложения** (`appendices.py`): заголовки «Приложение N/Буква»; `starts_new_page` = `page_break_before` у заголовка или у предшествующего пустого абзаца; при наличии `layout` дополнительно проверяется, что заголовок первый на своей странице.

Результат распознавания пишет в отчёт служебный блок «Распознанная структура» (дерево разделов с `detection`), чтобы пользователь видел, почему проверка «не выполнена».

## 8. Пагинация через LibreOffice (`layout/`, SPEC §0 п.1)

### 8.1. Результат
```
Layout
  engine: "libreoffice <version>"
  page_count: int
  paragraph_pages: dict[paragraph_idx, int]       # страница начала абзаца тела
  table_pages: dict[table_idx, (first_page, last_page)]
  heading_pages: dict[section_id, int]
  coverage: float                                 # доля абзацев тела, привязанных напрямую (не интерполяцией)
  font_substitutions: list[str]
  status: "ok" | "partial"                        # partial: coverage < порога «ok», но ≥ порога отката
```
Потребители (ARCHITECTURE_CHECKS.md): VOL-01 (страницы от `heading_pages[INTRO]` до страницы перед `BIBLIOGRAPHY`), TBL-10 (`last_page > first_page` и таблица длиннее страницы), разрывы коротких таблиц (`first_page != last_page` при числе строк ≤ порога), STR-02/номера страниц оглавления (`TocEntry.page_num` против `heading_pages`), STR-05 (приложение с новой страницы).

### 8.2. Запуск soffice (`soffice.py`)
- Вход — **санитизированная копия** .docx в temp dir: удалены внешние связи (`TargetMode="External"` в `.rels`, `w:attachedTemplate`, OLE-ссылки), чтобы LibreOffice ничего не загружал из сети.
- Команда: `soffice --headless --norestore --nolockcheck --nodefault -env:UserInstallation=file://<tmp>/lo-profile --convert-to pdf:writer_pdf_Export --outdir <tmp> <file>`. Отдельный профиль на каждый запуск — иначе параллельные запуски конфликтуют по lock-файлу профиля.
- `subprocess.Popen(start_new_session=True)`; по таймауту `VKR_LAYOUT_TIMEOUT_S` — `killpg(SIGKILL)` всей группы (soffice порождает `soffice.bin`). Ограничение одновременных запусков — семафор `VKR_LAYOUT_CONCURRENCY`.
- Поля LibreOffice при экспорте не обновляет: оглавление в PDF — то, что сохранил автор, что и нужно для проверки устаревших номеров.
- Риск производительности: холодный старт soffice 2–4 с + вёрстка 150 стр. 3–10 с. Если на целевом ноутбуке бюджет не держится, план Б — постоянный процесс через `unoserver` (тот же образ, +1 пакет). Решение — по замеру в задаче вёрстки (ARCHITECTURE_TASKS.md).

**Решение по замеру B-20 (2026-10-19): `soffice` на запрос, `unoserver` не нужен.** Замер `scripts/measure_layout.py` в Docker-образе проекта (LibreOffice 7.4.7, Debian bookworm, arm64, Docker Desktop на Mac M2, VM 2 CPU / 3,8 ГБ), каждый запуск с новым профилем (то есть «холодный»):

| Синтетика | Страниц в PDF | Время вёрстки |
|---|---|---|
| `clean_70p` | 70 | 0,6–1,2 с |
| `clean_150p` | 137 | 0,7–1,0 с |
| 150 стр. + 80 таблиц × 13 строк + 80 рисунков | 185 | 1,5–1,6 с |

Бюджет 20 с выдерживается с запасом более чем в 10 раз, поэтому постоянный процесс `unoserver` не вводится (меньше состояния, нет утечек памяти долгоживущего процесса). Оговорки: (1) это Linux-VM внутри Docker, нативный LibreOffice для macOS на этой машине не установлен и не измерялся (повторить: `brew install --cask libreoffice`, затем `python scripts/measure_layout.py`); (2) синтетика текстовая и без экзотики: у реальных работ со сканами, SmartArt и нестандартными шрифтами время может быть выше; (3) в Docker стоит LibreOffice 7.4, а не 24.x. Пересмотреть решение, если на реальных работах медиана `layout` превысит 10 с.

### 8.3. Текст по страницам (`pdftext.py`)
pypdfium2: для каждой страницы `textpage.get_text_range()` → нормализация (NFKC, `ё→е`, удалить мягкие переносы `­` и дефисы переноса в конце строки, схлопнуть пробельные символы, нижний регистр, убрать всё кроме букв/цифр). Строки, состоящие только из числа (колонтитул с номером страницы), отбрасываются. Получаем `pages_norm: list[str]` и общую строку с массивом смещений начала страниц.

### 8.4. Привязка к страницам (`align.py`)
Монотонное выравнивание: документ и PDF идут в одном порядке, поэтому поиск — с курсором вперёд, без квадратичного перебора.
1. Для каждого абзаца тела по порядку берётся ключ: первые 40 нормализованных символов `full_text` (короче 8 символов — пропуск, страница интерполируется). Автономер включается, т.к. LibreOffice его рендерит.
2. Поиск ключа в общей строке начиная с курсора в окне (курсор + 20 000 симв.); точное вхождение → страница по смещению, курсор сдвигается. Нет точного — `rapidfuzz.fuzz.partial_ratio_alignment` в том же окне, порог в `thresholds.py`. Не найден — абзац помечается непривязанным, курсор не двигается.
3. Таблицы: та же процедура для текста первой и последней непустой ячейки (по порядку строк) → `first_page`, `last_page`. Абзацы надписей и сносок в выравнивании не участвуют (их место в PDF непредсказуемо).
4. Непривязанные абзацы получают страницу интерполяцией между соседями (если соседи на одной странице — она же; иначе — страница предыдущего). `coverage` = доля привязанных напрямую.
5. Абзацы оглавления выравниваются тоже (они в начале и их текст повторяет заголовки — поэтому курсор не позволяет заголовку «Введение» сматчиться с пунктом оглавления).

### 8.5. Откат
Вёрстка считается неудавшейся, если: soffice не найден; ненулевой код / нет PDF; таймаут; ошибка pypdfium2; `coverage < LAYOUT_MIN_COVERAGE` (по умолчанию 0,6; ниже 0,85 — `status="partial"`, проверки по страницам дают максимум «подозрение»). Тогда `Document.layout = None`, причина — в `meta.warnings` и в отчёте:
- VOL-01 → оценка `layout/estimate.py`: страницы = символы с пробелами основной части / `CHARS_PER_PAGE` (1800, ориентир для 14 pt, 1,5 интервала, полей 3/1,5) + строки таблиц × `TABLE_ROW_PAGE_SHARE` + рисунки × `IMAGE_PAGE_SHARE`; итог помечен «оценка», максимум «подозрение» (поведение SPEC §0 п.1 в исходной редакции). Метод оценки фиксируется в отчёте (UI-03).
- TBL-10 → эвристика по числу строк/объёму текста (подозрение); разрывы коротких таблиц и номера страниц оглавления → «не проверяется кодом» с причиной.
- В отчёте всегда (и при успехе) — оговорка «вёрстка LibreOffice может расходиться с Word на 1–2 стр.»; допуски для проверок по страницам задаются в `thresholds.py` (`PAGE_TOLERANCE`).

## 9. Безопасность и данные (кратко; риски — ARCHITECTURE_TASKS.md)
- Файлы живут только в `TemporaryDirectory` запроса; удаление в `finally`, включая ошибки и таймауты; soffice-профиль — внутри того же temp dir. В Docker `/tmp` — tmpfs, файлы не попадают на диск хоста.
- Логи: имя файла (обрезанное), размер, длительность этапов, статус вёрстки. Никакого текста документа, цитат и находок; трассировки исключений — без значений локальных переменных; клиенту — только код и человекочитаемое сообщение.
- Документ никогда не инициирует сетевые запросы (lxml `no_network`, внешние связи вырезаются до LibreOffice). Сервис работает офлайн (SPEC §5).
- Server-режим: общий пароль из `VKR_PASSWORD`, только через HTTPS-прокси; лимит размера тела на уровне прокси и приложения. Если сервис откроют третьим лицам или начнут хранить работы — стоп, вопрос к legal-counsel (SPEC §7).
- Публичный репо: в коде — пересказ правил и короткие подсказки; фамилии в паттернах и тестах — только вымышленные; `local_corpus/` и исходные требования — в `.gitignore` с первого коммита.
