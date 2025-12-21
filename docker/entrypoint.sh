#!/usr/bin/env bash
set -euo pipefail

cd /app/astra_app/

if [[ "${DJANGO_AUTO_MIGRATE:-1}" == "1" ]]; then
  echo "[entrypoint] Running migrations (with retry)..."
  for i in $(seq 1 "${DJANGO_MIGRATE_RETRIES:-30}"); do
    if python manage.py migrate --noinput; then
      break
    fi
    echo "[entrypoint] migrate failed; retry ${i}/${DJANGO_MIGRATE_RETRIES:-30} in 2s"
    sleep 2
  done
fi

exec "$@"
