#!/usr/bin/env bash
# Выкладка/обновление vkr-checker на psy-ign.ru — БЕЗ sudo, от пользователя из группы docker.
#   bash ~/vkr-checker/deploy/deploy.sh        (обновляет до develop и перезапускает контейнер)
# nginx и сертификат ставятся один раз отдельно: sudo bash ~/vkr-checker/deploy/install-nginx.sh
set -euo pipefail

# Всё тело в { … }: bash разбирает блок целиком до выполнения, поэтому git reset ниже,
# переписывающий этот же файл, не ломает уже запущенный скрипт.
{

REPO=https://github.com/Douk771/vkr-checker.git
BRANCH=${BRANCH:-develop}
DIR=${DIR:-$HOME/vkr-checker}
PORT=8010

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch --quiet origin "$BRANCH"
  git -C "$DIR" checkout --quiet "$BRANCH"
  git -C "$DIR" reset --quiet --hard "origin/$BRANCH"
else
  git clone --quiet --branch "$BRANCH" "$REPO" "$DIR"
fi

cd "$DIR"
COMPOSE=(docker compose -p vkr-checker -f docker-compose.yml -f deploy/docker-compose.prod.yml)
REV=$(git rev-parse HEAD)
STAMP="$HOME/.vkr-checker-deployed"

# Код не менялся и контейнер жив — пересборка не нужна (и сеть тоже).
if [ "$(cat "$STAMP" 2>/dev/null)" = "$REV" ] && curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null; then
  echo "уже развёрнута эта версия ($(git rev-parse --short HEAD)), пересборка не нужна"
  exit 0
fi

# DNS роутера на первом запросе отвечает медленно: прогреваем кэш и повторяем сборку.
getent hosts auth.docker.io registry-1.docker.io ghcr.io >/dev/null 2>&1 || true
built=0
for attempt in 1 2 3; do
  if "${COMPOSE[@]}" build; then built=1; break; fi
  echo "сборка не удалась (попытка $attempt из 3), повтор через 15 с"
  sleep 15
  getent hosts auth.docker.io registry-1.docker.io ghcr.io >/dev/null 2>&1 || true
done
[ "$built" -eq 1 ] || { echo "образ не собрался"; exit 1; }
"${COMPOSE[@]}" up -d
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break
  sleep 2
done
if ! curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null; then
  echo "сервис не поднялся"
  "${COMPOSE[@]}" logs --tail 50
  exit 1
fi
echo "$REV" > "$STAMP"
echo "контейнер работает: http://127.0.0.1:$PORT ($(git rev-parse --short HEAD))"
exit 0
}
