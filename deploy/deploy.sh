#!/usr/bin/env bash
# Выкладка vkr-checker на сервер psy-ign.ru (Ubuntu, nginx уже стоит).
# Запуск на сервере под root:  bash deploy.sh   (повторный запуск = обновление до develop)
set -euo pipefail

REPO=https://github.com/Douk771/vkr-checker.git
BRANCH=${BRANCH:-develop}
DIR=/opt/vkr-checker
DOMAIN=psy-ign.ru
EMAIL=${CERTBOT_EMAIL:-}

if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  apt-get update
  apt-get install -y docker.io docker-compose-v2
  systemctl enable --now docker
fi

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch --quiet origin "$BRANCH"
  git -C "$DIR" checkout --quiet "$BRANCH"
  git -C "$DIR" reset --quiet --hard "origin/$BRANCH"
else
  git clone --quiet --branch "$BRANCH" "$REPO" "$DIR"
fi

# Открытый доступ без пароля: режим local, порт только на loopback, наружу — через nginx.
cd "$DIR"
docker compose -p vkr-checker up -d --build
for _ in $(seq 1 60); do
  curl -sf http://127.0.0.1:8000/api/health >/dev/null && break
  sleep 2
done
curl -sf http://127.0.0.1:8000/api/health >/dev/null || { echo "сервис не поднялся"; docker compose -p vkr-checker logs --tail 50; exit 1; }

# Конфиг nginx ставится только при первой выкладке: дальше в него дописывает HTTPS certbot,
# и перезапись при обновлении сломала бы сертификат.
if [ ! -e "/etc/nginx/sites-available/$DOMAIN.conf" ]; then
  install -m 644 "$DIR/deploy/nginx/$DOMAIN.conf" "/etc/nginx/sites-available/$DOMAIN.conf"
  ln -sf "/etc/nginx/sites-available/$DOMAIN.conf" "/etc/nginx/sites-enabled/$DOMAIN.conf"
  nginx -t
  systemctl reload nginx
fi

if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
  command -v certbot >/dev/null || apt-get install -y certbot python3-certbot-nginx
  if [ -n "$EMAIL" ]; then
    certbot --nginx --non-interactive --agree-tos -m "$EMAIL" --redirect -d "$DOMAIN" -d "www.$DOMAIN"
  else
    certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email --redirect \
      -d "$DOMAIN" -d "www.$DOMAIN"
  fi
fi
echo "готово: https://$DOMAIN"
