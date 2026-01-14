#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/etc/astra/astra.env"

if [[ $# -ne 1 ]]; then
  echo "Usage: $(basename "$0") <sha256|sha256:hash|image@sha256:hash>" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

if [[ -z "${APP_IMAGE:-}" ]]; then
  echo "APP_IMAGE is not set in $ENV_FILE" >&2
  exit 1
fi

digest_input="$1"
new_image=""

if [[ "$digest_input" == sha256:* ]]; then
  digest="$digest_input"
elif [[ "$digest_input" =~ ^[0-9a-fA-F]{64}$ ]]; then
  digest="sha256:$digest_input"
else
  new_image="$digest_input"
fi

if [[ -z "$new_image" ]]; then
  if [[ "$APP_IMAGE" == *@* ]]; then
    base_image="${APP_IMAGE%@*}"
  elif [[ "${APP_IMAGE##*/}" == *:* ]]; then
    base_image="${APP_IMAGE%:*}"
  else
    base_image="$APP_IMAGE"
  fi
  new_image="${base_image}@${digest}"
fi

if grep -q "^APP_IMAGE=" "$ENV_FILE"; then
  sed -i "s|^APP_IMAGE=.*|APP_IMAGE=${new_image}|" "$ENV_FILE"
else
  echo "APP_IMAGE=${new_image}" >> "$ENV_FILE"
fi

/usr/local/bin/deploy-prod.sh
