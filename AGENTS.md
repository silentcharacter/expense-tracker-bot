# Expense Tracker Telegram Bot

## Project
Multi-user Telegram bot for expense tracking with a Telegram Mini App dashboard.
Voice/text input → Gemini Flash (audio→JSON) → Firestore.
Mini App (React SPA) → REST API → same Firestore data.
Hosting: Google Cloud Functions (bot + API), GCS static hosting (Mini App).
Full architecture: docs/expense-bot-architecture.html

## Stack

### Backend
- Python 3.12, asyncio
- python-telegram-bot (async)
- Google Gemini 2.0 Flash (google-genai SDK)
- Google Cloud Firestore (google-cloud-firestore)
- Google Cloud Functions (2nd gen), functions-framework
- Pydantic for data models
- aiohttp (currency API client)

### Mini App (Frontend)
- React 18, TypeScript
- Vite 5 (build + dev server)
- Tailwind CSS
- Recharts (charts/analytics)
- React Router (HashRouter)
- Telegram WebApp SDK

## Structure
```
expense-bot/
├── main.py                  # Cloud Function entry: webhook + /api/* routing + CORS
├── handlers/                # Telegram message handlers
│   ├── commands.py          #   /start, /cat, /last, /undo, /export, /settings, /email, /broadcast
│   ├── text.py              #   Plain text → Gemini → expense
│   ├── voice.py             #   Voice OGG → Gemini → expense
│   └── callbacks.py         #   Inline keyboard callbacks (confirm/edit/cancel, currency)
├── api/                     # Mini App REST API
│   └── routes.py            #   /api/summary, /api/expenses, /api/budgets, /api/settings
├── services/                # Business logic
│   ├── gemini.py            #   Gemini Flash: audio/text → structured JSON
│   ├── firestore_service.py #   Firestore CRUD (transactions, categories, users, recurring)
│   ├── storage.py           #   Storage backend factory (STORAGE_BACKEND env var)
│   ├── sheets.py            #   Legacy Sheets backend (STORAGE_BACKEND=sheets)
│   ├── user_registry.py     #   Registration, user provisioning
│   ├── currency.py          #   FX rates (ExchangeRate-API) with 24h cache
│   └── auth.py              #   Telegram Mini App initData HMAC validation
├── models/                  # Pydantic models
│   ├── expense.py           #   Expense, ExpenseRecord, User, enums (ExpenseSource, UserRole)
│   └── category.py          #   Category/subcategory registry
├── mini-app/                # Telegram Mini App (React SPA)
│   ├── src/
│   │   ├── api/             #   API client (summary, expenses, budgets, settings)
│   │   ├── pages/           #   Dashboard, Analytics, Budget, History, Settings
│   │   ├── components/      #   analytics/, dashboard/, layout/, shared/
│   │   ├── context/         #   ThemeContext, UserContext
│   │   ├── hooks/           #   useSummary, useTelegram
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
├── tests/                   # pytest + pytest-asyncio
│   ├── test_api.py          #   Mini App API routes
│   ├── test_auth.py         #   initData validation
│   ├── test_budget_alerts.py
│   ├── test_recurring_cron.py
│   ├── test_firestore_integration.py  # requires Firestore emulator
│   ├── test_currency_integration.py   # requires EXCHANGE_RATE_API_KEY env var
│   ├── test_gemini_integration.py     # requires GOOGLE_API_KEY env var
│   └── test_config.yaml     #   non-secret test config (committed)
├── scripts/
├── docs/                    # Architecture, deployment, local dev guides
├── specs/                   # Product/technical specs
├── deploy.sh                # gcloud functions deploy wrapper
├── deploy_mini_app.sh       # Build + upload SPA to GCS
├── run_local.py             # Local bot polling with .env.yaml
├── run_dev.py               # Dev orchestration: API + Vite + ngrok
├── requirements.txt
└── .env.yaml
```

## Running Tests

```bash
# All tests — integration tests skip gracefully if emulator not running
pytest

# With Firestore emulator (Java 21+ required) — integration tests run fully
JAVA_HOME=/opt/homebrew/opt/openjdk@21 firebase emulators:start --only firestore --project expense-bot-489609
pytest
```

tests/test_config.yaml is committed to the repo and contains all required keys
(FIRESTORE_EMULATOR_HOST, GOOGLE_API_KEY, EXCHANGE_RATE_API_KEY).

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

## Mini App API
- Auth: `Authorization: tma <initData>` header, HMAC validated via bot token
- Single Cloud Function serves both Telegram webhook (POST /) and Mini App REST (/api/*)
- Endpoints: GET/PUT /api/settings, GET /api/summary, GET /api/expenses, DELETE /api/expenses/:id, GET/PUT /api/budgets
- CORS enabled for cross-origin Mini App requests
