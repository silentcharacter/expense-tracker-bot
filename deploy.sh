#!/usr/bin/env bash
set -euo pipefail

PROJECT="expense-bot-489609"
FUNCTION="expense-bot"
REGION="asia-southeast1"
RUNTIME="python312"
ENTRY_POINT="webhook"
SERVICE_ACCOUNT="expense-bot-sa@${PROJECT}.iam.gserviceaccount.com"
WEBHOOK_BASE="https://${REGION}-${PROJECT}.cloudfunctions.net/${FUNCTION}"

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
  --memory=256MB \
  --timeout=60s \
  --service-account="$SERVICE_ACCOUNT"

BOT_TOKEN=$(grep TELEGRAM_BOT_TOKEN .env.yaml | cut -d'"' -f2)

echo ""
echo "=== Setting Telegram webhook ==="
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook?url=${WEBHOOK_BASE}" | python3 -m json.tool

echo ""
echo "Deploy complete: ${WEBHOOK_BASE}"
