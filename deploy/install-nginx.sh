#!/usr/bin/env bash
# Один раз: сайт psy-ign.ru в nginx и сертификат Let's Encrypt. Запуск: sudo bash install-nginx.sh
# Существующие сайты nginx не трогаются: добавляется отдельный файл psy-ign.ru.conf.
set -euo pipefail

DOMAIN=psy-ign.ru
SRC="$(cd "$(dirname "$0")" && pwd)/nginx/$DOMAIN.conf"
DST="/etc/nginx/sites-available/$DOMAIN.conf"

[ "$(id -u)" -eq 0 ] || { echo "запустите через sudo"; exit 1; }

# Конфиг ставится, только если его ещё нет: после certbot в нём HTTPS-блок,
# и перезапись сломала бы сертификат.
LINK="/etc/nginx/sites-enabled/$DOMAIN.conf"
if [ ! -e "$DST" ]; then
  install -m 644 "$SRC" "$DST"
  ln -sf "$DST" "$LINK"
fi
# если конфиг не проходит проверку — отключаем только этот сайт, чтобы не сломать соседние
if ! nginx -t; then
  rm -f "$LINK"
  echo "конфиг $DOMAIN не прошёл nginx -t, сайт отключён, остальные сайты не тронуты"
  exit 1
fi
systemctl reload nginx

if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
  command -v certbot >/dev/null || apt-get install -y certbot python3-certbot-nginx
  certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email --redirect \
    -d "$DOMAIN" -d "www.$DOMAIN"
fi
echo "готово: https://$DOMAIN"
