# vkr-checker: LibreOffice нужен для вёрстки (ARCHITECTURE.md §2.3).
# Liberation Serif/Sans метрически совместимы с Times New Roman/Arial, Carlito/Caladea - с
# Calibri/Cambria: без них вёрстка «уезжает» на десятки страниц. Шрифты Microsoft не ставим (лицензия).
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    HOME=/tmp/app \
    VKR_HOST=0.0.0.0 \
    VKR_PORT=8000

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libreoffice-writer-nogui \
      fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core \
      fontconfig \
 && fc-cache -f \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
# Без uv.lock (до первой фиксации зависимостей) ставим по pyproject; с ним - строго по замку.
RUN \
    if [ -f uv.lock ]; then uv sync --frozen --no-dev --no-install-project; \
    else uv sync --no-dev --no-install-project; fi

COPY src ./src
COPY frontend ./frontend
COPY api ./api
RUN \
    if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi

RUN useradd --system --uid 10001 --home-dir /tmp/app --shell /usr/sbin/nologin app
USER app
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('VKR_PORT','8000'), timeout=4).status == 200 else 1)"]

CMD ["vkr-checker"]
