#!/usr/bin/env bash
# Deploy the bot Cloud Function and (re)register the Telegram webhook.
#
# Secrets hygiene:
#   - Never run this script with `bash -x` / `set -x`: values from .env.yaml
#     (bot token, webhook secret) would be traced to the terminal/logs.
#   - The bot token is only ever placed in a curl config read from stdin
#     (`curl --config -`), so it does not appear in argv / `ps` output or in
#     shell history, and the Telegram response is filtered before printing.
#   - `gcloud functions deploy` is run with --format=none because its default
#     output dumps the deployed function, including environment variables.
#
# Webhook secret (TELEGRAM_WEBHOOK_SECRET):
#   Read from the environment or .env.yaml and passed to setWebhook as
#   `secret_token`. Telegram then sends it in the
#   X-Telegram-Bot-Api-Secret-Token header and main.py rejects requests
#   without it. Generate one with:
#     python3 -c "import secrets; print(secrets.token_urlsafe(32))"
set -euo pipefail
{ set +x; } 2>/dev/null

cd "$(dirname "$0")"

PROJECT="expense-bot-489609"
FUNCTION="expense-bot"
REGION="asia-southeast1"
RUNTIME="python312"
ENTRY_POINT="webhook"
SERVICE_ACCOUNT="expense-bot-sa@${PROJECT}.iam.gserviceaccount.com"
ENV_FILE=".env.yaml"

if [ ! -f "${ENV_FILE}" ]; then
  echo "ERROR: ${ENV_FILE} not found (copy .env.yaml.example and fill it in)." >&2
  exit 1
fi

# Read a top-level `KEY: "value"` (or unquoted) entry from .env.yaml without
# echoing it. Prints the value on stdout for command substitution only.
read_env_yaml() {
  local key="$1"
  sed -n -E "s/^${key}:[[:space:]]*\"?([^\"#]*[^\"#[:space:]])?\"?[[:space:]]*(#.*)?$/\1/p" "${ENV_FILE}" | head -n 1
}

# Prefer the process environment, fall back to .env.yaml.
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-$(read_env_yaml TELEGRAM_BOT_TOKEN)}"
WEBHOOK_SECRET="${TELEGRAM_WEBHOOK_SECRET:-$(read_env_yaml TELEGRAM_WEBHOOK_SECRET)}"

if [ -z "${BOT_TOKEN}" ]; then
  echo "ERROR: TELEGRAM_BOT_TOKEN is missing in env and ${ENV_FILE}." >&2
  exit 1
fi

if [ -n "${WEBHOOK_SECRET}" ]; then
  # Telegram allows 1-256 chars of A-Z, a-z, 0-9, '_' and '-'.
  if ! [[ "${WEBHOOK_SECRET}" =~ ^[A-Za-z0-9_-]{1,256}$ ]]; then
    echo "ERROR: TELEGRAM_WEBHOOK_SECRET has invalid format (allowed: 1-256 of A-Z a-z 0-9 _ -)." >&2
    exit 1
  fi
  if ! grep -q -E '^TELEGRAM_WEBHOOK_SECRET:' "${ENV_FILE}"; then
    echo "ERROR: TELEGRAM_WEBHOOK_SECRET is set in the shell but not in ${ENV_FILE}." >&2
    echo "       The function reads its env from ${ENV_FILE}; add it there so both sides match." >&2
    exit 1
  fi
else
  echo "WARNING: TELEGRAM_WEBHOOK_SECRET is not set — the webhook will NOT be authenticated."
  echo "         Generate one and add it to ${ENV_FILE}:"
  echo "           python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
  echo "           TELEGRAM_WEBHOOK_SECRET: \"<generated value>\""
  echo "         then re-run ./deploy.sh."
  echo ""
fi

echo "=== Deploying function ==="

gcloud functions deploy "$FUNCTION" \
  --gen2 \
  --project="$PROJECT" \
  --runtime="$RUNTIME" \
  --region="$REGION" \
  --source=. \
  --entry-point="$ENTRY_POINT" \
  --trigger-http \
  --allow-unauthenticated \
  --env-vars-file="$ENV_FILE" \
  --memory=512MB \
  --cpu=1 \
  --timeout=60s \
  --min-instances=1 \
  --service-account="$SERVICE_ACCOUNT" \
  --format=none

# Use the Cloud Run URL (run.app). Gen2 also exposes cloudfunctions.net, but that
# alias can return 503 while run.app is healthy for the same revision.
WEBHOOK_BASE="$(gcloud functions describe "${FUNCTION}" --gen2 --project="${PROJECT}" --region="${REGION}" --format='value(serviceConfig.uri)' 2>/dev/null || true)"
if [ -z "${WEBHOOK_BASE}" ]; then
  WEBHOOK_BASE="https://${REGION}-${PROJECT}.cloudfunctions.net/${FUNCTION}"
fi

echo ""
echo "=== Setting Telegram webhook ==="

# The token must be in the URL path (Telegram API design). Feed the URL and
# form fields to curl through a config on stdin so they never hit argv.
# Config-file strings are double-quoted; our values contain no quotes or
# backslashes (token/secret formats are validated/known, URL is ours).
SECRET_LINE=""
if [ -n "${WEBHOOK_SECRET}" ]; then
  SECRET_LINE="data-urlencode = \"secret_token=${WEBHOOK_SECRET}\""
fi
RESPONSE="$(
  curl --silent --show-error --max-time 30 --config - <<CURLCFG
url = "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook"
data-urlencode = "url=${WEBHOOK_BASE}"
${SECRET_LINE}
CURLCFG
)" || { echo "ERROR: setWebhook request failed (curl error)." >&2; exit 1; }
unset SECRET_LINE
unset BOT_TOKEN WEBHOOK_SECRET

# Print only the status fields; never the raw response.
printf '%s' "${RESPONSE}" | python3 -c '
import json, sys
try:
    r = json.load(sys.stdin)
except Exception:
    print("setWebhook: unparseable response"); sys.exit(1)
print("setWebhook ok=%s description=%s" % (r.get("ok"), r.get("description", "")))
sys.exit(0 if r.get("ok") else 1)
'

echo ""
echo "Deploy complete: ${WEBHOOK_BASE}"
