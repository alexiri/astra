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

digest_input="$1"
digest_input_normalized="${digest_input,,}"
new_image=""

if [[ "$digest_input_normalized" == sha256:* ]]; then
  digest="$digest_input_normalized"
elif [[ "$digest_input_normalized" =~ ^[0-9a-f]{64}$ ]]; then
  digest="sha256:$digest_input_normalized"
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

set_env_value "APP_IMAGE" "$new_image"

/usr/local/bin/deploy-prod.sh
