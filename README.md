# Expense Tracker Bot

A multi-user Telegram bot for personal expense tracking. Users send voice messages or text in natural language; the bot transcribes and parses them into structured expense records via Gemini. A Telegram Mini App provides a dashboard for analytics, budget management, and expense history.

---

## Problem Statement

Manually logging expenses is friction-heavy — opening a spreadsheet mid-day, remembering category names, typing amounts. The goal was to make recording an expense as fast as sending a voice note, while still producing structured, queryable data across multiple independent users.

---

## Solution Statement

The bot accepts voice (OGG) and free-form text, routes both through Gemini Flash (multimodal LLM), and extracts a structured `Expense` object (amount, currency, category, subcategory, note). The record is confirmed via inline keyboard and written to Firestore. A React Mini App embedded in Telegram surfaces the same data with charts, per-category budgets, and spending pace projections — all authenticated via Telegram's `initData` HMAC.

---

## Architecture

```
User
 │
 ├─ Voice/Text message
 │       │
 │       ▼
 │   Telegram Webhook (POST /)
 │       │
 │       ▼
 │   Google Cloud Function  (Python 3.12, asia-southeast1)
 │       │
 │       ├─ handlers/voice.py ──► Gemini 2.5 Flash Lite  ──► Expense JSON
 │       ├─ handlers/text.py  ──► Gemini 2.5 Flash Lite  ──► Expense JSON
 │       │                                                      │
 │       │   Inline keyboard confirm/edit/cancel ◄──────────────┘
 │       │                                   │
 │       │                                   ▼
 │       │                           Firestore (or Sheets*)
 │       │
 │       ├─ /api/* routes ──► Mini App REST API
 │       │       │
 │       │       ├─ GET  /api/summary       (spending totals + pace)
 │       │       ├─ GET  /api/expenses      (paginated history)
 │       │       ├─ DELETE /api/expenses/:id
 │       │       ├─ GET/PUT /api/budgets
 │       │       ├─ GET/PUT /api/settings
 │       │       ├─ GET/PUT /api/categories (custom categories)
 │       │       └─ GET/PUT/DELETE /api/recurring
 │       │
 │       └─ /cron/* routes ──► Cloud Scheduler jobs
 │               ├─ /cron/recurring      (daily: materialise recurring expenses)
 │               └─ /cron/weekly_summary (weekly: per-user Telegram digest)
 │
 ├─ Telegram Mini App  (React SPA, served from GCS)
 │       ├─ Overview tab   — category breakdown, daily heatmap
 │       ├─ Trends tab     — period-over-period bar charts
 │       └─ Budget tab     — per-category budgets, spending pace
 │
 └─ Error tracking: Sentry (sentry-sdk[gcp])

* STORAGE_BACKEND=sheets falls back to legacy Google Sheets; default is firestore
```

**Auth flow (Mini App):** The Mini App passes Telegram's `initData` as `Authorization: tma <initData>`. The Cloud Function validates the HMAC using the bot token before serving any `/api/*` route.

---

## Key Features

- **Natural language input** — voice (OGG) and text messages parsed by Gemini into structured expense records (amount, currency, category, note).
- **Multi-user** — each Telegram user gets their own isolated data; `/start` auto-provisions the account. Admin role for broadcast and user management.
- **Telegram Mini App** — embedded React SPA with three tabs: Overview (category breakdown, daily heatmap), Trends (period charts), Budget (category budgets + pace). Supports expense deletion from the UI.
- **Spending pace projection** — API computes a projected month-end total from daily averages, split by fixed (recurring) vs discretionary spend.
- **Budget alerts** — inline Telegram notifications when a category crosses 80% or 100% of its monthly budget.
- **Recurring expenses** — templates stored in Firestore; a daily Cloud Scheduler job materialises them as real `ExpenseRecord` entries (idempotent).
- **Weekly digest** — Cloud Scheduler sends per-user spending summaries via Telegram every week (opt-in).
- **Multi-currency** — per-user `base_currency` + `default_currency`; FX rates fetched from ExchangeRate-API with 24-hour in-memory cache; all amounts normalised to `amount_base`.
- **Firestore backend** — migrated from Google Sheets (v1) to Firestore for reliability; legacy Sheets backend still available via `STORAGE_BACKEND=sheets`.
- **Sentry error tracking** — GCP integration initialised on cold start from `SENTRY_DSN`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Bot framework | python-telegram-bot ≥ 21 (async webhook) |
| LLM / STT | Google Gemini 2.5 Flash Lite (`google-genai ≥ 1.0`) |
| Primary storage | Google Cloud Firestore (`google-cloud-firestore ≥ 2.16`) |
| Legacy storage | Google Sheets (`gspread ≥ 6`) |
| Hosting | Google Cloud Functions 2nd gen, `asia-southeast1` |
| Scheduler | Google Cloud Scheduler → `/cron/*` HTTP routes |
| Data models | Pydantic v2 |
| HTTP client | aiohttp (currency API) |
| Error tracking | Sentry SDK for GCP (`sentry-sdk[gcp] ≥ 2.0`) |
| Mini App | React 18, TypeScript, Vite 5, Tailwind CSS, Recharts |
| Mini App auth | Telegram `initData` HMAC validation |
| Mini App hosting | Google Cloud Storage (static SPA) |

---

## Setup

### Prerequisites

- Python 3.12
- Node 18+ (Mini App build)
- A Google Cloud project with Cloud Functions, Firestore, and Cloud Scheduler enabled
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A free API key from [exchangerate-api.com](https://www.exchangerate-api.com/)
- A [Google AI Studio](https://aistudio.google.com/) API key (Gemini)
- (Optional) A [Sentry](https://sentry.io/) DSN for error tracking

### 1. Clone and install

```bash
git clone <repo>
cd expense-bot
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.yaml` and fill in your values:

```yaml
TELEGRAM_BOT_TOKEN: "<your_telegram_bot_token>"
TELEGRAM_WEBHOOK_SECRET: "<random_secret_for_webhook>"
GOOGLE_API_KEY: "<your_gemini_api_key>"
EXCHANGE_RATE_API_KEY: "<your_exchangerate_api_key>"
STORAGE_BACKEND: "firestore"           # or "sheets"
TIMEZONE: "Europe/Berlin"              # your local timezone
CRON_SECRET: "<random_secret_for_cron_auth>"
SENTRY_DSN: ""                         # optional

# Firestore (if STORAGE_BACKEND=firestore)
# Credentials come from the Cloud Function's service account — no extra key needed.

# Sheets legacy backend (if STORAGE_BACKEND=sheets)
TEMPLATE_SHEET_ID: ""
REGISTRY_SHEET_ID: ""
USERS_FOLDER_ID: ""
ADMIN_EMAIL: ""
GOOGLE_OAUTH_CLIENT_ID: ""
GOOGLE_OAUTH_CLIENT_SECRET: ""
GOOGLE_OAUTH_REFRESH_TOKEN: ""
```

### 3. Run locally

```bash
python run_local.py        # bot polling + local API server
# or
python run_dev.py          # API + Vite dev server + ngrok tunnel
```

### 4. Run tests

```bash
# Unit + integration (integration tests skip if emulator is offline)
pytest

# With Firestore emulator (Java 21+ required)
JAVA_HOME=/opt/homebrew/opt/openjdk@21 \
  firebase emulators:start --only firestore --project expense-bot-489609
pytest
```

### 5. Deploy

```bash
# Deploy Cloud Function
./deploy.sh

# Build and upload Mini App to GCS
./deploy_mini_app.sh
```

### 6. Configure Cloud Scheduler

Create two jobs pointing at your function URL:

| Schedule | Endpoint | Description |
|---|---|---|
| `0 9 * * *` (daily) | `POST /cron/recurring` | Materialise recurring expenses |
| `0 9 * * 1` (weekly) | `POST /cron/weekly_summary` | Send weekly spending digests |

Set the `X-Cron-Secret` header to the value of `CRON_SECRET` for both jobs.
