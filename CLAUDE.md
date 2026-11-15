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
│   ├── trips.py             #   /trip (start/end/list) + trip inline callbacks
│   ├── quick.py             #   Quick-expense reply keyboard, /quick, presses, "⚡ Quick button"
│   ├── expense_saving.py    #   Shared convert → save → alert → confirmation card
│   ├── text.py              #   Plain text → Gemini → expense
│   ├── voice.py             #   Voice OGG → Gemini → expense
│   └── callbacks.py         #   Inline keyboard callbacks (confirm/edit/cancel, currency)
├── api/                     # Mini App REST API
│   └── routes.py            #   /api/summary, /api/expenses, /api/budgets, /api/settings, /api/trips
├── services/                # Business logic
│   ├── gemini.py            #   Gemini Flash: audio/text → structured JSON
│   ├── firestore_service.py #   Firestore CRUD (transactions, categories, users, recurring)
│   ├── storage.py           #   Storage backend factory (STORAGE_BACKEND env var)
│   ├── sheets.py            #   Legacy Sheets backend (STORAGE_BACKEND=sheets)
│   ├── user_registry.py     #   Registration, user provisioning
│   ├── currency.py          #   FX rates (ExchangeRate-API) with 24h cache
│   ├── trip_service.py      #   Active-trip resolution and per-trip totals
│   └── auth.py              #   Telegram Mini App initData HMAC validation
├── models/                  # Pydantic models
│   ├── expense.py           #   Expense, ExpenseRecord, User, enums (ExpenseSource, UserRole)
│   ├── category.py          #   Category/subcategory registry
│   ├── trip.py              #   Trip (named date range tagged onto expenses)
│   └── quick_expense.py     #   QuickExpense (one-tap preset shown as a chat button)
├── utils/
│   └── timeutil.py          #   Per-user timezone: user_today/user_now, get_user_timezone
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
│   ├── test_trips.py        #   Trip model, trip_service, /api/trips, /trip command
│   ├── test_quick_expenses.py #  Quick expenses: model, bot flow, /api/quick-expenses
│   ├── test_recurring_cron.py
│   ├── test_timeutil.py     #   Per-user timezone, "just after local midnight" scenarios
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

## Dates & Timezones
- Never use bare `date.today()`, `datetime.now()` or `datetime.utcnow()`: Cloud Functions run
  in UTC, so near midnight the server day differs from the user's. Use `utils/timeutil.py`.
- The user's zone is a bot setting: `User.timezone` (IANA name), stored on the Firestore user
  doc `users/{telegram_id}.timezone` (Sheets backend: `timezone` column of the Registry sheet).
  Set via `/settings timezone Europe/Kyiv` or `PUT /api/settings {"timezone": ...}`;
  `""` / `/settings timezone default` resets it.
- Resolution (`timeutil.get_user_timezone(user)`): user setting → `TIMEZONE` env →
  `Asia/Bangkok`. Invalid values fall through to the next level.
- "Today", week/month boundaries, pace, budgets, exports, trips and both crons use
  `timeutil.user_today(user)` / `user_now(user)`. Crons iterate users and use each user's day.
  The zone-less `timeutil.today()` is only a fallback where no user exists.
- Storage: datetimes are written tz-aware UTC (`timeutil.utc_now()`); legacy naive values are
  read as UTC. The day of an expense is `record.local_date(user)`, never `timestamp.date()`.
  Date-range reads pass the user: `storage.get_transactions(..., since, until, tz=user)`.
  Manually dated / recurring expenses are stored as local midnight (`timeutil.start_of_day`).
- The API serialises expense timestamps in the user's zone (ISO with offset), so the Mini App's
  `timestamp.slice(0, 10)` is the user's local day.
- Tests freeze the clock by patching `utils.timeutil._utc_now`.

## Currency Model
- base_currency and default_currency are per-user settings
- ISO 4217 validation on registration
- amount_base = amount converted to user's base currency

## Trips
- A trip is a scope tag, not a category: an expense keeps `food/restaurant` and
  additionally carries `trip_id` (empty string = regular/home expense).
- `users/{id}/trips/{trip_id}` holds the registry; `User.active_trip_id` points at
  the trip new expenses are tagged with, and is cleared automatically once that
  trip ends or is deleted (`services/trip_service.resolve_active_trip`).
- The recurring cron never tags its expenses — rent and subscriptions keep running
  at home while the user travels.
- Monthly budgets, budget alerts and the spending pace count trip expenses like
  any other spending; `/api/budgets` additionally returns `total_spent_trip` so
  the Budget tab can show how much of the month came from trips. A trip also has
  its own optional `Trip.budget`, shown only inside the trip.
- Trip ids are 8 chars because they travel inside Telegram `callback_data` (64 bytes).
- Trips require `STORAGE_BACKEND=firestore`; the Sheets backend answers 501.

## Quick Expenses
- One-tap presets (`models/quick_expense.QuickExpense`), max 9, stored as the
  `quick_expenses` array on the user document (button order = array order).
  Firestore only; the Sheets backend answers 501 / "requires Firestore".
- Shown as a persistent reply keyboard (3 per row). A press arrives as plain text;
  `handle_text` sends messages starting with an emoji to `handlers/quick.py`,
  which matches the exact button text and saves without Gemini
  (`ExpenseSource.quick`). Presets with `amount=None` ask for the amount
  (`awaiting = "quick_amount:<id>"`). A press cancels any other pending prompt.
- The bot caches users in memory, so an unmatched emoji message triggers one
  fresh `find_user` before falling through to Gemini.
- "⚡ Quick button" under a saved expense turns it into a preset; `/quick` lists
  presets inline and shows/hides the keyboard (`User.quick_keyboard_hidden`).
- A reply keyboard only changes when a message carries it: `PUT /api/quick-expenses`
  makes the bot send one (`handlers.quick.send_keyboard_update`).

## Mini App API
- Auth: `Authorization: tma <initData>` header, HMAC validated via bot token
- Single Cloud Function serves both Telegram webhook (POST /) and Mini App REST (/api/*)
- Endpoints: GET/PUT /api/settings, GET /api/summary, GET /api/expenses, DELETE /api/expenses/:id, GET/PUT /api/budgets
- Trips: GET/POST /api/trips, PUT/DELETE /api/trips/:id, POST /api/trips/:id/assign, GET /api/trips/:id/summary
- Quick expenses: GET/PUT /api/quick-expenses (PUT replaces the whole list)
- Trip filters: `trip_id` on /api/summary, /api/expenses (`none` = home only) and /api/export
- CORS enabled for cross-origin Mini App requests
