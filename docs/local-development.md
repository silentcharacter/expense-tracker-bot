# Local Development

Step-by-step guide to running the bot and Mini App locally.

---

## Prerequisites

| Tool | Version | Installation |
|------|---------|-------------|
| Python | 3.12+ | [python.org](https://www.python.org/downloads/) or `brew install python@3.12` |
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) or `brew install node` |
| ngrok | any | [ngrok.com/download](https://ngrok.com/download) or `brew install ngrok/ngrok/ngrok` |
| gcloud CLI | (optional) | [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) — for deployment |

---

## 1. Initial Setup

### 1.1 Clone and create virtual environment

```bash
git clone <repo-url> && cd expense-bot

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 1.2 Environment variables

Copy the template and fill in real values:

```bash
cp .env.yaml.example .env.yaml
```

Minimum required variables for local development:

| Variable | Where to get |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/newbot` or `/mybots` |
| `GOOGLE_API_KEY` | [AI Studio](https://aistudio.google.com/app/apikey) |
| `REGISTRY_SHEET_ID` | ID of the user registry Google Spreadsheet |
| `TEMPLATE_SHEET_ID` | ID of the template Spreadsheet for new users |
| `USERS_FOLDER_ID` | ID of the Google Drive folder for user spreadsheets |
| `ADMIN_EMAIL` | Email of the spreadsheet owner |
| `SA_EMAIL` | Service Account email |
| `GOOGLE_OAUTH_*` | OAuth2 credentials for Drive (see `expense-bot-setup-guide.html`) |
| `EXCHANGE_RATE_API_KEY` | [exchangerate-api.com](https://www.exchangerate-api.com/) |

Detailed instructions for obtaining all keys: [`docs/expense-bot-setup-guide.html`](expense-bot-setup-guide.html).

### 1.3 Service Account credentials

Place the `credentials.json` file (GCP Service Account key) in the project root. This file is listed in `.gitignore`.

### 1.4 ngrok — authenticate (one time)

```bash
# Sign up at https://dashboard.ngrok.com and copy your authtoken
ngrok config add-authtoken <YOUR_TOKEN>
```

### 1.5 ngrok — static domain (recommended)

By default ngrok assigns a random URL on every restart, which means you'd need to update BotFather each time. To avoid this, claim a **free static domain**:

1. Go to [dashboard.ngrok.com/domains](https://dashboard.ngrok.com/domains)
2. Click **New Domain** — you'll get a domain like `your-name-something.ngrok-free.app`
3. Add it to `.env.yaml`:

```yaml
NGROK_DOMAIN: "your-name-something.ngrok-free.app"
```

Now `run_dev.py` will always use this domain. Set it once in BotFather and never touch it again.

Alternatively, pass it via CLI flag:

```bash
python run_dev.py --domain your-name-something.ngrok-free.app
```

---

## 2. Running Locally

The project has two scripts for local development:

| Script | What it starts | When to use |
|--------|---------------|-------------|
| `run_local.py` | Telegram bot in polling mode | Bot development (commands, voice, text) |
| `run_dev.py` | API + Mini App + ngrok | Mini App development |

### 2.1 Bot only (polling)

```bash
source .venv/bin/activate
python run_local.py
```

The script:
- Loads `.env.yaml` into environment
- Deletes the webhook (polling and webhook are mutually exclusive)
- Starts the bot — you can message it in Telegram

Stop with `Ctrl+C`.

### 2.2 Mini App + API + ngrok (full stack)

```bash
source .venv/bin/activate
python run_dev.py              # uses NGROK_DOMAIN from .env.yaml (or random URL)
python run_dev.py --domain … # override with a specific domain
```

The script starts three services:

```
┌─────────────────────────────────────────────────────────┐
│  Telegram WebView                                       │
│  opens Mini App via ngrok URL                           │
└───────────────┬─────────────────────────────────────────┘
                │ HTTPS
                ▼
┌───────────────────────────┐
│  ngrok tunnel             │
│  https://xxxx.ngrok.io    │──────────────────┐
│  → localhost:5173         │                  │
└───────────────┬───────────┘                  │
                │                              │
                ▼                              │
┌───────────────────────────┐                  │
│  Vite dev server  :5173   │                  │
│  React Mini App           │                  │
│  /api/* → proxy           │──────┐           │
└───────────────────────────┘      │           │
                                   ▼           │
                        ┌──────────────────┐   │
                        │ functions-       │   │
                        │ framework  :8080 │   │
                        │ Python API       │   │
                        │ (/api/*)         │   │
                        └──────────────────┘   │
                                               │
  run_local.py (separate terminal)             │
  Telegram bot (polling)  ◄────────────────────┘
                                    (optional)
```

After startup, the script prints the ngrok URL — set it in BotFather (see section 3).

To run the bot alongside, start it in a **separate** terminal:

```bash
source .venv/bin/activate
python run_local.py
```

Stop with `Ctrl+C` in each terminal.

### 2.3 Running components individually

If you need to run components separately (e.g. for debugging):

**Terminal 1 — API:**

```bash
source .venv/bin/activate
# Load environment variables
export GOOGLE_APPLICATION_CREDENTIALS=credentials.json
export $(python -c "
import yaml
with open('.env.yaml') as f:
    d = yaml.safe_load(f)
for k,v in d.items():
    if v is not None: print(f'{k}={v}')
")

# Start the API server
python -m functions_framework --target=webhook --port=8080 --debug
```

**Terminal 2 — Mini App:**

```bash
cd mini-app
npm install   # first time only
npm run dev
```

**Terminal 3 — ngrok:**

```bash
ngrok http 5173                                          # random URL
ngrok http 5173 --domain your-name-something.ngrok-free.app  # static domain
```

---

## 3. Configuring Telegram for Mini App

### 3.1 Set up the Menu Button in BotFather

1. Open [@BotFather](https://t.me/BotFather)
2. `/mybots` → select your bot → **Bot Settings** → **Menu Button**
3. Set the URL: ngrok URL from `run_dev.py` output (e.g. `https://your-name-something.ngrok-free.app`)
4. Set the button text (e.g. "Dashboard")

> If you configured a static domain in `NGROK_DOMAIN` (see section 1.5), this is a one-time setup.
> Without a static domain, the URL changes on every restart and must be updated in BotFather each time.

### 3.2 Opening the Mini App

After setting up the Menu Button:
- Open the bot chat in Telegram
- Tap the menu button at the bottom (next to the message input)
- The Mini App opens in Telegram WebView with real `initData`

For debugging on desktop Telegram: right-click the WebView → **Inspect Element** (built-in DevTools).

---

## 4. Testing

### 4.1 Python tests

```bash
source .venv/bin/activate

# All tests
pytest -v

# Unit tests only
pytest -v -m unit

# Integration tests only
pytest -v -m integration

# Specific file
pytest tests/test_api.py -v

# Verbose output, stop on first failure
pytest -v -s -x
```

### 4.2 Mini App — typecheck

```bash
cd mini-app
npm run typecheck
```

### 4.3 Testing the API with curl

With `functions-framework` running on port 8080:

```bash
# Health check (should return 401 without auth)
curl -s http://localhost:8080/api/summary | python -m json.tool

# With test initData (to verify response format)
curl -s -H "Authorization: tma test" http://localhost:8080/api/settings | python -m json.tool
```

---

## 5. VS Code / Cursor

Debug configurations are defined in `.vscode/launch.json`:

| Configuration | What it does |
|--------------|-------------|
| **Run Bot Locally** | Runs `run_local.py` (bot in polling mode) |
| **Run Dev Environment** | Runs `run_dev.py` (API + Mini App + ngrok) |
| **Debug Current Test File** | Runs the current test file via pytest |

Select a configuration in the Run & Debug panel (`Ctrl+Shift+D` / `Cmd+Shift+D`).

---

## 6. Project Structure

```
expense-bot/
├── main.py               # Cloud Function entry point (webhook + /api/*)
├── run_local.py           # Local bot runner (polling)
├── run_dev.py             # Local Mini App + API + ngrok runner
├── requirements.txt       # Python dependencies
├── .env.yaml              # Secrets (not committed)
├── .env.yaml.example      # Secrets template
├── credentials.json       # SA key (not committed)
│
├── handlers/              # Telegram message handlers
├── services/              # Business logic (gemini, sheets, currency, auth)
├── models/                # Pydantic models
├── api/                   # REST API for Mini App
│   └── routes.py          # /api/summary, /api/expenses, /api/budgets, /api/settings
├── tests/                 # pytest
│
├── mini-app/              # React Mini App (Vite + TypeScript + Tailwind)
│   ├── src/
│   │   ├── api/           # API client (fetch + tma auth)
│   │   ├── components/    # UI components
│   │   ├── pages/         # Pages (Dashboard, History, Settings)
│   │   ├── hooks/         # React hooks
│   │   └── utils/         # Utilities
│   ├── package.json
│   └── vite.config.ts     # Vite config (proxy /api → localhost:8080)
│
├── docs/                  # Documentation
│   ├── local-development.md       # ← this file
│   ├── expense-bot-architecture.html
│   ├── expense-bot-setup-guide.html
│   ├── claude-code-workflow.md
│   └── manual.cmd                 # Command cheat sheet
│
└── specs/                 # Feature specifications
```

---

## 7. Troubleshooting

### ngrok fails to start

```
Error: ngrok exited immediately
```

**Solution:** authenticate ngrok:

```bash
ngrok config add-authtoken <TOKEN>
```

Get your token at [dashboard.ngrok.com](https://dashboard.ngrok.com/get-started/your-authtoken).

### Port already in use

```
Error: listen tcp 127.0.0.1:8080: bind: address already in use
```

**Solution:** kill the process occupying the port:

```bash
lsof -ti:8080 | xargs kill
# or for port 5173:
lsof -ti:5173 | xargs kill
```

### Mini App shows 401 Unauthorized

The API requires an `Authorization: tma <initData>` header — this is only available inside the Telegram WebView. Opening the Mini App in a regular browser will result in 401 for all API requests.

**Solution:** open the Mini App through Telegram (Menu Button), not directly in a browser.

### Bot not responding in polling mode

```
Webhook deleted: {"ok":true,"result":true,"description":"Webhook was deleted"}
Bot started in polling mode.
```

But the bot is silent.

**Check:**
- Correct `TELEGRAM_BOT_TOKEN` in `.env.yaml`
- Bot is not blocked (try `/start`)
- No other running instance (two polling processes conflict with each other)

### `credentials.json` not found

```
FileNotFoundError: credentials.json
```

**Solution:** download the Service Account key from GCP Console → IAM → Service Accounts → Keys → Add Key → JSON. Place the file in the project root as `credentials.json`.
