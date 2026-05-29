#!/usr/bin/env bash
set -euo pipefail

PROJECT="expense-bot-489609"
FUNCTION="expense-bot"
REGION="asia-southeast1"
RUNTIME="python312"
ENTRY_POINT="webhook"
SERVICE_ACCOUNT="expense-bot-sa@${PROJECT}.iam.gserviceaccount.com"
# Use the Cloud Run URL (run.app). Gen2 also exposes cloudfunctions.net, but that
# alias can return 503 while run.app is healthy for the same revision.
WEBHOOK_BASE="$(gcloud functions describe "${FUNCTION}" --gen2 --project="${PROJECT}" --region="${REGION}" --format='value(serviceConfig.uri)' 2>/dev/null || true)"
if [ -z "${WEBHOOK_BASE}" ]; then
  WEBHOOK_BASE="https://${REGION}-${PROJECT}.cloudfunctions.net/${FUNCTION}"
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
  --env-vars-file=.env.yaml \
  --memory=512MB \
  --cpu=1 \
  --timeout=60s \
  --min-instances=1 \
  --service-account="$SERVICE_ACCOUNT"

BOT_TOKEN=$(grep TELEGRAM_BOT_TOKEN .env.yaml | cut -d'"' -f2)

echo ""
echo "=== Setting Telegram webhook ==="
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook?url=${WEBHOOK_BASE}" | python3 -m json.tool

echo ""
echo "Deploy complete: ${WEBHOOK_BASE}"
