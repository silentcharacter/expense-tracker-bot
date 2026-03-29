# SPEC 13 — Telegram Mini App (Expense Dashboard)

> References: `docs/expense-bot-architecture.html` (Section 09, V3 Roadmap)
> This spec defines the Telegram Mini App — an interactive expense dashboard accessible directly inside Telegram.

---

## Overview

### What
A single-page web application (Telegram Mini App / TWA) that serves as a rich visual dashboard for the Expense Tracker Bot. Users open it via a button in the bot chat and get full analytics, charts, transaction history, budget management, and settings — all without leaving Telegram.

### Why
Bot commands (`/week`, `/month`, `/budget`) are limited to text output. The Mini App provides:
- Interactive charts and visual breakdowns
- Scrollable transaction history with filters
- Budget editing UI (impossible via bot commands)
- Category management
- Better UX for settings and currency selection

### How it's accessed
- **Menu Button**: persistent button in bot chat header (configured via BotFather `menubutton`)
- **Inline button**: bot can send a message with "📊 Open Dashboard" button that launches the Mini App
- **Direct link**: `t.me/your_bot/app`

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Framework | **React 18** + TypeScript | Component-based, rich ecosystem, fast dev |
| Build | **Vite** | Fast HMR, small bundles, ESM-native |
| Styling | **Tailwind CSS** | Utility-first, matches Telegram theme vars easily |
| Charts | **Recharts** | React-native, composable, lightweight |
| State | **React Context** + `useReducer` | No external state lib needed for this scale |
| API client | **fetch** (native) | No axios needed, tiny footprint |
| Telegram SDK | **@telegram-apps/sdk-react** | Official React bindings for Telegram Mini Apps |
| Hosting | **Google Cloud Storage** (static site) or **Cloud Functions** serving static | Same GCP project, no extra infra |
| Backend | Existing **Cloud Function** (`expense-bot`) | Add REST endpoints alongside webhook |

---

## Architecture

```
┌─────────────────────────────────────────┐
│           Telegram Client                │
│  ┌───────────────────────────────────┐  │
│  │      Mini App WebView (React)     │  │
│  │                                    │  │
│  │  ┌──────┐ ┌──────┐ ┌──────────┐  │  │
│  │  │Dashb.│ │Trans.│ │ Settings │  │  │
│  │  └──┬───┘ └──┬───┘ └────┬─────┘  │  │
│  │     └────────┼──────────┘         │  │
│  │              ▼                     │  │
│  │     REST API calls (fetch)        │  │
│  └──────────────┬────────────────────┘  │
│                 │                        │
└─────────────────┼────────────────────────┘
                  ▼
┌─────────────────────────────────────────┐
│  Cloud Function (expense-bot)            │
│                                          │
│  POST /webhook  ← existing Telegram bot  │
│  GET  /api/expenses?since=...&until=...  │
│  GET  /api/summary?period=week|month     │
│  GET  /api/budgets                       │
│  PUT  /api/budgets                       │
│  GET  /api/settings                      │
│  PUT  /api/settings                      │
│  DELETE /api/expenses/:id                │
│                                          │
│  Auth: Telegram initData validation      │
└──────────────┬───────────────────────────┘
               ▼
┌──────────────────────────┐
│  Google Sheets (per-user) │
│  + Master Registry        │
└──────────────────────────┘
```

---

## Authentication

Telegram Mini Apps pass `initData` — a signed string containing user info, verified via bot token. No passwords, no OAuth for the user.

### Flow
1. Mini App opens → Telegram injects `initData` into `window.Telegram.WebApp.initData`
2. Every API request includes header: `Authorization: tma <initData>`
3. Cloud Function validates signature using `TELEGRAM_BOT_TOKEN` (HMAC-SHA256)
4. Extracts `user.id` (telegram_id) from validated data
5. Looks up user in registry → gets `spreadsheet_id`
6. Serves data from user's personal Spreadsheet

### Validation (server-side)

```python
import hashlib
import hmac
from urllib.parse import parse_qs

def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Validate Telegram Mini App initData.
    Returns parsed data dict if valid, None if invalid.
    
    Algorithm (from Telegram docs):
    1. Parse init_data as query string
    2. Extract 'hash' parameter, remove it from params
    3. Sort remaining params alphabetically
    4. Build data_check_string: "key=value\nkey=value\n..."
    5. secret_key = HMAC-SHA256("WebAppData", bot_token)
    6. Compute HMAC-SHA256(secret_key, data_check_string)
    7. Compare with hash
    """
```

### Security rules
- **Every** API endpoint validates initData (no exceptions)
- initData has `auth_date` — reject if older than 1 hour
- User can only access their own Spreadsheet (telegram_id from initData → registry lookup)
- No API key or token stored in frontend code

---

## REST API Endpoints

All endpoints are added to the existing Cloud Function alongside the Telegram webhook.

### Routing

```python
@functions_framework.http
def webhook(request: flask.Request) -> tuple[str, int]:
    path = request.path
    
    # Existing webhook
    if request.method == "POST" and path == "/":
        return handle_telegram_update(request)
    
    # Mini App API
    if path.startswith("/api/"):
        user = authenticate_mini_app(request)  # validates initData
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        return handle_api(request, user)
    
    return "not found", 404
```

### `GET /api/summary`

Returns aggregated expense data for a period.

**Query params:**
- `period`: `today` | `week` | `month` | `year` (required)
- `compare`: `true` | `false` — include previous period comparison (default: false)

**Response:**
```json
{
  "period": "week",
  "date_range": {
    "start": "2026-03-10",
    "end": "2026-03-16"
  },
  "total_base": 245.30,
  "base_currency": "USD",
  "transaction_count": 18,
  "daily_average": 35.04,
  "by_category": [
    {
      "category": "food",
      "amount_base": 98.50,
      "percentage": 40.2,
      "transaction_count": 8
    }
  ],
  "by_currency": [
    {
      "currency": "THB",
      "amount_local": 6500.00,
      "amount_base": 188.40
    }
  ],
  "daily_totals": [
    {"date": "2026-03-10", "amount_base": 42.10},
    {"date": "2026-03-11", "amount_base": 28.50}
  ],
  "comparison": {
    "previous_total": 312.00,
    "change_percent": -21.4,
    "direction": "down"
  }
}
```

### `GET /api/expenses`

Returns paginated transaction list.

**Query params:**
- `since`: ISO date (optional)
- `until`: ISO date (optional)
- `category`: filter by category (optional)
- `limit`: max results, default 50, max 200
- `offset`: pagination offset, default 0

**Response:**
```json
{
  "expenses": [
    {
      "id": "a1b2c3d4",
      "timestamp": "2026-03-16T14:30:00+07:00",
      "amount_local": 350.00,
      "local_currency": "THB",
      "amount_base": 10.15,
      "base_currency": "USD",
      "fx_rate": 0.029,
      "category": "food",
      "subcategory": "restaurant",
      "description": "lunch at cafe",
      "source": "voice"
    }
  ],
  "total": 156,
  "limit": 50,
  "offset": 0
}
```

### `DELETE /api/expenses/:id`

Delete a specific expense by ID.

**Response:**
```json
{
  "deleted": true,
  "expense": { ... }
}
```

### `GET /api/budgets`

Returns budget configuration and current spending per category.

**Response:**
```json
{
  "base_currency": "USD",
  "month": "2026-03",
  "budgets": [
    {
      "category": "food",
      "budget": 400.00,
      "spent": 243.50,
      "remaining": 156.50,
      "percentage": 60.9,
      "status": "normal"
    },
    {
      "category": "transport",
      "budget": 150.00,
      "spent": 135.00,
      "remaining": 15.00,
      "percentage": 90.0,
      "status": "warning"
    }
  ]
}
```

**Status values:** `normal` (< 80%), `warning` (80-100%), `exceeded` (> 100%)

### `PUT /api/budgets`

Update budget values.

**Request body:**
```json
{
  "budgets": {
    "food": 450.00,
    "transport": 200.00
  }
}
```

### `GET /api/settings`

Returns current user settings.

**Response:**
```json
{
  "telegram_id": 123456789,
  "display_name": "Vasya",
  "email": "vasya@gmail.com",
  "base_currency": "USD",
  "default_currency": "THB",
  "spreadsheet_id": "1aBcDeF...",
  "owner": "user",
  "created_at": "2026-03-07T12:00:00+07:00"
}
```

### `PUT /api/settings`

Update user settings (currencies).

**Request body:**
```json
{
  "base_currency": "EUR",
  "default_currency": "THB"
}
```

Validates ISO 4217 codes. Returns updated settings.

---

## Frontend — Pages & Components

### Page structure (bottom tab navigation)

```
┌─────────────────────────────────┐
│  Header: "Expense Tracker"       │
│  Period selector: Today/Week/Mo  │
├─────────────────────────────────┤
│                                  │
│  [Active page content]           │
│                                  │
│                                  │
├─────────────────────────────────┤
│  📊 Dashboard  📋 History  ⚙ Set │
│  (bottom tabs)                   │
└─────────────────────────────────┘
```

Three tabs: **Dashboard**, **History**, **Settings**.

---

### Page 1: Dashboard (`/`)

The main analytics view. Shows summary for selected period.

**Layout (top to bottom):**

1. **Period Selector** — segmented control: Today / Week / Month
2. **Total Card** — big number with base currency, comparison badge (↑12% or ↓8%)
3. **Daily Average** — smaller card below total
4. **Category Donut Chart** — interactive donut (Recharts `PieChart`), tap category → highlight
5. **Category Breakdown List** — below chart, each row: emoji + name + amount + bar + percentage
6. **Daily Spending Chart** — bar chart (Recharts `BarChart`), one bar per day
7. **Budget Progress** — horizontal progress bars per category with budget limits
8. **Currency Breakdown** — if multi-currency expenses exist, pie chart showing spend by currency
9. **Top Expenses** — top 5 largest transactions for the period

**Component tree:**
```
<DashboardPage>
  <PeriodSelector value={period} onChange={setPeriod} />
  <TotalCard total={summary.total_base} currency={user.base_currency} comparison={summary.comparison} />
  <DailyAverageCard average={summary.daily_average} currency={user.base_currency} />
  <CategoryDonut data={summary.by_category} />
  <CategoryBreakdown data={summary.by_category} currency={user.base_currency} />
  <DailyChart data={summary.daily_totals} />
  <BudgetProgress budgets={budgets} />
  <CurrencyBreakdown data={summary.by_currency} />
  <TopExpenses expenses={topExpenses} />
</DashboardPage>
```

**Data fetching:**
- On mount and period change: `GET /api/summary?period={period}&compare=true`
- Budgets: `GET /api/budgets`
- Skeleton loading state while fetching

---

### Page 2: History (`/history`)

Scrollable transaction list with filters.

**Layout:**

1. **Filter Bar** — category dropdown + date range picker (month selector)
2. **Transaction List** — grouped by date
   - Date header: "Today, March 16" or "Monday, March 15"
   - Transaction row: category emoji + description + amount (local + base) + source icon (🎙/✏️/📷)
3. **Pull to refresh** (Telegram Mini App native)
4. **Infinite scroll** — load more on scroll bottom (paginated via offset)

**Transaction row detail (on tap):**
```
┌────────────────────────────────────┐
│ 🍕 Food — restaurant               │
│ Lunch at cafe                       │
│ 350 THB ($10.15)  FX: 0.029        │
│ Mar 16, 2:30 PM · 🎙 voice         │
│                                     │
│ [Delete]                            │
└────────────────────────────────────┘
```

**Component tree:**
```
<HistoryPage>
  <FilterBar
    category={filter.category}
    month={filter.month}
    onCategoryChange={...}
    onMonthChange={...}
  />
  <TransactionList>
    {groupedByDate.map(group => (
      <DateGroup key={group.date} date={group.date}>
        {group.expenses.map(exp => (
          <TransactionRow
            key={exp.id}
            expense={exp}
            baseCurrency={user.base_currency}
            onTap={() => openDetail(exp)}
          />
        ))}
      </DateGroup>
    ))}
    <InfiniteScrollTrigger onReach={loadMore} />
  </TransactionList>
  <TransactionDetail expense={selected} onDelete={handleDelete} />
</HistoryPage>
```

**Data fetching:**
- On mount: `GET /api/expenses?limit=50`
- On filter change: re-fetch with query params
- On scroll bottom: `GET /api/expenses?limit=50&offset={offset}`
- Delete: `DELETE /api/expenses/:id` → remove from local state

---

### Page 3: Settings (`/settings`)

User configuration.

**Sections:**

1. **Profile** (read-only)
   - Display name, Telegram username
   - Registration date
   - Linked email (or "Not linked" + hint to use /email in bot)

2. **Currencies**
   - Base currency — selector with search (all ISO 4217)
   - Default currency — same selector
   - Save button → `PUT /api/settings`

3. **Budgets** (editable)
   - List of categories with budget input fields
   - Current values pre-filled
   - Save button → `PUT /api/budgets`
   - "Reset" to clear all budgets

4. **Data**
   - "Export CSV" button → triggers file download
   - "Open in Google Sheets" link → opens spreadsheet in browser
   - Transaction count: "156 transactions since Mar 7, 2026"

**Component tree:**
```
<SettingsPage>
  <ProfileSection user={user} />
  <CurrencySection
    baseCurrency={user.base_currency}
    defaultCurrency={user.default_currency}
    onSave={updateSettings}
  />
  <BudgetSection
    budgets={budgets}
    categories={CATEGORIES}
    baseCurrency={user.base_currency}
    onSave={updateBudgets}
  />
  <DataSection
    spreadsheetId={user.spreadsheet_id}
    expenseCount={count}
    createdAt={user.created_at}
    onExport={exportCSV}
  />
</SettingsPage>
```

---

## Design System

### Telegram Theme Integration

Telegram Mini Apps provide CSS variables for native look. The app **must** use these as primary theme tokens:

```css
:root {
  /* Telegram-provided (auto-set by WebView) */
  --tg-theme-bg-color: ...;
  --tg-theme-text-color: ...;
  --tg-theme-hint-color: ...;
  --tg-theme-link-color: ...;
  --tg-theme-button-color: ...;
  --tg-theme-button-text-color: ...;
  --tg-theme-secondary-bg-color: ...;
  --tg-theme-header-bg-color: ...;
  --tg-theme-accent-text-color: ...;
  --tg-theme-section-bg-color: ...;
  --tg-theme-section-header-text-color: ...;
  --tg-theme-subtitle-text-color: ...;
  --tg-theme-destructive-text-color: ...;
  
  /* App-specific tokens (derived from Telegram theme) */
  --app-card-bg: var(--tg-theme-section-bg-color);
  --app-text-primary: var(--tg-theme-text-color);
  --app-text-secondary: var(--tg-theme-hint-color);
  --app-accent: var(--tg-theme-button-color);
  --app-danger: var(--tg-theme-destructive-text-color);
  --app-border: color-mix(in srgb, var(--tg-theme-hint-color) 20%, transparent);
}
```

### Category Colors & Emojis

Each category has a fixed color and emoji (consistent with bot messages):

```typescript
const CATEGORY_CONFIG: Record<string, { emoji: string; color: string }> = {
  food:           { emoji: "🍕", color: "#34d399" },
  transport:      { emoji: "🚗", color: "#22d3ee" },
  housing:        { emoji: "🏠", color: "#a78bfa" },
  health:         { emoji: "💊", color: "#f472b6" },
  entertainment:  { emoji: "🎮", color: "#fbbf24" },
  shopping:       { emoji: "🛍️", color: "#fb923c" },
  education:      { emoji: "📚", color: "#60a5fa" },
  services:       { emoji: "✂️", color: "#c084fc" },
  subscriptions:  { emoji: "📱", color: "#f87171" },
  travel:         { emoji: "✈️", color: "#2dd4bf" },
  other:          { emoji: "📦", color: "#94a3b8" },
};
```

### Typography

- **Numbers (amounts):** Monospace or tabular-nums, for alignment in lists
- **Headers:** System font (Telegram provides), bold
- **Body:** System font, regular
- **Small/labels:** System font, hint color

No custom web fonts — use system stack for instant render and native feel:
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

### Spacing & Layout

- Page padding: 16px horizontal
- Card padding: 16px
- Card border-radius: 12px
- Card gap: 12px
- Tab bar height: 56px (fixed bottom)
- Header height: 48px (fixed top, below Telegram header)
- Content area: scrollable between header and tab bar
- Max width: none (fills Telegram WebView width, typically 390-430px on mobile)

### Animations

- Page transitions: slide left/right (200ms ease-out)
- Number changes: count-up animation on total card (400ms)
- Chart appearance: fade-in + slight scale (300ms)
- List items: stagger fade-in on load (50ms delay per item, max 10)
- Skeleton loading: shimmer animation on placeholder blocks
- Pull-to-refresh: native Telegram behavior
- Delete: slide-out left (200ms) then collapse height (150ms)

---

## Project Structure

```
mini-app/
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── package.json
│
├── public/
│   └── favicon.svg
│
├── src/
│   ├── main.tsx                    # React entry point
│   ├── App.tsx                     # Router + layout + Telegram SDK init
│   │
│   ├── api/
│   │   ├── client.ts              # fetch wrapper with initData auth
│   │   ├── types.ts               # API response types
│   │   ├── summary.ts             # GET /api/summary
│   │   ├── expenses.ts            # GET/DELETE /api/expenses
│   │   ├── budgets.ts             # GET/PUT /api/budgets
│   │   └── settings.ts            # GET/PUT /api/settings
│   │
│   ├── context/
│   │   ├── UserContext.tsx         # User settings + auth state
│   │   └── ThemeContext.tsx        # Telegram theme vars
│   │
│   ├── pages/
│   │   ├── DashboardPage.tsx
│   │   ├── HistoryPage.tsx
│   │   └── SettingsPage.tsx
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── TabBar.tsx
│   │   │   ├── Header.tsx
│   │   │   └── PageTransition.tsx
│   │   │
│   │   ├── dashboard/
│   │   │   ├── PeriodSelector.tsx
│   │   │   ├── TotalCard.tsx
│   │   │   ├── DailyAverageCard.tsx
│   │   │   ├── CategoryDonut.tsx
│   │   │   ├── CategoryBreakdown.tsx
│   │   │   ├── DailyChart.tsx
│   │   │   ├── BudgetProgress.tsx
│   │   │   ├── CurrencyBreakdown.tsx
│   │   │   └── TopExpenses.tsx
│   │   │
│   │   ├── history/
│   │   │   ├── FilterBar.tsx
│   │   │   ├── DateGroup.tsx
│   │   │   ├── TransactionRow.tsx
│   │   │   ├── TransactionDetail.tsx
│   │   │   └── InfiniteScrollTrigger.tsx
│   │   │
│   │   ├── settings/
│   │   │   ├── ProfileSection.tsx
│   │   │   ├── CurrencySection.tsx
│   │   │   ├── BudgetSection.tsx
│   │   │   └── DataSection.tsx
│   │   │
│   │   └── shared/
│   │       ├── Skeleton.tsx
│   │       ├── CurrencySelect.tsx
│   │       ├── EmptyState.tsx
│   │       ├── ErrorState.tsx
│   │       └── AmountDisplay.tsx
│   │
│   ├── hooks/
│   │   ├── useSummary.ts          # fetch + cache summary data
│   │   ├── useExpenses.ts         # fetch + paginate + filter expenses
│   │   ├── useBudgets.ts          # fetch + update budgets
│   │   ├── useSettings.ts         # fetch + update settings
│   │   └── useTelegram.ts         # Telegram WebApp SDK helpers
│   │
│   ├── utils/
│   │   ├── categories.ts          # CATEGORY_CONFIG, emoji/color maps
│   │   ├── format.ts              # formatAmount, formatDate, formatPercent
│   │   └── currency.ts            # currency symbols, display helpers
│   │
│   └── styles/
│       └── globals.css            # Tailwind base + Telegram theme vars + animations
│
└── tests/
    ├── api/
    │   └── client.test.ts
    ├── components/
    │   ├── TotalCard.test.tsx
    │   ├── TransactionRow.test.tsx
    │   └── CategoryDonut.test.tsx
    └── hooks/
        └── useSummary.test.ts
```

---

## API Client (`src/api/client.ts`)

```typescript
const API_BASE = import.meta.env.VITE_API_URL; // Cloud Function URL

interface ApiClient {
  get<T>(path: string, params?: Record<string, string>): Promise<T>;
  put<T>(path: string, body: unknown): Promise<T>;
  delete<T>(path: string): Promise<T>;
}

function createApiClient(): ApiClient {
  const telegram = window.Telegram?.WebApp;
  const initData = telegram?.initData || "";

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const url = new URL(`/api${path}`, API_BASE);
    
    const response = await fetch(url.toString(), {
      method,
      headers: {
        "Content-Type": "application/json",
        "Authorization": `tma ${initData}`,
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new ApiError(response.status, error.message || "Request failed");
    }

    return response.json();
  }

  return {
    get: (path, params) => {
      const qs = params ? "?" + new URLSearchParams(params).toString() : "";
      return request("GET", path + qs);
    },
    put: (path, body) => request("PUT", path, body),
    delete: (path) => request("DELETE", path),
  };
}
```

---

## Telegram SDK Integration (`src/hooks/useTelegram.ts`)

```typescript
import { useEffect } from "react";

export function useTelegram() {
  const tg = window.Telegram?.WebApp;

  useEffect(() => {
    if (!tg) return;

    // Expand to full height
    tg.expand();

    // Enable closing confirmation (prevent accidental close)
    tg.enableClosingConfirmation();

    // Set header color to match app
    tg.setHeaderColor("secondary_bg_color");

    // Ready signal (hides loading placeholder)
    tg.ready();
  }, []);

  return {
    tg,
    user: tg?.initDataUnsafe?.user,
    colorScheme: tg?.colorScheme, // "light" | "dark"
    viewportHeight: tg?.viewportStableHeight,
    hapticFeedback: tg?.HapticFeedback,
    close: () => tg?.close(),
    showConfirm: (message: string) =>
      new Promise<boolean>((resolve) => tg?.showConfirm(message, resolve)),
  };
}
```

### Haptic feedback usage
- **On confirm/save**: `hapticFeedback.notificationOccurred("success")`
- **On delete**: `hapticFeedback.notificationOccurred("warning")` before confirmation
- **On error**: `hapticFeedback.notificationOccurred("error")`
- **On tab switch**: `hapticFeedback.selectionChanged()`
- **On period toggle**: `hapticFeedback.impactOccurred("light")`

---

## Backend Changes

### New file: `api/routes.py`

```python
"""REST API for Mini App, added to existing Cloud Function."""

import json
from flask import Request, jsonify
from services.auth import validate_init_data
from services.sheets import SheetsService
from services.user_registry import UserRegistry
from services.currency import CurrencyService


def handle_api(request: Request, user: User) -> tuple:
    """Route /api/* requests to appropriate handler."""
    
    path = request.path.removeprefix("/api")
    method = request.method

    if path == "/summary" and method == "GET":
        return api_summary(request, user)
    elif path == "/expenses" and method == "GET":
        return api_expenses_list(request, user)
    elif path.startswith("/expenses/") and method == "DELETE":
        expense_id = path.split("/")[-1]
        return api_expense_delete(expense_id, user)
    elif path == "/budgets" and method == "GET":
        return api_budgets_get(user)
    elif path == "/budgets" and method == "PUT":
        return api_budgets_update(request, user)
    elif path == "/settings" and method == "GET":
        return api_settings_get(user)
    elif path == "/settings" and method == "PUT":
        return api_settings_update(request, user)
    else:
        return jsonify({"error": "not found"}), 404
```

### New file: `services/auth.py`

```python
"""Telegram Mini App initData validation."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote


MAX_AUTH_AGE_SECONDS = 3600  # 1 hour


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Validate and parse Telegram Mini App initData.
    Returns user dict if valid, None otherwise.
    """
    parsed = parse_qs(init_data)
    
    if "hash" not in parsed:
        return None
    
    received_hash = parsed.pop("hash")[0]
    
    # Check auth_date freshness
    auth_date = int(parsed.get("auth_date", ["0"])[0])
    if time.time() - auth_date > MAX_AUTH_AGE_SECONDS:
        return None
    
    # Build data_check_string
    data_check_string = "\n".join(
        f"{k}={v[0]}" for k, v in sorted(parsed.items())
    )
    
    # Compute secret key
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    
    # Compute hash
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(computed_hash, received_hash):
        return None
    
    # Parse user object
    user_json = parsed.get("user", ["{}"])[0]
    user = json.loads(unquote(user_json))
    
    return user
```

### Updated `main.py` routing

```python
@functions_framework.http
def webhook(request):
    # CORS for Mini App
    if request.method == "OPTIONS":
        return handle_cors_preflight(request)
    
    path = request.path
    
    # Telegram webhook (existing)
    if request.method == "POST" and (path == "/" or path == "/webhook"):
        return handle_telegram_update(request)
    
    # Mini App REST API (new)
    if path.startswith("/api/"):
        response = handle_api_request(request)
        return add_cors_headers(response)
    
    # Mini App static files (if serving from same function)
    if path.startswith("/app/"):
        return serve_static(path)
    
    return "ok", 200


def handle_cors_preflight(request):
    """Handle CORS preflight for Mini App API calls."""
    headers = {
        "Access-Control-Allow-Origin": "*",  # Telegram WebView origin
        "Access-Control-Allow-Methods": "GET, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "3600",
    }
    return "", 204, headers
```

---

## Hosting Options

### Option A: Google Cloud Storage (recommended for MVP)

Static React build served from GCS bucket. API remains on Cloud Function.

```bash
# Build
cd mini-app && npm run build

# Deploy static files to GCS
gsutil mb gs://expense-bot-app
gsutil web set -m index.html -e index.html gs://expense-bot-app
gsutil -m cp -r dist/* gs://expense-bot-app/
gsutil iam ch allUsers:objectViewer gs://expense-bot-app

# URL: https://storage.googleapis.com/expense-bot-app/index.html
```

### Option B: Same Cloud Function

Serve static files from the Cloud Function itself (simpler setup, no CORS issues).

```python
import os
from flask import send_from_directory

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

def serve_static(path: str):
    file_path = path.removeprefix("/app/") or "index.html"
    return send_from_directory(STATIC_DIR, file_path)
```

### BotFather configuration

```
/setmenubutton
> Choose your bot
> URL: https://your-function-url/app/
> Title: Dashboard
```

---

## Environment Variables (additions to .env.yaml)

```yaml
# Existing vars stay the same, add:
MINI_APP_URL: "https://storage.googleapis.com/expense-bot-app"
CORS_ALLOWED_ORIGINS: "*"
```

---

## Implementation Order

```
Phase 1: Backend API (2-3 days)
  1. services/auth.py — initData validation + tests
  2. api/routes.py — routing + CORS
  3. api/summary.py — GET /api/summary (reuse analytics.py)
  4. api/expenses.py — GET + DELETE /api/expenses
  5. api/budgets.py — GET + PUT /api/budgets
  6. api/settings.py — GET + PUT /api/settings
  7. Update main.py routing
  8. Deploy and test with curl

Phase 2: Frontend Scaffold (1 day)
  9. Vite + React + TypeScript + Tailwind setup
  10. Telegram SDK integration (useTelegram hook)
  11. API client with initData auth
  12. TabBar + Header + page routing
  13. Theme integration (Telegram CSS vars)

Phase 3: Dashboard Page (2 days)
  14. PeriodSelector + TotalCard
  15. CategoryDonut + CategoryBreakdown (Recharts)
  16. DailyChart (Recharts BarChart)
  17. BudgetProgress
  18. Summary data fetching hook (useSummary)

Phase 4: History Page (1-2 days)
  19. TransactionRow + DateGroup
  20. TransactionDetail (slide-up sheet)
  21. FilterBar (category + month)
  22. Infinite scroll pagination
  23. Delete with confirmation

Phase 5: Settings Page (1 day)
  24. ProfileSection (read-only)
  25. CurrencySection (editable)
  26. BudgetSection (editable)
  27. DataSection (export + link)

Phase 6: Polish & Deploy (1 day)
  28. Loading skeletons for all pages
  29. Error states and empty states
  30. Haptic feedback on interactions
  31. Page transition animations
  32. Build and deploy to GCS
  33. Configure BotFather menu button
```

---

## Acceptance Criteria

### Auth
- [ ] Valid initData returns user object
- [ ] Expired initData (> 1 hour) returns 401
- [ ] Tampered initData returns 401
- [ ] Every API endpoint rejects requests without valid auth

### Dashboard
- [ ] Period selector switches between today/week/month
- [ ] Total card shows correct amount in base_currency
- [ ] Comparison badge shows correct % change vs previous period
- [ ] Category donut renders with correct proportions and colors
- [ ] Daily chart shows one bar per day with correct amounts
- [ ] Budget progress bars show correct fill percentage
- [ ] Empty state shown when no expenses for period

### History
- [ ] Transactions load on page mount
- [ ] Transactions grouped by date with correct headers
- [ ] Category filter shows only matching transactions
- [ ] Infinite scroll loads next page when bottom reached
- [ ] Transaction detail opens on tap
- [ ] Delete removes transaction and updates list
- [ ] Delete confirmation uses Telegram native dialog

### Settings
- [ ] Profile shows correct user data
- [ ] Currency selection validates ISO 4217
- [ ] Save currencies updates backend and refreshes all data
- [ ] Budget inputs accept numeric values only
- [ ] Save budgets updates backend
- [ ] Export triggers CSV download
- [ ] Google Sheets link opens correct spreadsheet

### UX
- [ ] App uses Telegram theme colors (works in both light and dark)
- [ ] Haptic feedback fires on key interactions
- [ ] Loading states shown during API calls
- [ ] Error states shown on API failure with retry button
- [ ] Page transitions animate smoothly
- [ ] App is usable on viewport widths 320px–430px
- [ ] Tab bar stays fixed at bottom during scroll

---

## How to use with Claude Code

```bash
cd expense-bot
claude
```

### Backend first:

```
Read specs/13-mini-app.md — Backend Changes section.
Implement services/auth.py with initData validation.
Write tests/test_auth.py covering valid, expired, and tampered initData.
Run tests and fix failures.
```

```
Read specs/13-mini-app.md — REST API Endpoints section.
Implement api/routes.py with all 7 endpoints.
Update main.py to route /api/* requests.
Write tests for each endpoint.
```

### Then frontend:

```
Read specs/13-mini-app.md — Frontend section completely.
Scaffold the React project in mini-app/ directory:
- Vite + React + TypeScript + Tailwind
- Telegram SDK integration
- API client with auth
- TabBar + Header + routing between 3 pages
- Telegram theme CSS variables
```

```
Read specs/13-mini-app.md — Dashboard Page section.
Implement DashboardPage with all components:
- PeriodSelector, TotalCard, CategoryDonut, DailyChart, BudgetProgress
- useSummary hook for data fetching
- Skeleton loading states
- Recharts for charts
```
