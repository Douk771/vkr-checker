# vkr-checker

Сервис проверки ВКР (магистратура, 37.04.01 Психология) на соответствие требованиям методички и чек-листу целостности, плюс сравнение двух версий работы. Только детерминированные проверки кодом, без LLM.

## Возможности

- **Проверка** одного `.docx`: структура, оформление таблиц, нумерация, введение, согласованность чисел, методики, гипотеза, лексика, задачи; матрица «гипотеза - теория - методика - расчёт - результат - вывод» с выгрузкой в `.xlsx`.
- **Сравнение** двух версий: изменения по разделам и абзацам, перемещения, числа, таблицы и рисунки, влияние правок на выводы, динамика замечаний.
- Контракт API: `api/openapi.yaml` и `API_CONTRACT.md`. Устройство: `ARCHITECTURE*.md`.

## Запуск

Требуется Python 3.10+ (в Docker 3.12) и LibreOffice (`soffice`) для проверок по страницам. Без него отчёт строится с оценкой объёма, а проверки, зависящие от вёрстки, получают статус «не проверено».

### Local (на своём компьютере)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
vkr-checker            # http://127.0.0.1:8000
```

Пароль не нужен, слушается только 127.0.0.1.

### Server

```bash
VKR_MODE=server VKR_PASSWORD='...' vkr-checker
```

Без `VKR_PASSWORD` процесс не стартует. Вход: `POST /api/session`, cookie `vkr_session` (HttpOnly, SameSite=Strict) или заголовок `Authorization: Bearer`. Неудачные входы ограничены по IP. Хост по умолчанию 0.0.0.0; за прокси включайте `VKR_TRUST_PROXY=true`.

### Docker

```bash
docker compose up --build
```

Контейнер работает под non-root с read-only корнем, LibreOffice внутри образа; healthcheck - `/api/health`.

## Переменные окружения

Полный список с примерами - `.env.example`. Основные:

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `VKR_MODE` | `local` | `local` или `server` |
| `VKR_PASSWORD` | - | обязателен в `server` |
| `VKR_HOST`, `VKR_PORT` | 127.0.0.1 / 8000 | адрес |
| `VKR_SOFFICE_PATH` | поиск в PATH | путь к `soffice` |
| `VKR_LAYOUT_TIMEOUT_S` | 20 | таймаут вёрстки |
| `VKR_MAX_UPLOAD_MB` | 20 | размер файла |
| `VKR_MAX_CONCURRENT_JOBS` | 2 | слоты (check = 1, compare = 2), не меньше 2 |
| `VKR_CHECK_TIMEOUT_S`, `VKR_COMPARE_TIMEOUT_S` | 90 / 150 | таймауты запросов |
| `VKR_SESSION_TTL_H` | 12 | срок сессии |

## Тесты и утилиты

```bash
pytest                                   # unit + contract
python scripts/build_fixtures.py         # синтетические .docx в tests/fixtures/generated
python scripts/profile_pipeline.py       # время check/compare на 150 стр. (--profile)
python scripts/measure_layout.py         # время вёрстки LibreOffice
python scripts/calibrate.py [каталог]    # распределения мер по local_corpus/*.docx
```

## Оговорки

- Проверки детерминированные, без LLM; часть пунктов методички кодом не проверяется - они перечислены в блоке «Не проверяется кодом» каждого отчёта.
- Номера страниц берутся из вёрстки LibreOffice и могут отличаться от Word; при сбое вёрстки объём оценивается по символам и помечается как оценка.
- Загруженные файлы не сохраняются: обработка во временном каталоге, который удаляется после ответа.
- Реальные работы и методичка (`*.docx`, `*.pdf`, `local_corpus/`) в репозиторий не коммитятся.
- Калибровка порогов и тесты - только на синтетике.
