#!/usr/bin/env bash
# Build the Mini App and deploy static files to Google Cloud Storage.
#
# Prerequisites:
#   - gcloud CLI authenticated (gcloud auth login)
#   - Node.js and npm installed
#   - mini-app/.env.production with VITE_API_URL set
#
# Usage:
#   ./deploy_mini_app.sh                     # default bucket: expense-bot-mini-app
#   ./deploy_mini_app.sh my-custom-bucket    # custom bucket name

set -euo pipefail

BUCKET="${1:-expense-bot-mini-app}"
MINI_APP_DIR="$(cd "$(dirname "$0")/mini-app" && pwd)"

echo "=== Mini App Deploy ==="
echo "Bucket: gs://$BUCKET"
echo ""

# 1) Install dependencies
echo "[1/5] Installing dependencies..."
cd "$MINI_APP_DIR"
npm ci --silent

# 2) Build
echo "[2/5] Building Mini App..."
if [ -f .env.production ]; then
  echo "      Using .env.production"
else
  echo "      WARNING: .env.production not found — VITE_API_URL will be empty."
  echo "      Create mini-app/.env.production with:"
  echo "        VITE_API_URL=https://your-cloud-function-url"
  echo ""
fi
npm run build

# 3) Create bucket if needed
echo "[3/5] Ensuring bucket exists..."
if ! gsutil ls "gs://$BUCKET" &>/dev/null; then
  gsutil mb -l asia-southeast1 "gs://$BUCKET"
  echo "      Created gs://$BUCKET"
else
  echo "      gs://$BUCKET already exists"
fi

# 4) Configure bucket for static website hosting
echo "[4/5] Configuring bucket..."
gsutil web set -m index.html -e index.html "gs://$BUCKET"
gsutil iam ch allUsers:objectViewer "gs://$BUCKET"

# 5) Upload build
echo "[5/6] Uploading dist/ to gs://$BUCKET..."
gsutil -m -h "Cache-Control:public,max-age=3600" cp -r dist/* "gs://$BUCKET/"
# index.html should not be cached aggressively (it references hashed assets)
gsutil -h "Cache-Control:no-cache,max-age=0" cp dist/index.html "gs://$BUCKET/index.html"

URL="https://storage.googleapis.com/$BUCKET/index.html"

# Copy URL to clipboard for pasting into BotFather Main App URL
if command -v pbcopy &>/dev/null; then
  echo -n "$URL" | pbcopy
  echo "      URL copied to clipboard ✓"
elif command -v xclip &>/dev/null; then
  echo -n "$URL" | xclip -selection clipboard
  echo "      URL copied to clipboard ✓"
fi

echo ""
echo "=== Done ==="
echo "Mini App URL: $URL"
echo ""
echo "Update Main App URL in BotFather (cannot be automated):"
echo "  https://t.me/BotFather → /editapp → Edit Web App URL → paste"