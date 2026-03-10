# Setup webhook
curl "https://api.telegram.org/bot$(grep TELEGRAM_BOT_TOKEN .env.yaml | cut -d'"' -f2)/setWebhook?url=https://asia-southeast1-expense-bot-489609.cloudfunctions.net/expense-bot"

# Удали webhook (иначе polling не работает)
curl "https://api.telegram.org/bot$(grep TELEGRAM_BOT_TOKEN .env.yaml | cut -d'"' -f2)/deleteWebhook"

# Запусти бота локально
python run_local.py