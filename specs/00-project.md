# Expense Tracker Bot — Specifications

> Spec-driven development: each module has a formal specification.
> Claude Code reads the spec and implements exactly to it.
> All specs reference the architecture: `docs/expense-bot-architecture.html`

---

## specs/ directory structure

```
specs/
├── 00-project.md           ← this file (overview + conventions)
├── models/
│   ├── 01-expense.md
│   ├── 02-user.md
│   └── 03-category.md
├── services/
│   ├── 04-gemini.md
│   ├── 05-sheets.md
│   ├── 06-user-registry.md
│   └── 07-currency.md
├── handlers/
│   ├── 08-voice.md
│   ├── 09-text.md
│   ├── 10-commands.md
│   └── 11-callbacks.md
└── 12-main.md
```

---

## Conventions

- Language: Python 3.12
- All I/O: async/await
- Models: Pydantic v2 BaseModel
- Tests: pytest + pytest-asyncio
- Type hints: mandatory on all public functions
- Docstrings: English, concise
- Error handling: custom exceptions, never bare `except:`
- Env vars: via `os.environ`, validated at startup
- ISO 4217: all currency codes validated
- Timezone: user-configurable, stored per-user

---

# SPEC 01 — models/expense.py

## Purpose
Pydantic models for expense data: parsing input from Gemini, storing to Sheets.

## Models

### `GeminiExpenseResponse`
What Gemini returns from audio/text parsing.

```python
class GeminiExpenseResponse(BaseModel):
    amount: float              # e.g. 350.0
    currency: str              # ISO 4217, e.g. "THB"
    category: str              # e.g. "food"
    subcategory: str           # e.g. "restaurant"
    description: str           # e.g. "lunch at cafe"
```

### `Expense`
Full expense record ready for Sheets storage.

```python
class Expense(BaseModel):
    id: str                    # UUID4 hex, 8 chars
    timestamp: datetime        # timezone-aware
    amount_local: float        # original amount
    local_currency: str        # ISO 4217
    amount_base: float         # converted to user's base_currency
    fx_rate: float             # local_currency → base_currency rate
    category: str
    subcategory: str
    description: str
    source: Literal["voice", "text", "photo"]
    raw_input: str             # original transcription or text

    def to_sheet_row(self) -> list[str]:
        """Convert to list of strings for Sheets API append."""

    @classmethod
    def from_gemini(
        cls,
        response: GeminiExpenseResponse,
        amount_base: float,
        fx_rate: float,
        source: str,
        raw_input: str,
    ) -> "Expense":
        """Factory: create Expense from Gemini response + conversion data."""
```

### Validation rules
- `amount` and `amount_local`: must be > 0
- `currency` and `local_currency`: 3 uppercase letters, valid ISO 4217
- `category`: must be in VALID_CATEGORIES
- `id`: generated via `uuid4().hex[:8]`
- `timestamp`: defaults to `datetime.now(tz)` if not provided

## Acceptance criteria
- [ ] `GeminiExpenseResponse` validates correct Gemini JSON
- [ ] `GeminiExpenseResponse` rejects negative amounts
- [ ] `GeminiExpenseResponse` rejects invalid currency codes (e.g. "XYZ", "th", "1234")
- [ ] `Expense.from_gemini()` creates correct Expense from parsed response
- [ ] `Expense.to_sheet_row()` returns list matching Transactions Sheet column order
- [ ] All fields have type hints and Pydantic validators

---

# SPEC 02 — models/user.py

## Purpose
Pydantic models for user data: registration, settings, registry lookup.

## Models

### `User`
Represents a registered user in the master registry.

```python
class User(BaseModel):
    telegram_id: int
    username: str | None       # @username, may be absent
    display_name: str
    email: str | None          # Google email, optional
    spreadsheet_id: str
    owner: Literal["user", "admin"]
    base_currency: str         # ISO 4217, for analytics
    default_currency: str      # ISO 4217, fallback when not specified
    created_at: datetime
    status: Literal["active", "suspended"]

    @classmethod
    def from_sheet_row(cls, row: list[str]) -> "User":
        """Parse a row from the Registry sheet."""

    def to_sheet_row(self) -> list[str]:
        """Serialize to a list of strings for Sheets API."""
```

### `UserSettings`
Subset of User for the /settings command.

```python
class UserSettings(BaseModel):
    base_currency: str
    default_currency: str
    timezone: str              # e.g. "Asia/Bangkok"
```

### `CurrencyValidator`
Utility class for ISO 4217 validation.

```python
class CurrencyValidator:
    VALID_CODES: ClassVar[set[str]]  # loaded from a static list

    @classmethod
    def validate(cls, code: str) -> str:
        """Return uppercase code if valid, raise ValueError otherwise."""

    @classmethod
    def is_valid(cls, code: str) -> bool:
        """Return True if code is a valid ISO 4217 currency."""
```

## Acceptance criteria
- [ ] `User.from_sheet_row()` parses all 10 columns correctly
- [ ] `User.to_sheet_row()` serializes back to the same format
- [ ] `CurrencyValidator.validate("thb")` returns "THB"
- [ ] `CurrencyValidator.validate("XYZ")` raises ValueError
- [ ] `CurrencyValidator.validate("")` raises ValueError
- [ ] `CurrencyValidator.validate("US")` raises ValueError (too short)
- [ ] `CurrencyValidator.validate("USDX")` raises ValueError (too long)

---

# SPEC 03 — models/category.py

## Purpose
Category definitions and validation.

## Data structure

```python
CATEGORIES: dict[str, list[str]] = {
    "food":           ["restaurant", "grocery", "delivery", "coffee", "other"],
    "transport":      ["fuel", "taxi", "rental", "flights", "public", "other"],
    "housing":        ["rent", "utilities", "maintenance", "other"],
    "health":         ["pharmacy", "gym", "medical", "insurance", "other"],
    "entertainment":  ["movies", "games", "bars", "events", "other"],
    "shopping":       ["clothes", "electronics", "household", "other"],
    "education":      ["courses", "books", "software", "other"],
    "services":       ["haircut", "laundry", "repairs", "other"],
    "subscriptions":  ["streaming", "saas", "telecom", "other"],
    "travel":         ["hotel", "tours", "activities", "other"],
    "other":          ["other"],
}

VALID_CATEGORIES: set[str]     # all top-level keys
VALID_SUBCATEGORIES: dict[str, set[str]]  # category → set of subcategories
```

## Functions

```python
def validate_category(category: str) -> str:
    """Return lowercase category if valid, raise ValueError otherwise."""

def validate_subcategory(category: str, subcategory: str) -> str:
    """Return lowercase subcategory if valid for given category."""

def get_categories_for_prompt() -> str:
    """Format categories as a string for Gemini system instruction."""
```

## Acceptance criteria
- [ ] `validate_category("Food")` returns "food"
- [ ] `validate_category("invalid")` raises ValueError
- [ ] `validate_subcategory("food", "Restaurant")` returns "restaurant"
- [ ] `validate_subcategory("food", "invalid")` raises ValueError
- [ ] `get_categories_for_prompt()` returns pipe-delimited string of categories

---

# SPEC 04 — services/gemini.py

## Purpose
Client for Gemini 3.1 Flash Lite API. Handles audio→JSON and text→JSON parsing.

## Dependencies
- `google-genai` SDK
- `models.expense.GeminiExpenseResponse`
- `models.category.get_categories_for_prompt`

## Configuration
- `GOOGLE_API_KEY` env var
- Model: `gemini-3.1-flash-lite-preview`
- Response format: `response_mime_type="application/json"` + `response_schema`

## Public API

```python
class GeminiService:
    def __init__(self, api_key: str):
        """Initialize Gemini client and model."""

    async def parse_audio(
        self, audio_bytes: bytes, default_currency: str
    ) -> GeminiExpenseResponse:
        """
        Send OGG/OPUS audio to Gemini, return parsed expense.
        - Uploads audio as inline data (not File API for small files)
        - System instruction includes default_currency
        - Uses response_schema for guaranteed JSON
        """

    async def parse_text(
        self, text: str, default_currency: str
    ) -> GeminiExpenseResponse:
        """
        Send text message to Gemini, return parsed expense.
        - Same system instruction and schema as audio
        """

    def _build_system_instruction(self, default_currency: str) -> str:
        """Build system prompt with user's default currency and categories."""
```

## System instruction template
```
You are an expense parser. Extract from the input:
- amount: number (float)
- currency: ISO 4217 code ("бат/baht" → THB, "долларов/$" → USD, "евро/€" → EUR)
- If currency not specified → {default_currency}
- category: one of [{categories}]
- subcategory: specific type within category
- description: brief description in the original language, 2-5 words
```

## Error handling
- `google.genai.errors.APIError` → log and raise `GeminiAPIError`
- Invalid JSON response → retry once, then raise `GeminiParseError`
- Empty audio → raise `ValueError("Empty audio data")`

## Acceptance criteria
- [ ] `parse_text("обед 350 бат", "THB")` returns amount=350, currency="THB", category="food"
- [ ] `parse_text("coffee 4.5 dollars", "THB")` returns currency="USD" (explicit override)
- [ ] `parse_text("taxi 200", "THB")` returns currency="THB" (default applied)
- [ ] `parse_audio(ogg_bytes, "THB")` returns valid GeminiExpenseResponse
- [ ] Empty audio raises ValueError
- [ ] API error is wrapped in GeminiAPIError
- [ ] System instruction contains user's default_currency
- [ ] System instruction contains all valid categories

---

# SPEC 05 — services/sheets.py

## Purpose
Google Sheets client for reading/writing transactions and registry data.

## Dependencies
- `gspread` (async wrapper or sync with executor)
- `google.oauth2.service_account`
- `models.expense.Expense`
- `models.user.User`

## Configuration
- `credentials.json` or default SA credentials in Cloud Functions
- Sheet IDs from env vars: `REGISTRY_SHEET_ID`, per-user `spreadsheet_id`

## Public API

```python
class SheetsService:
    def __init__(self, credentials_path: str | None = None):
        """Initialize gspread client with SA credentials."""

    # --- Registry operations ---

    async def get_all_users(self) -> list[User]:
        """Read all rows from Registry sheet, return list of User."""

    async def find_user(self, telegram_id: int) -> User | None:
        """Find user by telegram_id in Registry. Return None if not found."""

    async def add_user(self, user: User) -> None:
        """Append user row to Registry sheet."""

    async def update_user(self, user: User) -> None:
        """Update existing user row in Registry (match by telegram_id)."""

    # --- Transaction operations (per-user spreadsheet) ---

    async def append_expense(self, spreadsheet_id: str, expense: Expense) -> None:
        """Append expense row to Transactions sheet."""

    async def get_expenses(
        self,
        spreadsheet_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Expense]:
        """Read expenses from Transactions sheet, optionally filtered by date range."""

    async def delete_last_expense(self, spreadsheet_id: str) -> Expense | None:
        """Delete the last row from Transactions sheet. Return the deleted expense."""

    async def get_expense_count(self, spreadsheet_id: str) -> int:
        """Return total number of expenses in user's sheet."""
```

## Error handling
- `gspread.exceptions.APIError` → log and raise `SheetsAPIError`
- Sheet not found → raise `SheetNotFoundError`
- Permission denied → raise `SheetsPermissionError`

## Acceptance criteria
- [ ] `append_expense()` adds a row with correct column order
- [ ] `get_expenses(since=monday)` returns only this week's expenses
- [ ] `get_expenses()` without filters returns all expenses
- [ ] `delete_last_expense()` removes last row and returns it
- [ ] `delete_last_expense()` on empty sheet returns None
- [ ] `find_user(12345)` returns User when exists
- [ ] `find_user(99999)` returns None when not found
- [ ] `add_user()` appends correct row to Registry

---

# SPEC 06 — services/user_registry.py

## Purpose
User lifecycle management: registration, Spreadsheet creation, ownership transfer.

## Dependencies
- `googleapiclient.discovery` (Drive API)
- `services.sheets.SheetsService`
- `models.user.User, CurrencyValidator`

## Configuration
- `ADMIN_EMAIL` — fallback owner for Spreadsheets
- `TEMPLATE_SHEET_ID` — ID of the template Spreadsheet to copy
- `USERS_FOLDER_ID` — Google Drive folder for user Spreadsheets

## Public API

```python
class UserRegistry:
    def __init__(
        self,
        drive_service,
        sheets_service: SheetsService,
        admin_email: str,
        template_sheet_id: str,
        users_folder_id: str,
    ):
        self._cache: dict[int, User] = {}  # telegram_id → User

    async def get_user(self, telegram_id: int) -> User | None:
        """
        Lookup user: cache → Sheets registry → None.
        Populates cache on successful lookup.
        """

    async def create_user(
        self,
        telegram_id: int,
        username: str | None,
        display_name: str,
        base_currency: str,
        default_currency: str,
    ) -> User:
        """
        Full registration flow:
        1. Validate currencies (CurrencyValidator)
        2. Copy template Spreadsheet via Drive API
        3. Transfer ownership to ADMIN_EMAIL
        4. Create User record
        5. Save to Registry sheet
        6. Update cache
        Return the new User.
        """

    async def transfer_ownership(self, telegram_id: int, email: str) -> None:
        """
        /email command handler:
        1. Lookup user
        2. Share Spreadsheet with email (writer)
        3. Transfer ownership to email
        4. Update user.email and user.owner in Registry
        5. Update cache
        """

    async def update_settings(
        self, telegram_id: int, base_currency: str | None, default_currency: str | None
    ) -> User:
        """
        /settings command handler:
        1. Validate new currency values
        2. Update user record in Registry
        3. Update cache
        Return updated User.
        """

    async def warm_cache(self) -> None:
        """Load all users from Registry into cache. Called on startup."""
```

## Error handling
- Invalid currency → raise `ValueError` with message
- User already exists → raise `UserAlreadyExistsError`
- User not found → raise `UserNotFoundError`
- Drive API error → raise `DriveAPIError`

## Acceptance criteria
- [ ] `create_user()` copies template and creates new Spreadsheet
- [ ] `create_user()` with invalid currency raises ValueError
- [ ] `create_user()` for existing telegram_id raises UserAlreadyExistsError
- [ ] `get_user()` returns from cache on second call (no Sheets API call)
- [ ] `transfer_ownership()` updates owner field to "user"
- [ ] `transfer_ownership()` for unknown user raises UserNotFoundError
- [ ] `update_settings()` validates currencies before updating
- [ ] `warm_cache()` loads all users into memory

---

# SPEC 07 — services/currency.py

## Purpose
Exchange rate fetching and caching. Converts between any two currencies.

## Dependencies
- `httpx` (async HTTP client)

## Configuration
- `EXCHANGE_RATE_API_KEY` env var
- Base URL: `https://v6.exchangerate-api.com/v6/{key}/latest/{base}`
- Cache TTL: 24 hours

## Public API

```python
class CurrencyService:
    def __init__(self, api_key: str, cache_ttl_hours: int = 24):
        self._cache: dict[str, tuple[dict[str, float], datetime]] = {}

    async def get_rate(self, from_currency: str, to_currency: str) -> float:
        """
        Return exchange rate from_currency → to_currency.
        Uses cached rates if available and fresh.
        If from == to, return 1.0 immediately.
        """

    async def convert(
        self, amount: float, from_currency: str, to_currency: str
    ) -> tuple[float, float]:
        """
        Convert amount. Return (converted_amount, fx_rate).
        converted_amount = amount * fx_rate, rounded to 2 decimals.
        """

    async def _fetch_rates(self, base_currency: str) -> dict[str, float]:
        """Fetch rates from API, update cache, return rates dict."""

    def _is_cache_fresh(self, base_currency: str) -> bool:
        """Return True if cache for base_currency is less than cache_ttl old."""
```

## Error handling
- API error / timeout → raise `CurrencyAPIError`
- Unknown currency in response → raise `CurrencyNotFoundError`
- Network timeout: 10 seconds

## Acceptance criteria
- [ ] `get_rate("USD", "USD")` returns 1.0 without API call
- [ ] `get_rate("USD", "THB")` returns a positive float
- [ ] `convert(100, "USD", "THB")` returns (amount, rate) where amount ≈ 100 * rate
- [ ] Second call within cache TTL does not make API request
- [ ] Call after cache TTL expiry makes a new API request
- [ ] API failure raises CurrencyAPIError

---

# SPEC 08 — handlers/voice.py

## Purpose
Handle incoming Telegram voice messages: download → Gemini → confirm → save.

## Dependencies
- `services.gemini.GeminiService`
- `services.currency.CurrencyService`
- `services.user_registry.UserRegistry`
- `handlers.callbacks` (for building confirmation keyboard)

## Public API

```python
async def handle_voice(update: Update, context: CallbackContext) -> None:
    """
    Flow:
    1. Get user from registry (by update.effective_user.id)
    2. Download voice message as bytes (OGG/OPUS)
    3. Call gemini.parse_audio(bytes, user.default_currency)
    4. Call currency.convert(amount, local_currency, user.base_currency)
    5. Create Expense object (source="voice", raw_input=transcription)
    6. Store pending expense in context.user_data["pending_expense"]
    7. Send confirmation message with inline keyboard
    """
```

## Confirmation message format
```
✅ {category_emoji} {category}: {amount_local} {local_currency} ({amount_base} {base_currency}) — {description}
```
With inline buttons: `[Confirm] [Edit Category] [Edit Amount] [Cancel]`

## Error handling
- Unregistered user → reply "Use /start to register first"
- Gemini parse failure → reply "Could not parse expense. Try again or type it manually."
- Currency conversion failure → save with fx_rate=0, amount_base=0, add warning

## Acceptance criteria
- [ ] Voice message from registered user triggers full flow
- [ ] Unregistered user gets registration prompt
- [ ] Pending expense stored in context.user_data
- [ ] Confirmation message shows both currencies
- [ ] Inline keyboard has 4 buttons
- [ ] Gemini error shows user-friendly message

---

# SPEC 09 — handlers/text.py

## Purpose
Handle incoming text messages that are not commands.

## Public API

```python
async def handle_text(update: Update, context: CallbackContext) -> None:
    """
    Same flow as voice handler, but:
    1. Text goes directly to gemini.parse_text() (no audio download)
    2. raw_input = the original message text
    3. source = "text"
    Everything else identical to voice handler.
    """
```

## Acceptance criteria
- [ ] Text "обед 350 бат" triggers parse and confirmation
- [ ] Text "coffee 4.5 dollars" triggers parse with currency override
- [ ] Unregistered user gets registration prompt
- [ ] Empty text is ignored

---

# SPEC 10 — handlers/commands.py

## Purpose
All bot slash commands.

## Commands

### `/start`
```python
async def cmd_start(update: Update, context: CallbackContext) -> int:
    """
    If user exists → "Welcome back! Send a voice or text message."
    If new user → start onboarding ConversationHandler:
      1. Ask base_currency (inline buttons: USD, EUR, GBP, THB, ILS, Other)
      2. Ask default_currency (inline buttons: same + user can type custom)
      3. Validate both currencies
      4. Call registry.create_user()
      5. Reply "Ready! Your base currency is X, default is Y. Send /email to link Google account."
    """
```
Returns: `ConversationHandler` state constants for the onboarding flow.

### `/email <address>`
```python
async def cmd_email(update: Update, context: CallbackContext) -> None:
    """
    Parse email from message text.
    Validate email format.
    Call registry.transfer_ownership(telegram_id, email).
    Reply "Spreadsheet shared and ownership transferred to {email}."
    """
```

### `/settings`
```python
async def cmd_settings(update: Update, context: CallbackContext) -> None:
    """
    No args → show current settings (base_currency, default_currency).
    /settings base EUR → update base_currency.
    /settings default THB → update default_currency.
    Validate currency before updating.
    """
```

### `/today`
```python
async def cmd_today(update: Update, context: CallbackContext) -> None:
    """
    Get expenses since start of today (user's timezone).
    Reply: "Today: {total} {base_currency} ({count} transactions)"
    + top 3 categories breakdown.
    """
```

### `/week`
```python
async def cmd_week(update: Update, context: CallbackContext) -> None:
    """
    Get expenses since Monday of current week.
    Reply: total, daily average, top categories, comparison vs last week.
    """
```

### `/month`
```python
async def cmd_month(update: Update, context: CallbackContext) -> None:
    """
    Get expenses since 1st of current month.
    Reply: total, daily average, category breakdown, top 5 expenses.
    """
```

### `/last [N]`
```python
async def cmd_last(update: Update, context: CallbackContext) -> None:
    """
    Show last N expenses (default 10, max 20).
    Format: "{date} {category} {amount_local} {local_currency} ({amount_base} {base}) — {description}"
    """
```

### `/undo`
```python
async def cmd_undo(update: Update, context: CallbackContext) -> None:
    """
    Delete last expense from user's sheet.
    Reply: "Deleted: {category} {amount_local} {local_currency}"
    If no expenses → "Nothing to undo."
    """
```

### `/budget`
```python
async def cmd_budget(update: Update, context: CallbackContext) -> None:
    """
    Show budget status per category (budgets defined in Categories sheet).
    Format: "{category}: {spent}/{budget} {base_currency} ({percent}%)"
    Categories over 80% get ⚠️, over 100% get 🔴.
    """
```

### `/export`
```python
async def cmd_export(update: Update, context: CallbackContext) -> None:
    """
    Export current month expenses as CSV file.
    Send as Telegram document attachment.
    """
```

## Acceptance criteria
- [ ] `/start` for new user triggers onboarding conversation
- [ ] `/start` for existing user shows welcome back message
- [ ] Onboarding validates currencies and creates Spreadsheet
- [ ] `/email invalid-email` shows validation error
- [ ] `/email valid@gmail.com` transfers ownership
- [ ] `/settings` with no args shows current settings
- [ ] `/settings base INVALID` shows error
- [ ] `/today` returns correct total for today
- [ ] `/week` includes comparison with last week
- [ ] `/last` defaults to 10, respects N parameter
- [ ] `/last 25` caps at 20
- [ ] `/undo` on empty sheet says "Nothing to undo"
- [ ] `/export` sends CSV file via Telegram

---

# SPEC 11 — handlers/callbacks.py

## Purpose
Handle inline button callbacks from confirmation messages and onboarding.

## Callback data format
```
confirm:{expense_id}
cancel:{expense_id}
edit_category:{expense_id}
edit_amount:{expense_id}
currency_base:{code}
currency_default:{code}
currency_custom_base
currency_custom_default
```

## Public API

```python
async def handle_confirm(update: Update, context: CallbackContext) -> None:
    """
    Save pending expense to Sheets.
    Edit message to: "✅ Saved: {category} {amount} {currency}"
    Remove inline keyboard.
    """

async def handle_cancel(update: Update, context: CallbackContext) -> None:
    """
    Remove pending expense from context.
    Edit message to: "❌ Cancelled"
    Remove inline keyboard.
    """

async def handle_edit_category(update: Update, context: CallbackContext) -> None:
    """
    Show category selection keyboard (all categories as buttons).
    On selection → update pending expense category → show confirmation again.
    """

async def handle_edit_amount(update: Update, context: CallbackContext) -> None:
    """
    Reply: "Send the correct amount (e.g. 350 THB or just 350):"
    Set conversation state to WAITING_AMOUNT.
    On next text message → parse amount → update pending expense → show confirmation.
    """

async def handle_currency_selection(update: Update, context: CallbackContext) -> None:
    """
    Handle currency button press during onboarding.
    Validate and store selected currency.
    Advance onboarding state.
    """
```

## Acceptance criteria
- [ ] Confirm saves expense and edits message
- [ ] Cancel removes pending expense and edits message
- [ ] Edit category shows category buttons
- [ ] Selecting category updates expense and re-shows confirmation
- [ ] Edit amount prompts for new amount
- [ ] Entering valid amount updates expense
- [ ] Entering invalid amount shows error
- [ ] Currency selection during onboarding advances flow

---

# SPEC 12 — main.py

## Purpose
Cloud Function entry point. Routes Telegram webhook to appropriate handler.

## Public API

```python
@functions_framework.http
def webhook(request: flask.Request) -> tuple[str, int]:
    """
    1. Verify webhook secret token (if configured)
    2. Parse Update from request JSON
    3. Initialize Application (singleton, cached between invocations)
    4. Process update through Application
    5. Return "ok", 200
    """
```

## Application setup

```python
def create_application() -> Application:
    """
    Create and configure telegram Application:
    1. Initialize all services (GeminiService, SheetsService, UserRegistry, CurrencyService)
    2. Register ConversationHandler for /start onboarding
    3. Register command handlers (/email, /settings, /today, etc.)
    4. Register message handlers (voice, text)
    5. Register callback query handler
    6. Warm user registry cache
    Return configured Application.
    """
```

## Initialization order
1. Load env vars, validate required vars present
2. Create SheetsService (with credentials)
3. Create GeminiService (with API key)
4. Create CurrencyService (with API key)
5. Create Drive service (with credentials)
6. Create UserRegistry (with drive, sheets, config)
7. Warm registry cache
8. Create Telegram Application with all handlers
9. Store services in `application.bot_data` for handler access

## Required environment variables
```
TELEGRAM_BOT_TOKEN
GOOGLE_API_KEY
ADMIN_EMAIL
TEMPLATE_SHEET_ID
REGISTRY_SHEET_ID
USERS_FOLDER_ID
EXCHANGE_RATE_API_KEY
TIMEZONE
```

## Error handling
- Missing env var → raise `RuntimeError` with clear message at startup
- Webhook parse error → return "bad request", 400
- Unhandled exception in handler → log, return "ok", 200 (don't break webhook)

## Acceptance criteria
- [ ] Missing env var raises RuntimeError with var name
- [ ] Valid webhook JSON is processed
- [ ] Invalid JSON returns 400
- [ ] Voice message routes to voice handler
- [ ] Text message routes to text handler
- [ ] Command message routes to command handler
- [ ] Callback query routes to callback handler
- [ ] Services are accessible from handlers via context.bot_data
- [ ] Application is created once and reused across invocations (Cloud Function warm start)

---

# Implementation order

Recommended sequence for Claude Code:

```
Phase 1: Models (no external dependencies)
  1. models/category.py + tests
  2. models/user.py + tests
  3. models/expense.py + tests

Phase 2: Services (external APIs, need mocks in tests)
  4. services/currency.py + tests
  5. services/sheets.py + tests
  6. services/gemini.py + tests
  7. services/user_registry.py + tests

Phase 3: Handlers (depend on services)
  8. handlers/callbacks.py + tests
  9. handlers/voice.py + tests
  10. handlers/text.py + tests
  11. handlers/commands.py + tests

Phase 4: Entry point
  12. main.py + integration tests

Phase 5: Deploy
  13. requirements.txt
  14. .env.yaml.example
  15. gcloud deploy + webhook setup
```

---

# How to use with Claude Code

```bash
cd expense-bot
claude
```

```
Read specs/00-project.md completely.
Then implement SPEC 01 (models/expense.py):
- Read the spec carefully
- Create models/expense.py with all models and validation
- Create tests/test_expense.py with all acceptance criteria
- Run the tests and fix any failures
```

Then for each subsequent spec:

```
Read specs/00-project.md SPEC 04 (services/gemini.py).
Implement services/gemini.py according to the spec.
Write tests/test_gemini.py covering all acceptance criteria.
Run tests and fix failures.
```
