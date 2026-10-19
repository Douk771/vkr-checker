# ARCHITECTURE_CHECKS: движок проверок, сравнение версий, матрица, отчёт

Версия 1.0, 2026-10-19. Продолжает [ARCHITECTURE.md](ARCHITECTURE.md): модель `Document`, `Location`, `Layout` берутся оттуда. Правила называются по ID из SPEC §4, их текст здесь не повторяется. Пороги лежат в `src/vkr_checker/thresholds.py` (§6), в тексте ниже они обозначены `ИМЕНЕМ_КАПСОМ`.

Разделы: 1. Модель находки · 2. Интерфейс правила и движок · 3. Слой фактов · 4. Реестр правил · 5. Сравнение версий (DIF) · 6. Пороги · 7. Матрица (MAT-01) · 8. Отчёт и NC-01.

---

## 1. Модель находки (`model/finding.py`, Pydantic v2: она же схема отчёта в openapi)

```
Level   = "violation" | "suspicion" | "not_checked"        # нарушение / подозрение / не проверяется кодом
Outcome = "passed" | "findings" | "not_run" | "not_checked" # итог правила целиком
Method  = "style" | "regex" | "morph" | "fuzzy" | "layout" | "estimate" | "count"

Finding
  id: str                 # стабильный: sha1(rule_id | fingerprint | порядковый № при совпадении)[:12]
  rule_id: str            # "TBL-01"
  title: str              # короткое название правила
  block: BlockId          # группа отчёта (SPEC §3.4), см. §8
  level: Level
  not_run: bool           # служебный статус «Проверка не выполнена» (SPEC §3.1), показывается как suspicion
  source: {doc: "M"|"CH", section: str}   # пересказ: «[Ч] Оформление таблиц»
  message: str            # с конкретными значениями
  values: dict[str, str|int|float|list]   # те же значения в структурированном виде (для diff, тестов, DIF-06)
  locations: list[Location]               # минимум одна, кроме глобальных (нет раздела → место = нет)
  count: int = 1          # >1 после схлопывания (§8.2)
  hint: str | None        # пересказ рекомендации [Ч]
  method: Method          # каким способом найдено (видно в отчёте: «по вёрстке», «оценка»)
  fingerprint: str        # якорь без номеров абзацев: rule_id + объект (подпись таблицы, ключ величины,
                          # заголовок раздела) + подвид. Нужен для DIF-06 и стабильного id
  origin: "rules"         # для будущего модуля моделей: "model:<name>"; формат отчёта не меняется

RuleResult
  rule_id, title, block, outcome, findings: list[Finding]
  artifacts: dict[str, Any]   # вспомогательные таблицы: INT-01 «элемент→место», TSK-01 «задача→вывод»,
                              # VOL-01 «объём по разделам», CON-01 «индекс чисел» (для NC-01)
  skipped_reason: str | None  # при not_run: «не найден §2.1»
```
Уровень находки задаёт правило. Движок может только понизить его (никогда не повышает): `violation → suspicion`, если `layout.status == "partial"` (для method=layout) или если раздел-источник распознан с `confidence < STRUCT_LOW_CONFIDENCE`.

## 2. Интерфейс правила и движок (`checks/base.py`, `checks/engine.py`)

```python
class Need(StrEnum):
    (
        INTRO,
        CH1,
        CH2,
        SUB_2_1,
        CONCLUSION,
        CH_CONCLUSIONS,
        TOC,
        BIBLIOGRAPHY,
        APPENDICES,
        TABLES,
        LAYOUT,
        LAYOUT_OR_ESTIMATE,
    )


class Rule(Protocol):
    id: str
    title: str
    block: BlockId
    source: Source
    default_level: Level
    needs: frozenset[Need]  # без чего правило не работает → движок ставит not_run сам
    priority: Literal["must", "should", "could"]

    def run(self, ctx: CheckContext) -> RuleResult: ...


@dataclass
class CheckContext:
    doc: Document
    facts: Facts  # ленивые кэшированные извлечения (§3), общие для правил, diff, матрицы
    th: Thresholds
    loc: LocationFactory  # обёртка над make_location (ARCHITECTURE.md §5)
```
- **Регистрация:** декоратор `@register` в модулях `checks/*.py`; `checks/registry.py` импортирует модули явно (без автосканирования, чтобы порядок был детерминированным). Порядок выполнения: по `rule_id` (каталог правил сортируется).
- **Движок:** для каждого правила (1) проверяет `needs` по `doc.sections`/`doc.layout`; если чего-то нет → `RuleResult(outcome="not_run")` и одна находка `not_run=True, level=suspicion` с текстом «не найден <фрагмент>, проверка <ID> пропущена». (2) Вызывает `run` в `try/except`. При исключении итог `not_run`, причина «внутренняя ошибка разбора», трассировка уходит только в лог без значений переменных. Сервис из-за этого не падает (SPEC §5 «Надёжность»). (3) Применяет понижение уровня (§1). (4) Схлопывает однотипные находки (§8.2). (5) Сортирует находки по ключу `(block_order, rule_id, first_location.paragraph_idx or 0, table_idx, fingerprint)`.
- **Без находок:** итог `passed`, в сводке правило попадает в список «пройдено».
- **Нет сайд-эффектов:** правило не меняет `doc`/`facts`. Факты считаются один раз (`functools.cached_property`), поэтому правила независимы и тестируются по отдельности на синтетике.
- **Точка расширения (LLM позже):** класс `ModelRule`, который реализует тот же `Rule` и возвращает `Finding(origin="model:…")`. HTTP, отчёт и DIF-06 при этом не меняются. В MVP не реализуется.

## 3. Слой фактов (`checks/facts/`, `nlp/`)

Факты — извлечения, которые используются больше чем в одном месте. Правила, diff и матрица берут их отсюда, а не извлекают заново.

| Факт | Модуль | Что содержит | Кто использует |
|---|---|---|---|
| `sentences` | `nlp/sentences.py` | разбиение на предложения (regex с защитой сокращений «и т.д.», «И.О.», «рис.», «табл.», «p < 0,05»), смещения в абзаце | все текстовые |
| `lemmas` | `nlp/morph.py` | pymorphy3 с LRU-кэшем по слову; `content_lemmas()` = без стоп-слов и без служебных глаголов задач («изучить», «выявить», «определить»…) | INT, HYP, TSK, STR-04, MAT |
| `quantities` | `facts/quantities.py` | `Quantity(kind, qualifier, value, unit, loc, section_kind)` | CON-01..04, DIF-03, DIF-05.1, MAT |
| `methods` | `facts/methods.py` + `nlp/lexicons/methods.py` | словарь: `id → {names (леммы, варианты написания), stat_patterns (regex)}`; вхождения с местом | MET-01, LEX-01, DIF-05.3, MAT |
| `intro_elements` | `facts/intro.py` | элемент → (абзац, позиция: `heading`/`para_start`/`sentence_start`/`inline`, текст элемента) | INT-01, HYP, TSK, MET-03, MAT, DIF-05.2 |
| `hypotheses` | `facts/hypothesis.py` | части гипотезы из введения; упоминания в гл.2/выводах/заключении; статус («подтверждена»…) | HYP-01, MAT, DIF-05.2 |
| `tasks`, `conclusions` | `facts/tasks.py` | задачи (автонумерация/«1)»), пункты заключения, положения на защиту | TSK-01, MAT, DIF-05.2 |
| `instruments` | `facts/instruments.py` | методики §2.1: название в кавычках, аббревиатура, авторы, адаптация | MET-02, MAT |
| `authors` | `facts/authors.py` | фамилии по шаблонам «И.О. Фамилия», «Фамилия И.О.», «Фамилия (год)», «[N]»; нормализация падежа фамилии через pymorphy3 (`Surn`) с запасным усечением окончания | MET-02..04, MAT |
| `refs` | `facts/refs.py` | ссылки «табл./таблица/рис./рисунок/приложение N» с учётом падежей, «(см. …)», диапазоны «табл. 2–4», ссылки на литературу «[N]», «[N, с. M]» | NUM-02, STR-05, DIF-05.4, BIB-01 |

**Тождество величин (риск SPEC §6 п.6).** Ключ величины: `(kind, qualifier)`.
- `kind`: `sample_n`, `age_min_max`, `age_mean`, `age_sd`, `percent_of:<лемма объекта>`, `group_n:<метка группы>`.
- `sample_n` присваивается только при якоре в ±1 предложении: «выборк», «респондент», «испытуем», «участник», «n/N =».
- `qualifier` ≠ ∅, если в том же предложении есть «групп», «подвыборк», «из них», «в том числе», «мужчин/женщин», «экспериментальн/контрольн». CON-01 сравнивает значения только при одинаковом ключе и `qualifier = ∅`. Поэтому подвыборки не дают ложных расхождений, это главный регулятор шума.

## 4. Реестр правил (SPEC → модуль → подход → уровень)

Модули лежат в `src/vkr_checker/checks/`. Подходы: **стиль** — эффективное форматирование (ARCHITECTURE.md §6.3); **рег** — регэксп; **морф** — леммы pymorphy3; **fuzzy** — rapidfuzz/difflib; **вёрстка** — `Layout`; **счёт** — подсчёт объектов модели. «Н» — нарушение, «П» — подозрение, «НК» — не проверяется кодом.

| ID | Модуль | Подход | Уровень по умолчанию | Нужно (`needs`) / примечание |
|---|---|---|---|---|
| STR-01 | `structure.py` | счёт по `Section.kind` | нет раздела → Н; порядок, число глав ≠ 2, нет титула → П | — |
| STR-02 | `structure.py` | fuzzy (`TocEntry.resolved_section_id`) | Н | TOC; сверяются только главы/параграфы уровня ≤ 2 |
| STR-06* | `structure.py` | вёрстка: `TocEntry.page_num` против `heading_pages` с допуском `PAGE_TOLERANCE` | расхождение > допуска → П (Word и LO расходятся) | TOC, LAYOUT; без вёрстки → НК |
| STR-03 | `structure.py` | `CHAPTER_CONCLUSIONS` + рег «^Выводы» в последних `CH_CONCL_TAIL_PARAS` абзацах главы | Н | CH1, CH2 |
| STR-04 | `structure.py` | fuzzy: `fuzz.ratio` по строкам лемм предложений ≥ `STR04_DUP_RATIO` | П | CONCLUSION, CH_CONCLUSIONS |
| STR-05 | `structure.py` | рег (заголовок), `starts_new_page`/вёрстка, `refs` | Н | APPENDICES; ссылки на приложения из основной части |
| PAGE-01 | `structure.py` | `page_setup` ± `MARGIN_TOL_CM` | Н | все `sectPr` основной части |
| INT-01 | `intro.py` | морф + рег: словарь элементов (пересказ), основы ключевых слов в начале абзаца/предложения | нет → Н; только `inline` → П; «внедрен…» без «Акт внедрения» → П; «Внедрение» → информационно (artifact) | INTRO; artifact `elements` |
| VOL-01 | `volume.py` | вёрстка (страницы INTRO..CONCLUSION) / откат `estimate` | вне `VOL_MIN..VOL_MAX` → П (никогда не Н) | LAYOUT_OR_ESTIMATE; artifact `by_section`, `method` |
| TBL-01 | `tables_format.py` | стиль: `first_line/hanging/left_cm` ≠ 0 (\|x\| > `INDENT_EPS_CM`) | Н | TABLES; подсказка из `origin` («пришло из стиля „Обычный“») |
| TBL-02 | `tables_format.py` | стиль: `line_rule=auto, line=1.0`, `space_after=0` | Н | TABLES |
| TBL-03 | `tables_format.py` | стиль: `layout_type=fixed`, сумма `grid_cols_cm` против `text_width_cm` ± `TBL_WIDTH_TOL_CM` | Н | TABLES |
| TBL-04 | `tables_format.py` | рег «№» в шапке + ширина ≤ `NUM_COL_MAX_CM`; самый широкий столбец — с max средней длиной текста | П | TABLES |
| TBL-05 | `tables_format.py` | стиль + классификатор ячейки: шапка (row 0 / `tblHeader`), номер, число (`^[\d\s,.\-–±<>=%*]+$`), текст | Н; для ячеек с долей цифр в `CELL_NUMERIC_GRAY` → П | TABLES |
| TBL-06 | `typography.py` | рег: число/символ + обычный пробел + единица/знак (`n = 17`, `p < 0,001`, `1,5 ч`), в тексте и ячейках | П | — ; схлопывание по абзацу/таблице |
| TBL-07 | `tables_format.py` | `height_rule=exact` и `height > ROW_EXACT_MAX_PT` | П | TABLES |
| TBL-08 | `tables_format.py` | стиль `keep_next` у подписи; у строк длинной (> `LONG_TABLE_ROWS`) таблицы | подпись → Н; строки длинной → П | TABLES |
| TBL-09 | `tables_format.py` | `style_exists == False` | Н | TABLES |
| TBL-10 | `tables_place.py` | вёрстка: таблица основной части занимает > 1 стр. (`last_page − first_page ≥ 1` и не только «перелив» ≤ `SPILL_MAX_ROWS` строк); откат: строки > `TBL10_ROWS_EST` | П | TABLES, LAYOUT_OR_ESTIMATE |
| TBL-11 | `tables_place.py` | рег по подписи/шапке (`M`, `SD`, `p`, «результат», «диагностик») + нет ссылки «приложени» в ±`NEAR_PARAS` абзацах | П | TABLES |
| TBL-12* | `tables_place.py` | вёрстка: таблица ≤ `SHORT_TABLE_ROWS` строк и `first_page ≠ last_page` | П (Н не ставим: расхождение LO/Word) | TABLES, LAYOUT; без вёрстки → НК |
| NUM-01 | `numbering.py` | счёт по `captions`: схема (сквозная/по главам) по большинству, смешение, пропуск/дубль/порядок, объект без подписи; отдельная схема для приложений | Н; `seq_field_stale_suspect` → П (SPEC §3.5) | — |
| NUM-02 | `numbering.py` | `refs` + морф (падежи «таблиц(е\|ы\|у)»); «далеко» = первая ссылка после объекта дальше `REF_FAR_PARAS` абзацев | нет ссылки / несуществующий номер → Н; далеко → П | — |
| NUM-03 | `numbering.py` | рег фразы («содержит/включает … N рисунков … M таблиц», также приложения и источники) | ≠ → Н; не найдено → П; «совпадает с приложениями» в тексте | — |
| CON-01 | `consistency.py` | рег + `quantities` (ключ §3) | П, все значения и места | — ; artifact `numbers_index` |
| CON-02 | `consistency.py` | рег M, min–max, SD в одном предложении/таблице | M вне диапазона → Н; M ± k·SD несовместимо с диапазоном (`SD_RANGE_K`) → П | — |
| CON-03 | `consistency.py` | рег процентов в перечислении/столбце «%»; оговорка «округл» в ±1 абзаце отключает | вне `100 ± PCT_TOL` → П; 98–102 → П «вероятно, округление» | — |
| CON-04 | `consistency.py` | морф: словарь способов деления (терцил, квартил, медиан, M ± σ, норм) у одних групп (общая лемма «групп» + метка) | П | — |
| MET-01 | `methods.py` | морф + рег статистик (`methods`) | введение ≠ §2.1 → Н; заявлен, но не применён / применён, но не заявлен → П | INTRO, SUB_2_1, CH2 |
| MET-02 | `methods.py` | рег методик (`instruments`) + поиск в гл.1 по названию/аббревиатуре (fuzzy ≥ `INSTR_MATCH`) и авторам | П | SUB_2_1, CH1 |
| MET-03 | `methods.py` | `intro_elements[теор.-метод. основания]` → `authors` + названия концепций → поиск в гл.1 | П | INTRO, CH1 |
| MET-04 | `methods.py` | `authors` обсуждения гл.2 минус `authors` гл.1 | П (Should) | CH1, CH2 |
| HYP-01 | `hypothesis.py` | морф (`content_lemmas`) + fuzzy (Жаккар лемм < `HYP_SIM_MIN` — расхождение); пословная подсветка difflib по леммам; статусы — рег | П | INTRO (гипотеза); упоминания в CH2/CONCLUSION |
| LEX-01 | `lexical.py` | морф: леммы глаголов причинности + маркеры связи (рег `r`, `rs`, `β`, `R²`, «корреляц», «регресс», «связь») в одном предложении | П | — |
| LEX-02 | `lexical.py` | морф «установить/выявить/доказать» (прич./глаг.) + `[N]`/фамилия/«по данным» в предложении; любые в выводах гл.1 | П | CONCLUSION / CH_CONCLUSIONS |
| LEX-03 | `lexical.py` | рег «возможно, вероятно, по-видимому, можно предположить» в CH2-результатах/выводах/заключении вне блока «ограничени|перспектив» | П (Should) | — |
| TSK-01 | `tasks.py` | морф + fuzzy: близость = взвешенный Жаккар `content_lemmas` (+ бонус за общие термины-биграммы); жадное сопоставление по убыванию близости | задача без вывода < `TSK_MATCH_MIN` → П; вывод без задачи → П; \|задач − выводов\| > `TSK_COUNT_DIFF` → П | INTRO (задачи), CONCLUSION; artifact `task_map` |
| BIB-01* | `bibliography.py` | `refs[N]` против `len(bibliography)`; непроцитированные источники | номер > длины → Н; не процитирован → П (Could, делать последним) | BIBLIOGRAPHY |
| NC-01 | `not_checked.py` | статический список + вспомогательные артефакты (§8.3) | НК, выводится всегда | — |

\* Новые ID, которых нет в SPEC. Их нужно согласовать с product-analyst. STR-06 (номера страниц оглавления) и TBL-12 (разрыв короткой таблицы) получились из пунктов NC-01, которые по решению заказчика §0 п.1 теперь проверяются вёрсткой. BIB-01 — это US-25 (Could). Если вёрстка не удалась, STR-06 и TBL-12 дают `outcome=not_checked` и одну находку НК с причиной.

**Блоки отчёта (`BlockId`, порядок SPEC §3.4):** structure (STR, PAGE-01), intro (INT-01), volume (VOL-01), tables (TBL-01..09, TBL-12), numbering (NUM, TBL-10/11, BIB-01), consistency (CON), methods (MET), hypothesis (HYP), wording (LEX), tasks (TSK), not_checked (NC-01). Служебный блок `recognized_structure` идёт отдельно и в счётчики не входит.

## 5. Сравнение версий (`diff/`, DIF-01…06)

Вход: два `Document` (+ их `Facts`) после полного конвейера. Выход: `DiffReport` (§8.1) и полный отчёт проверок новой версии. Бюджет: ≤ 10 с из 60 на ~1500 абзацев.

**5.1. Выравнивание разделов (`diff/sections.py`, DIF-01).** Дерево разделов разворачивается в список (уровни 1–2). Сопоставление идёт в три прохода, жадно по убыванию оценки, при равенстве выигрывает меньший индекс:
1. совпадают `kind` и нормализованный заголовок (без номера, нижний регистр, `ё→е`);
2. тот же `kind`/родитель и `fuzz.token_set_ratio(заголовки) ≥ SEC_RENAME_RATIO` → `renamed`;
3. содержимое: `token_set_ratio` по первым `SEC_CONTENT_CHARS` символам ≥ `SEC_CONTENT_RATIO` → `renamed` (по содержимому).
Несопоставленные разделы помечаются `added`/`removed`. Абзацы вне разделов (титул) образуют псевдораздел.

**5.2. Абзацы (`diff/paragraphs.py`).** Для каждой пары разделов выполняется `difflib.SequenceMatcher(autojunk=False)` по нормализованным хэшам абзацев. Блоки `replace` разбираются попарно: если `fuzz.ratio ≥ PARA_MODIFIED_RATIO`, это `modified` с пословным diff (SequenceMatcher по токенам, выход — список сегментов `equal|ins|del`), иначе `deleted` + `inserted`. Разделы без изменений помечаются `unchanged` (UI сворачивает их).

**5.3. Перемещения (`diff/moves.py`, DIF-02).** Глобальные пулы: все `deleted` (D) и все `inserted` (I) по всем разделам. Для абзацев D длиной ≥ `MOVE_MIN_CHARS` выполняется `rapidfuzz.process.extractOne(scorer=fuzz.ratio, score_cutoff=MOVE_RATIO·100)` по I, предварительно отфильтрованному по длине ±30%. Найденная пара → `moved(from_section, to_section, word_diff)`, оба абзаца убираются из пулов. Подряд идущие перемещения с подряд идущими целями склеиваются в одну запись-группу. Сложность O(|D|·|I|) на C-реализации укладывается в бюджет. Если окажется медленно, рядом есть индекс по 5-граммам слов (`diff/index.py`, опция).

**5.4. Числа (`diff/numbers.py`, DIF-03).** Для пар `modified`/`moved` числа в токенах заменяются плейсхолдером и токены выравниваются. Позиции, где отличается только число, дают `NumberChange(old, new, context, loc_old, loc_new, kind)`. `kind` берётся из `quantities` новой версии (тип и ключ §3) либо из рег статистик (`p`, `r`, `U`, `t`…). Типизированные изменения выводятся первыми.

**5.5. Таблицы (`diff/tables.py`, DIF-04).** Сопоставление: (1) номер и `fuzz.ratio(название) ≥ TBL_TITLE_RATIO`; (2) только название (так ловится перенумерация); (3) содержимое: Жаккар множеств текстов ячеек ≥ `TBL_CONTENT_JACCARD`. Внутри пары строки выравниваются SequenceMatcher по ключу «текст первой ячейки», затем сравниваются ячейки. Выход: `added|removed|renumbered|retitled`, изменения строк и ячеек `было → стало`. Рисунки сопоставляются так же по подписи (`diff/figures.py`, без содержимого).

**5.6. Анализ последствий (`diff/impact.py`, DIF-05).** Каждый сценарий — отдельная функция-правило с тем же интерфейсом `Finding` (block `diff_impact`, уровень П, `locations` = [место правки (старое + новое), …места без синхронизации]):

| № | Условие (в терминах 5.1–5.5 и фактов) |
|---|---|
| 1 | есть `NumberChange` с типизированным ключом K: old → new. В новой версии `quantities` с ключом K и значением old в абзаце, который `unchanged` → П «старое значение осталось» |
| 2 | якоря введения (`hypotheses`, `tasks`, цель/объект/предмет из `intro_elements`) изменились: сходство лемм старого и нового < `ANCHOR_CHANGED`. Их отражения в новой версии (упоминания гипотезы в CH2/заключении из HYP-01, сопоставленные выводы из TSK-01, выводы к главам) лежат в `unchanged` абзацах → П. Обратное направление: изменилось отражение, а введение — нет |
| 3 | `methods(old: INTRO ∪ SUB_2_1) − methods(new: INTRO ∪ SUB_2_1)` = удалённые. Вхождения их названий и `stat_patterns` в новой версии → П с местами |
| 4 | таблица/рисунок `removed` или `renumbered` (old_no → new_no). `refs` новой версии на old_no находятся в `unchanged` абзацах → П «ссылка, вероятно, на старый номер» |
| 5 | число таблиц или рисунков основной части изменилось, а абзац с фразой NUM-03 `unchanged` → П |
| 6 | в CH2 есть изменённые ячейки таблиц или типизированные `NumberChange`, а все абзацы выводов к гл.2 и заключения `unchanged` → мягкое П «проверьте, держатся ли выводы» (одна находка, перечислены изменения) |

**5.7. Динамика находок (`diff/dynamics.py`, DIF-06, Should).** Находки двух полных прогонов сопоставляются по `fingerprint` (в нём нет номеров абзацев, поэтому сдвиг текста не ломает сопоставление). Результат: `fixed` (только в старой), `new` (только в новой), `remaining` (в обеих). Для находок со схлопыванием сравнивается и `count`, при изменении — пометка «стало меньше/больше».

## 6. Пороги (`thresholds.py`)

Один `@dataclass(frozen=True) Thresholds` с значениями по умолчанию. `scripts/calibrate.py` прогоняет `local_corpus/` и печатает распределения мер близости, по ним правят числа. Логику при этом не трогают. Стартовые значения (калибруются):

| Порог | Знач. | Порог | Знач. |
|---|---|---|---|
| `INDENT_EPS_CM` | 0,01 | `STR04_DUP_RATIO` | 85 |
| `TBL_WIDTH_TOL_CM` | 0,2 (SPEC) | `HYP_SIM_MIN` | 0,7 |
| `MARGIN_TOL_CM` | 0,05 | `TSK_MATCH_MIN` | 0,25 |
| `NUM_COL_MAX_CM` | 1,5 | `TSK_COUNT_DIFF` | 2 |
| `CELL_NUMERIC_GRAY` | 0,3–0,7 | `INSTR_MATCH` | 85 |
| `ROW_EXACT_MAX_PT` | 28 | `REF_FAR_PARAS` | 15 |
| `LONG_TABLE_ROWS` | 15 | `NEAR_PARAS` | 3 |
| `SHORT_TABLE_ROWS` | 10 | `PCT_TOL` | 0,5 |
| `SPILL_MAX_ROWS` | 2 | `SD_RANGE_K` | 3 |
| `TBL10_ROWS_EST` | 25 | `SEC_RENAME_RATIO` / `SEC_CONTENT_RATIO` | 60 / 70 |
| `VOL_MIN` / `VOL_MAX` | 60 / 85 (SPEC) | `PARA_MODIFIED_RATIO` | 50 |
| `PAGE_TOLERANCE` | 2 стр. | `MOVE_RATIO` / `MOVE_MIN_CHARS` | 0,9 / 40 |
| `CHARS_PER_PAGE` | 1800 | `TBL_TITLE_RATIO` / `TBL_CONTENT_JACCARD` | 80 / 0,6 |
| `STRUCT_LOW_CONFIDENCE` | 0,5 | `ANCHOR_CHANGED` | 0,95 |
| `COLLAPSE_SHOW_LOCATIONS` | 5 | `NOISE_SUSPICION_BUDGET` | 50 |
| `CH_CONCL_TAIL_PARAS` | 40 | `MAT_THEORY_MIN` | 0,15 |

## 7. Матрица связности (`matrix/`, MAT-01)

**Модель (`matrix/model.py`, входит в JSON отчёта):**
```
Matrix: rows: list[MatrixRow], stats {rows, gaps, auto_cells}
MatrixRow: kind ("hypothesis_part" | "defense_position" | "task"), label («Гипотеза, ч.2», «Задача 3»),
           statement (текст), statement_loc, is_theoretical: bool,
           cells: {theory, instrument, calculation, result, conclusion} → MatrixCell
MatrixCell: status ("auto" | "gap" | "n/a"), text, candidates: list[str] (≤3), locations: list[Location]
```
**Строки** берутся из фактов `hypotheses` (части), `intro_elements["положения"]` (по пунктам списка или предложениям), `tasks`. Если источника нет (например, не найдена гипотеза), строк этого вида нет, а в `stats` пишется предупреждение со ссылкой на not_run соответствующего правила.

**Заполнение** (`matrix/build.py`). Ключевые слова строки — `content_lemmas(statement)`.
- **Теория:** подразделы гл.1 ранжируются по TF-IDF-косинусу лемм (IDF по подразделам гл.1). Берётся топ-1 при оценке ≥ `MAT_THEORY_MIN`, к нему до 3 фамилий из `authors` этого подраздела.
- **Методика:** методики из `instruments`. «Измеряемое понятие» — леммы названия методики плюс предложения §2.1 с её упоминанием. Выбирается методика с максимальным пересечением.
- **Расчёт:** таблицы и абзацы гл.2 с наибольшим пересечением ключевых слов → номер таблицы и методы (`methods`) в ней или в абзаце, где на неё ссылаются.
- **Результат:** статистики и числа (`r = …`, `p < …`, `U = …`) из найденного фрагмента расчёта.
- **Вывод:** для задач — `task_map` TSK-01; для частей гипотезы — упоминание со статусом в заключении (HYP-01); для положений — лучший вывод заключения той же мерой, что в TSK-01; плюс выводы к главам.
- `is_theoretical` (основы «проанализировать литератур», «теоретически обосновать», «раскрыть понятие») → «Методика» и «Расчёт» получают `n/a`. Пустые ячейки остальных строк получают статус `gap`.

**Скачивание:** `matrix/xlsx.py` (openpyxl) строит файл из JSON матрицы, который присылает клиент (см. API_CONTRACT.md). Лист «Матрица» содержит 6 столбцов SPEC + «Тип» + «Статус строки». Ячейки `auto` — курсив, жёлтая заливка и префикс «[авто, проверить] ». Ячейки `gap` — красная заливка и текст «РАЗРЫВ». `n/a` — серым «не требуется». Статус подписан словом, так что файл читается без цвета (SPEC §5). На листе «Места» для каждой ячейки указаны путь по заголовкам, номер абзаца и цитата. Ширины колонок и перенос строк заданы, закреплена первая строка.

## 8. Отчёт (`report/`)

**8.1. Корневая структура JSON (`report/schema.py`, Pydantic; шаг 3 переносит её в openapi как `CheckReport`/`CompareReport`):**
```
CheckReport
  schema_version: "1.0"; service_version; checked_at (ISO, единственное недетерминированное поле)
  file: {name, size_bytes, sha256}
  layout: {status: ok|partial|failed, engine, page_count, coverage, reason, font_substitutions[], disclaimer}
  volume: {method: layout|estimate, pages_main, by_section[{title, pages}], estimate_formula}
  structure: дерево {title, kind, number, detection, confidence, paragraph_idx, children[]}
  summary: {violation, suspicion, not_checked, not_run, passed_rules[], noise_warning: str|None}
  blocks: [{id, title, rule_results: [RuleResult]}]      # порядок §4
  not_checked: [NcItem]                                   # §8.3
  matrix: Matrix
  warnings: [str]                                         # парсинг, автонумерация, шрифты
CompareReport
  old: {file}, new: CheckReport
  diff: {sections[{status, old_title, new_title, paragraphs[{status, old_idx, new_idx, segments[]}]}],
         moves[], number_changes[], tables[], figures[], impact: [Finding], dynamics: {fixed[], new[], remaining[]}}
```

**8.2. Схлопывание и шум (`report/collapse.py`).** Ключ схлопывания — `(rule_id, объект, подвид)`. Объект — таблица, абзац или ключ величины. Подвид — например, «первая строка ≠ 0». Однотипные находки объединяются в одну: `count = N`, сообщение по шаблону «Таблица 3: красная строка в 42 ячейках», в `locations` первые `COLLAPSE_SHOW_LOCATIONS` мест, полный список — в `values.all_cells`. Если подозрений больше `NOISE_SUSPICION_BUDGET`, в `summary.noise_warning` выводится «много подозрений: проверьте блок „Распознанная структура“; пороги требуют калибровки». Находки при этом не обрезаются.

**8.3. NC-01 (`checks/not_checked.py`).** Статический список `NcItem(id, title, source, hint, helper)`. Пункты — пересказ SPEC §4 NC-01, у каждого id `NC-01.1…NC-01.10`. `helper` ссылается на вспомогательные данные отчёта: `numbers_index` (artifact CON-01: все числа с местами) — к пункту «числа сверены с файлом данных»; `matrix` — к пункту «каждая часть гипотезы проверяется расчётом»; `rule:MET-01`, `rule:MET-04`, `rule:TBL-09` — к соответствующим пунктам. Пункты «номера страниц в оглавлении» и «разрывы коротких таблиц» попадают в NC-01 **только при неудачной вёрстке**. Иначе их закрывают STR-06 и TBL-12 (решение заказчика §0 п.1). Каждый пункт NC-01 считается в `summary.not_checked`.

**8.4. Рендер.** Бэкенд отдаёт только JSON. HTML для показа и для скачивания — один шаблон `frontend/report_viewer.html` с вшитым JSON (ARCHITECTURE.md §1). В отчёте всегда показываются версия, дата, имена файлов, метод объёма (UI-03) и оговорка о расхождении LibreOffice и Word на 1–2 стр. `Location.page` выводится как «≈ стр. N (по вёрстке LibreOffice)» только при `layout.status = ok`. Это поле — расширение SPEC §3.3, его нужно подтвердить (ARCHITECTURE.md §5).

**8.5. Детерминизм и тесты.** Golden-тесты (`tests/golden/`): JSON отчёта синтетических работ без `checked_at` сравнивается побайтно. На каждое правило есть пара фикстур «чистая / с ошибкой» (SPEC §4), на каждый сценарий DIF-05 — пара версий. Эталонная чистая работа даёт 0 Н и 0 П (общий критерий SPEC).
