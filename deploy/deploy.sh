#!/usr/bin/env bash
# Выкладка/обновление vkr-checker на psy-ign.ru — БЕЗ sudo, от пользователя из группы docker.
#   bash ~/vkr-checker/deploy/deploy.sh        (обновляет до develop и перезапускает контейнер)
# nginx и сертификат ставятся один раз отдельно: sudo bash ~/vkr-checker/deploy/install-nginx.sh
set -euo pipefail

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
docker compose -p vkr-checker -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break
  sleep 2
done
if ! curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null; then
  echo "сервис не поднялся"
  docker compose -p vkr-checker logs --tail 50
  exit 1
fi
echo "контейнер работает: http://127.0.0.1:$PORT ($(git rev-parse --short HEAD))"
