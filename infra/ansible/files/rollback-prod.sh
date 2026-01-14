#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/etc/astra/astra.env"
LAST_IMAGE_FILE="/etc/astra/last_app_image"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

if [[ ! -f "$LAST_IMAGE_FILE" ]]; then
  echo "Missing rollback image file $LAST_IMAGE_FILE" >&2
  exit 1
fi

rollback_image=$(cat "$LAST_IMAGE_FILE")
if [[ -z "$rollback_image" ]]; then
  echo "Rollback image is empty" >&2
  exit 1
fi

set_env_value() {
  local key="$1"
  local value="$2"
  local tmp_file

  tmp_file="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    $0 ~ "^" key "=" {
      print key "=" value
      found = 1
      next
    }
    { print }
    END {
      if (found == 0) {
        print key "=" value
      }
    }
  ' "$ENV_FILE" > "$tmp_file"
  mv "$tmp_file" "$ENV_FILE"
}

wait_for_unit() {
  local unit="$1"
  local timeout="${2:-300}"
  local elapsed=0

  while ! systemctl is-active --quiet "$unit"; do
    if (( elapsed >= timeout )); then
      systemctl status "$unit" --no-pager
      echo "Timed out waiting for $unit" >&2
      exit 1
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
}

set_env_value "APP_IMAGE" "$rollback_image"

podman pull "$rollback_image"

systemctl restart astra-app@1.service
wait_for_unit astra-app@1.service

systemctl restart astra-app@2.service
wait_for_unit astra-app@2.service
