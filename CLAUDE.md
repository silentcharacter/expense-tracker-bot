cat > CLAUDE.md << 'EOF'
# Expense Tracker Telegram Bot

## Project
Multi-user Telegram bot for expense tracking.
Voice/text input → Gemini Flash (audio→JSON) → Google Sheets.
Hosting: Google Cloud Functions. Full architecture: docs/expense-bot-architecture.html

## Stack
- Python 3.12, asyncio
- python-telegram-bot (async)
- Google Gemini 2.0 Flash (google-genai SDK)
- Google Sheets API (gspread)
- Google Drive API (googleapiclient)
- Google Cloud Functions (2nd gen)
- Pydantic for data models

## Structure
expense-bot/
├── main.py              # Cloud Function entry point
├── handlers/            # Telegram message handlers
├── services/            # Business logic (gemini, sheets, user_registry, currency)
├── models/              # Pydantic models
├── tests/               # pytest
├── requirements.txt
└── .env.yaml

## Coding Rules
- Type hints on all functions
- Async: all I/O operations use async/await
- Pydantic: for all data models and validation
- Tests: pytest + pytest-asyncio, test real logic, avoid unnecessary mocks
- Docstrings: concise, in English
- Error handling: try/except with logging, graceful degradation
- Env vars: via os.environ, never hardcode values

## Currency Model
- base_currency and default_currency are per-user settings
- ISO 4217 validation on registration
- amount_base = amount converted to user's base currency
EOF