# Setup webhook
curl "https://api.telegram.org/bot$(grep TELEGRAM_BOT_TOKEN .env.yaml | cut -d'"' -f2)/setWebhook?url=https://asia-southeast1-expense-bot-489609.cloudfunctions.net/expense-bot"

# Удали webhook (иначе polling не работает)
curl "https://api.telegram.org/bot$(grep TELEGRAM_BOT_TOKEN .env.yaml | cut -d'"' -f2)/deleteWebhook"

# Запусти бота локально
python run_local.py

# Run tests
# Run all tests
.venv/bin/pytest -v
# Run integration tests
.venv/bin/pytest -v -m integration
# Run unit tests
.venv/bin/pytest -v -m unit
# Run tests with verbose output
.venv/bin/pytest -v -v
# Run tests with detailed output
.venv/bin/pytest -v -v -v
# Run specific test file
.venv/bin/pytest tests/test_gemini_integration.py -m integration -v

# Check currency rates
curl "https://v6.exchangerate-api.com/v6/$(grep EXCHANGE_RATE_API_KEY .env.yaml | cut -d'"' -f2)/pair/THB/USD"

# Deploy Cloud Function (bot + API)
gcloud functions deploy expense-bot \
  --gen2 \
  --runtime=python312 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=webhook \
  --trigger-http \
  --allow-unauthenticated \
  --env-vars-file=.env.yaml \
  --memory=256MB \
  --timeout=60s \
  --service-account=expense-bot-sa@expense-bot-489609.iam.gserviceaccount.com

# Deploy Mini App to GCS (static files)
./deploy_mini_app.sh                       # default bucket: expense-bot-mini-app
./deploy_mini_app.sh my-custom-bucket      # custom bucket name
