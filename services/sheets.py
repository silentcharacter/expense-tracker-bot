"""Google Sheets client — CRUD operations for per-user Spreadsheets."""

import logging
import os
import random
import threading
import time
from datetime import datetime, date
from typing import Optional

import gspread
from gspread.exceptions import APIError
from gspread.utils import ValueRenderOption
from google.auth import default as google_auth_default
from google.oauth2.service_account import Credentials
import requests.exceptions

from models.expense import ExpenseRecord, User
from models.category import UserCategory, UserSubcategory, default_user_categories

# Module-level category cache: spreadsheet_id → (list[UserCategory], expiry_timestamp)
_category_cache: dict[str, tuple[list[UserCategory], float]] = {}
_CATEGORY_TTL = 300.0  # 5 minutes

# Module-level transaction cache: spreadsheet_id → (list[ExpenseRecord], expiry_timestamp).
# Writes invalidate, so a longer TTL is safe and keeps us well under Sheets'
# 300 reads/min/user quota when the Mini App fans out across endpoints.
_transaction_cache: dict[str, tuple[list["ExpenseRecord"], float]] = {}
_TRANSACTION_TTL = 300.0  # 5 minutes

# Module-level recurring cache: spreadsheet_id → (list[dict], expiry_timestamp).
# Writes invalidate so the Mini App always sees fresh data after edits.
_recurring_cache: dict[str, tuple[list[dict], float]] = {}
_RECURRING_TTL = 300.0  # 5 minutes

# Per-spreadsheet locks so concurrent callers coalesce onto a single fetch
# instead of each one blowing past the cache miss into the API (thundering herd).
_transaction_fetch_locks: dict[str, threading.Lock] = {}
_transaction_fetch_locks_guard = threading.Lock()


def _fetch_lock_for(spreadsheet_id: str) -> threading.Lock:
    """Return the per-spreadsheet lock used to serialise transaction fetches."""
    lock = _transaction_fetch_locks.get(spreadsheet_id)
    if lock is not None:
        return lock
    with _transaction_fetch_locks_guard:
        lock = _transaction_fetch_locks.get(spreadsheet_id)
        if lock is None:
            lock = threading.Lock()
            _transaction_fetch_locks[spreadsheet_id] = lock
        return lock

# Spreadsheets whose Transactions header has already been migrated this process lifetime.
_migrated_transactions_headers: set[str] = set()

# Module-level worksheet cache: (spreadsheet_id, sheet_name) → gspread.Worksheet.
# Avoids the metadata fetch that `Spreadsheet.worksheet()` performs on every call.
_worksheet_cache: dict[tuple[str, str], gspread.Worksheet] = {}


_SHEETS_TIMEOUT = 30  # seconds; applied to every Google Sheets HTTP call


def _with_retry(fn, *, attempts: int = 4, base_delay: float = 0.5):
    """Call a Sheets API function, retrying on transient 429/5xx/timeouts with jittered backoff."""
    for i in range(attempts):
        try:
            return fn()
        except APIError as exc:
            status = getattr(exc.response, "status_code", None)
            if status not in (429, 500, 503) or i == attempts - 1:
                raise
            delay = base_delay * (2 ** i) + random.uniform(0, 0.25)
            logger.warning("Sheets API %s — retry %d/%d in %.2fs", status, i + 1, attempts, delay)
            time.sleep(delay)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            if i == attempts - 1:
                raise
            delay = base_delay * (2 ** i) + random.uniform(0, 0.25)
            logger.warning("Sheets network error (%s) — retry %d/%d in %.2fs", exc.__class__.__name__, i + 1, attempts, delay)
            time.sleep(delay)


def _parse_budget(raw) -> float | None:
    """Parse a raw cell value into a float budget, or None if empty/invalid."""
    if raw in ("", None):
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Sheet tab names inside each user Spreadsheet
SHEET_TRANSACTIONS = "Transactions"
SHEET_DASHBOARD = "Dashboard"
SHEET_CATEGORIES = "Categories"
SHEET_RATES = "Exchange Rates"
SHEET_RECURRING = "Reccuring"  # Note: intentional typo to match existing tab name

RECURRING_HEADERS = ["id", "category", "subcategory", "description", "amount_local", "local_currency", "day_of_month"]


class SheetsError(Exception):
    """Raised on unrecoverable Sheets API errors."""


class SheetsService:
    """CRUD operations for both the Master Registry and per-user Spreadsheets.

    Authentication uses Application Default Credentials (ADC) when running
    on Cloud Functions; falls back to a service-account JSON file when the
    env var GOOGLE_APPLICATION_CREDENTIALS is set.
    """

    def __init__(self, client: Optional[gspread.Client] = None) -> None:
        self._client = client or self._build_client()
        self._registry_id = os.environ["REGISTRY_SHEET_ID"]
        # Simple in-process cache: spreadsheet_id → gspread.Spreadsheet
        self._spreadsheet_cache: dict[str, gspread.Spreadsheet] = {}

    # ── Authentication ──────────────────────────────────────────────────────

    @staticmethod
    def _build_client() -> gspread.Client:
        """Build a gspread client using ADC or service-account credentials."""
        try:
            creds, _ = google_auth_default(scopes=_SCOPES)
        except Exception:
            # Fallback: explicit service account file (local dev)
            sa_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if not sa_file:
                raise
            creds = Credentials.from_service_account_file(sa_file, scopes=_SCOPES)
        client = gspread.Client(auth=creds)
        client.http_client.timeout = _SHEETS_TIMEOUT
        return client

    # ── Low-level helpers ───────────────────────────────────────────────────

    def _get_spreadsheet(self, spreadsheet_id: str) -> gspread.Spreadsheet:
        """Return a cached or freshly opened Spreadsheet."""
        if spreadsheet_id not in self._spreadsheet_cache:
            self._spreadsheet_cache[spreadsheet_id] = self._client.open_by_key(spreadsheet_id)
        return self._spreadsheet_cache[spreadsheet_id]

    def _get_sheet(self, spreadsheet_id: str, sheet_name: str) -> gspread.Worksheet:
        """Return a named worksheet, cached at module level to skip the per-call metadata fetch."""
        key = (spreadsheet_id, sheet_name)
        ws = _worksheet_cache.get(key)
        if ws is not None:
            return ws
        ws = _with_retry(lambda: self._get_spreadsheet(spreadsheet_id).worksheet(sheet_name))
        _worksheet_cache[key] = ws
        return ws

    # ── Transactions ────────────────────────────────────────────────────────

    def append_transaction(self, spreadsheet_id: str, record: ExpenseRecord) -> None:
        """Append a single expense record to the Transactions sheet.

        Args:
            spreadsheet_id: User's personal Spreadsheet ID.
            record:         Fully populated ExpenseRecord.
        """
        self._ensure_transactions_columns(spreadsheet_id)
        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        sheet.append_row(record.to_sheet_row(), value_input_option="RAW")
        _transaction_cache.pop(spreadsheet_id, None)
        logger.info("Appended transaction %s to %s", record.id, spreadsheet_id)

    def delete_last_transaction(self, spreadsheet_id: str) -> Optional[ExpenseRecord]:
        """Delete the most recent transaction row and return it.

        Returns:
            The deleted ExpenseRecord, or None if the sheet is empty.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        all_values = sheet.get_all_values(value_render_option=ValueRenderOption.unformatted)
        if len(all_values) <= 1:  # header only
            return None

        last_row_index = len(all_values)  # 1-based, header = row 1
        last_row = all_values[-1]
        sheet.delete_rows(last_row_index)
        _transaction_cache.pop(spreadsheet_id, None)

        headers = ExpenseRecord.sheet_headers()
        row_dict = dict(zip(headers, last_row))
        try:
            return ExpenseRecord(**row_dict)
        except Exception as exc:
            logger.warning("Could not parse deleted row into ExpenseRecord: %s", exc)
            return None

    def _ensure_transactions_columns(self, spreadsheet_id: str) -> None:
        """Append any missing Transactions header columns introduced after the
        original schema (e.g. ``recurring``, ``recurring_template_id``).

        Idempotent and cached per process — only the first call per spreadsheet
        actually touches the API.
        """
        if spreadsheet_id in _migrated_transactions_headers:
            return
        try:
            sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
            existing = sheet.row_values(1)
            expected = ExpenseRecord.sheet_headers()
            if not existing:
                sheet.insert_row(expected, index=1)
            else:
                for i, col_name in enumerate(expected):
                    col_num = i + 1
                    if col_num > len(existing):
                        sheet.update_cell(1, col_num, col_name)
        except Exception as exc:
            logger.warning("Could not migrate transactions header for %s: %s", spreadsheet_id, exc)
        _migrated_transactions_headers.add(spreadsheet_id)

    def _get_all_transactions(self, spreadsheet_id: str) -> list[ExpenseRecord]:
        """Return every parsed record for a spreadsheet, with a TTL cache.

        Concurrent callers that miss the cache are serialised on a per-spreadsheet
        lock so only one of them hits the API; the rest pick up the freshly cached
        result on their second check.
        """
        cached = _transaction_cache.get(spreadsheet_id)
        if cached and time.monotonic() < cached[1]:
            return cached[0]

        with _fetch_lock_for(spreadsheet_id):
            cached = _transaction_cache.get(spreadsheet_id)
            if cached and time.monotonic() < cached[1]:
                return cached[0]

            self._ensure_transactions_columns(spreadsheet_id)
            sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
            rows = _with_retry(lambda: sheet.get_all_records(
                expected_headers=ExpenseRecord.sheet_headers(),
                value_render_option=ValueRenderOption.unformatted,
            ))

            records: list[ExpenseRecord] = []
            for row in rows:
                try:
                    records.append(ExpenseRecord(**row))
                except Exception:
                    continue

            records.sort(key=lambda r: r.timestamp, reverse=True)
            _transaction_cache[spreadsheet_id] = (records, time.monotonic() + _TRANSACTION_TTL)
            logger.debug("Cached %d transactions for %s (TTL %.0fs)", len(records), spreadsheet_id, _TRANSACTION_TTL)
            return records

    def get_transactions(
        self,
        spreadsheet_id: str,
        since: Optional[date] = None,
        until: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[ExpenseRecord]:
        """Fetch transactions optionally filtered by date range.

        Uses an in-memory TTL cache (invalidated on write) to collapse burst
        reads from the mini app — multiple endpoints reading the same sheet
        in parallel share a single underlying fetch.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            since:          Inclusive start date (UTC).
            until:          Inclusive end date (UTC).
            limit:          Maximum number of rows to return (most recent first).

        Returns:
            List of ExpenseRecord ordered by timestamp descending.
        """
        all_records = self._get_all_transactions(spreadsheet_id)

        if since or until:
            filtered: list[ExpenseRecord] = []
            for r in all_records:
                d = r.timestamp.date()
                if since and d < since:
                    continue
                if until and d > until:
                    continue
                filtered.append(r)
        else:
            filtered = list(all_records)

        if limit:
            filtered = filtered[:limit]
        return filtered

    def get_last_n_transactions(self, spreadsheet_id: str, n: int = 10) -> list[ExpenseRecord]:
        """Return the n most recent transactions."""
        return self.get_transactions(spreadsheet_id, limit=n)

    # ── Budget (Categories sheet) ────────────────────────────────────────────

    def get_categories(self, spreadsheet_id: str) -> list[UserCategory]:
        """Read user's categories from the Categories sheet with a 5-minute TTL cache.

        Expects columns: slug, label, budget (budget is optional).
        Falls back to default CATEGORIES if the sheet is empty or unreadable.

        Returns:
            List of UserCategory for this user.
        """
        now = time.monotonic()
        cached = _category_cache.get(spreadsheet_id)
        if cached and now < cached[1]:
            return cached[0]

        categories: list[UserCategory] = []
        sheet_was_empty = False
        try:
            sheet = self._get_sheet(spreadsheet_id, SHEET_CATEGORIES)
            rows = sheet.get_all_records()
            # Accumulate into cat_data before constructing models (subcategory rows
            # may appear before or after their parent category row)
            cat_data: dict[str, dict] = {}
            for row in rows:
                # Support new "category" column and legacy "slug" column name
                cat_slug = str(row.get("category") or row.get("slug", "")).strip().lower()
                sub_slug = str(row.get("subcategory", "")).strip().lower()
                label = str(row.get("label", "")).strip()
                budget = _parse_budget(row.get("budget", ""))
                if not cat_slug:
                    continue
                entry = cat_data.setdefault(cat_slug, {"label": "", "budget": None, "subs": []})
                if not sub_slug:  # category row
                    if label:
                        entry["label"] = label
                    if budget is not None:
                        entry["budget"] = budget
                else:  # subcategory row
                    entry["subs"].append((sub_slug, label, budget))

            from models.category import category_label as _cat_label
            for slug, info in cat_data.items():
                label = info["label"] or _cat_label(slug)
                subs = [
                    UserSubcategory(
                        slug=s,
                        label=lbl or s.replace("_", " ").capitalize(),
                        budget=b,
                    )
                    for s, lbl, b in info["subs"]
                ]
                # If no category-level budget, aggregate subcategory budgets.
                effective_budget = info["budget"]
                if effective_budget is None:
                    sub_total = sum(b for _, _, b in info["subs"] if b is not None)
                    if sub_total > 0:
                        effective_budget = sub_total
                categories.append(UserCategory(slug=slug, label=label, budget=effective_budget, subcategories=subs))

            if not categories:
                sheet_was_empty = True
        except Exception as exc:
            logger.warning("Could not read categories for %s: %s", spreadsheet_id, exc)
            sheet_was_empty = True

        if not categories:
            categories = default_user_categories()
            if sheet_was_empty:
                # Seed the sheet so the user can configure labels and budgets
                try:
                    self.ensure_categories_sheet(spreadsheet_id)
                except Exception as exc:
                    logger.warning("Could not seed categories sheet for %s: %s", spreadsheet_id, exc)

        _category_cache[spreadsheet_id] = (categories, now + _CATEGORY_TTL)
        return categories

    def ensure_categories_sheet(self, spreadsheet_id: str) -> None:
        """Write headers and default category/subcategory rows to Categories sheet if empty.

        Schema: category | subcategory | label | budget
        Category row: subcategory column is empty.
        Subcategory row: subcategory column is filled.

        Safe to call on new or existing spreadsheets — leaves existing data intact.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_CATEGORIES)
        existing = sheet.get_all_values()
        if existing and len(existing) > 1:
            return  # user has already configured categories, leave them

        headers = ["category", "subcategory", "label", "budget"]
        sheet.clear()
        sheet.insert_row(headers, index=1)

        rows = []
        for cat in default_user_categories():
            rows.append([cat.slug, "", cat.label, ""])
            for sub in cat.subcategories:
                rows.append([cat.slug, sub.slug, sub.label, ""])
        sheet.append_rows(rows, value_input_option="RAW")
        logger.info("Seeded %d category/subcategory rows for spreadsheet %s", len(rows), spreadsheet_id)

    def get_budgets(self, spreadsheet_id: str) -> dict[str, float]:
        """Read category budgets from the Categories sheet.

        A category budget is either the value on the category row itself, or
        the sum of all subcategory budgets when no category-level budget is set.

        Returns:
            Dict mapping category slug → budget amount in base currency.
        """
        result: dict[str, float] = {}
        for cat in self.get_categories(spreadsheet_id):
            if cat.budget is not None:
                result[cat.slug] = cat.budget
            else:
                sub_total = sum(s.budget for s in cat.subcategories if s.budget is not None)
                if sub_total > 0:
                    result[cat.slug] = sub_total
        return result

    # ── Master Registry ──────────────────────────────────────────────────────

    def find_user(self, telegram_id: int) -> Optional[User]:
        """Look up a user in the Master Registry by Telegram ID.

        Uses only the required base headers for validation so that registries
        that pre-date the notification columns can still be read correctly;
        Pydantic defaults fill in any missing optional fields.

        Returns:
            User if found, None otherwise.
        """
        sheet = self._get_sheet(self._registry_id, "Registry")
        rows = sheet.get_all_records(expected_headers=User.required_registry_headers())
        for row in rows:
            if int(row.get("telegram_id", 0)) == telegram_id:
                try:
                    return User(**row)
                except Exception as exc:
                    logger.error("Malformed registry row for %s: %s", telegram_id, exc)
                    return None
        return None

    def get_all_active_users(self) -> list[User]:
        """Return all active users from the Master Registry."""
        from models.expense import UserStatus

        sheet = self._get_sheet(self._registry_id, "Registry")
        rows = sheet.get_all_records(expected_headers=User.required_registry_headers())
        users: list[User] = []
        for row in rows:
            try:
                user = User(**row)
                if user.status == UserStatus.active:
                    users.append(user)
            except Exception as exc:
                logger.error("Malformed registry row: %s", exc)
        return users

    def register_user(self, user: User) -> None:
        """Append a new user row to the Master Registry.

        Args:
            user: Fully populated User model.
        """
        sheet = self._get_sheet(self._registry_id, "Registry")
        sheet.append_row(user.to_registry_row(), value_input_option="USER_ENTERED")
        logger.info("Registered user %s (%s)", user.telegram_id, user.display_name)

    def append_feedback(self, telegram_id: int, username: str, display_name: str, feedback: str) -> None:
        """Append user feedback to the Feedback tab of the Registry spreadsheet."""
        sheet = self._get_sheet(self._registry_id, "Feedback")
        sheet.append_row([str(telegram_id), username, display_name, feedback], value_input_option="USER_ENTERED")
        logger.info("Appended feedback from %s", telegram_id)

    def update_user_email(self, telegram_id: int, email: str) -> bool:
        """Set the email field for an existing user in the Master Registry.

        Returns:
            True if the row was found and updated, False otherwise.
        """
        sheet = self._get_sheet(self._registry_id, "Registry")
        cell = sheet.find(str(telegram_id), in_column=1)
        if cell is None:
            return False
        headers = User.registry_headers()
        email_col = headers.index("email") + 1  # gspread columns are 1-based
        sheet.update_cell(cell.row, email_col, email)
        return True

    def update_user_settings(
        self,
        telegram_id: int,
        base_currency: Optional[str] = None,
        default_currency: Optional[str] = None,
        budget_alerts: Optional[bool] = None,
        weekly_summary: Optional[bool] = None,
        insights: Optional[bool] = None,
    ) -> bool:
        """Update mutable settings for an existing user in the Registry.

        Only the fields that are not None are written; others are left unchanged.
        Notification columns are appended to the sheet row when they do not yet
        exist (backward-compatible with registries created before this feature).

        Returns:
            True if the row was found and updated, False otherwise.
        """
        sheet = self._get_sheet(self._registry_id, "Registry")
        cell = sheet.find(str(telegram_id), in_column=1)
        if cell is None:
            return False

        headers = User.registry_headers()
        # Determine actual column count of the sheet header row to know whether
        # notification columns need to be appended or can be updated in place.
        header_row = sheet.row_values(1)
        actual_col_count = len(header_row)

        updates: dict[str, object] = {}
        if base_currency is not None:
            updates["base_currency"] = base_currency.upper()
        if default_currency is not None:
            updates["default_currency"] = default_currency.upper()
        if budget_alerts is not None:
            updates["budget_alerts"] = str(budget_alerts).upper()
        if weekly_summary is not None:
            updates["weekly_summary"] = str(weekly_summary).upper()
        if insights is not None:
            updates["insights"] = str(insights).upper()

        for field_name, value in updates.items():
            col_idx = headers.index(field_name)  # 0-based
            col_num = col_idx + 1  # gspread is 1-based
            if col_num > actual_col_count:
                # Column does not exist yet — extend header row first.
                sheet.update_cell(1, col_num, field_name)
            sheet.update_cell(cell.row, col_num, value)

        return True

    def delete_transaction_by_id(self, spreadsheet_id: str, expense_id: str) -> Optional[ExpenseRecord]:
        """Find a transaction by ID, delete its row, and return the deleted record.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            expense_id:     UUID of the expense to delete.

        Returns:
            The deleted ExpenseRecord, or None if not found.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        all_values = sheet.get_all_values(value_render_option=ValueRenderOption.unformatted)
        if len(all_values) <= 1:
            return None

        headers = ExpenseRecord.sheet_headers()
        id_col = headers.index("id")

        for row_idx, row in enumerate(all_values):
            if row_idx == 0:  # skip header
                continue
            if len(row) > id_col and str(row[id_col]) == expense_id:
                row_dict = dict(zip(headers, row))
                try:
                    record: Optional[ExpenseRecord] = ExpenseRecord(**row_dict)
                except Exception as exc:
                    logger.warning("Could not parse row into ExpenseRecord during delete: %s", exc)
                    record = None
                sheet.delete_rows(row_idx + 1)  # gspread rows are 1-based
                _transaction_cache.pop(spreadsheet_id, None)
                logger.info("Deleted transaction %s from %s", expense_id, spreadsheet_id)
                return record

        return None

    def update_transaction_category(
        self, spreadsheet_id: str, record_id: str, category: str, subcategory: str
    ) -> bool:
        """Find a transaction by ID and update its category and subcategory cells.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            record_id:      UUID of the expense to update.
            category:       New category slug.
            subcategory:    New subcategory slug (empty string to clear).

        Returns:
            True if the row was found and updated, False otherwise.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        all_values = sheet.get_all_values(value_render_option=ValueRenderOption.unformatted)
        if len(all_values) <= 1:
            return False

        headers = ExpenseRecord.sheet_headers()
        id_col = headers.index("id")
        cat_col = headers.index("category") + 1    # 1-based for gspread
        sub_col = headers.index("subcategory") + 1

        for row_idx, row in enumerate(all_values):
            if row_idx == 0:  # skip header
                continue
            if len(row) > id_col and str(row[id_col]) == record_id:
                sheet.update_cell(row_idx + 1, cat_col, category)
                sheet.update_cell(row_idx + 1, sub_col, subcategory)
                _transaction_cache.pop(spreadsheet_id, None)
                logger.info(
                    "Updated category for transaction %s in %s: %s/%s",
                    record_id, spreadsheet_id, category, subcategory,
                )
                return True

        return False

    def update_transaction_description(
        self, spreadsheet_id: str, record_id: str, description: str
    ) -> bool:
        """Find a transaction by ID and update its description cell.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            record_id:      UUID of the expense to update.
            description:    New description text.

        Returns:
            True if the row was found and updated, False otherwise.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        all_values = sheet.get_all_values(value_render_option=ValueRenderOption.unformatted)
        if len(all_values) <= 1:
            return False

        headers = ExpenseRecord.sheet_headers()
        id_col = headers.index("id")
        desc_col = headers.index("description") + 1  # 1-based for gspread

        for row_idx, row in enumerate(all_values):
            if row_idx == 0:  # skip header
                continue
            if len(row) > id_col and str(row[id_col]) == record_id:
                sheet.update_cell(row_idx + 1, desc_col, description)
                _transaction_cache.pop(spreadsheet_id, None)
                logger.info(
                    "Updated description for transaction %s in %s",
                    record_id, spreadsheet_id,
                )
                return True

        return False

    def update_subcategory_budgets(self, spreadsheet_id: str, budgets: dict[str, float]) -> None:
        """Update budget amounts for subcategory rows in the Categories sheet.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            budgets:        Mapping of "category/subcategory" → new budget amount.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_CATEGORIES)
        all_values = sheet.get_all_values()
        if not all_values or len(all_values) < 2:
            return

        raw_headers = [h.lower().strip() for h in all_values[0]]
        cat_col = next((i for i, h in enumerate(raw_headers) if h in ("category", "slug")), None)
        sub_col = next((i for i, h in enumerate(raw_headers) if h == "subcategory"), None)
        budget_col = next((i for i, h in enumerate(raw_headers) if h == "budget"), None)

        if cat_col is None or sub_col is None or budget_col is None:
            logger.warning(
                "Could not find required columns in Categories sheet for %s", spreadsheet_id
            )
            return

        updates: list[tuple[int, int, float]] = []
        for row_idx, row in enumerate(all_values[1:], start=2):
            cat_slug = str(row[cat_col]).strip().lower() if len(row) > cat_col else ""
            sub_slug = str(row[sub_col]).strip().lower() if len(row) > sub_col else ""
            if not cat_slug or not sub_slug:
                continue
            key = f"{cat_slug}/{sub_slug}"
            if key in budgets:
                updates.append((row_idx, budget_col + 1, budgets[key]))

        for row_num, col_num, value in updates:
            sheet.update_cell(row_num, col_num, value)

        _category_cache.pop(spreadsheet_id, None)
        logger.info("Updated %d subcategory budgets for %s", len(updates), spreadsheet_id)

    def update_category_budgets(self, spreadsheet_id: str, budgets: dict[str, float]) -> None:
        """Update budget amounts for the given category slugs in the Categories sheet.

        Only updates category-level rows (rows where subcategory column is empty).
        Invalidates the in-memory category cache after writing.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            budgets:        Mapping of category slug → new budget amount.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_CATEGORIES)
        all_values = sheet.get_all_values()
        if not all_values or len(all_values) < 2:
            return

        raw_headers = [h.lower().strip() for h in all_values[0]]
        # Support both "category" (new schema) and "slug" (legacy)
        cat_col = next((i for i, h in enumerate(raw_headers) if h in ("category", "slug")), None)
        sub_col = next((i for i, h in enumerate(raw_headers) if h == "subcategory"), None)
        budget_col = next((i for i, h in enumerate(raw_headers) if h == "budget"), None)

        if cat_col is None or budget_col is None:
            logger.warning(
                "Could not find required columns in Categories sheet for %s", spreadsheet_id
            )
            return

        updates: list[tuple[int, int, float]] = []
        for row_idx, row in enumerate(all_values[1:], start=2):  # skip header; 1-based
            cat_slug = str(row[cat_col]).strip().lower() if len(row) > cat_col else ""
            sub_slug = (
                str(row[sub_col]).strip().lower()
                if sub_col is not None and len(row) > sub_col
                else ""
            )
            if cat_slug in budgets and not sub_slug:
                updates.append((row_idx, budget_col + 1, budgets[cat_slug]))

        for row_num, col_num, value in updates:
            sheet.update_cell(row_num, col_num, value)

        _category_cache.pop(spreadsheet_id, None)
        logger.info("Updated %d category budgets for %s", len(updates), spreadsheet_id)

    def add_category(
        self,
        spreadsheet_id: str,
        slug: str,
        label: str,
        budget: float | None = None,
    ) -> None:
        """Append a new category row to the Categories sheet.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            slug:           URL-safe identifier (lowercase, underscores).
            label:          Human-readable category name.
            budget:         Optional monthly budget amount in base currency.

        Raises:
            ValueError: If a category with the same slug already exists.
        """
        existing = self.get_categories(spreadsheet_id)
        if any(cat.slug == slug for cat in existing):
            raise ValueError(f"Category '{slug}' already exists")

        sheet = self._get_sheet(spreadsheet_id, SHEET_CATEGORIES)
        row = [slug, "", label, budget if budget is not None else ""]
        sheet.append_row(row, value_input_option="RAW")

        _category_cache.pop(spreadsheet_id, None)
        logger.info("Added category '%s' to spreadsheet %s", slug, spreadsheet_id)

    def add_subcategory(
        self,
        spreadsheet_id: str,
        cat_slug: str,
        sub_slug: str,
        label: str,
    ) -> None:
        """Append a new subcategory row to the Categories sheet.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            cat_slug:       Parent category slug.
            sub_slug:       URL-safe subcategory identifier.
            label:          Human-readable subcategory name.

        Raises:
            ValueError: If the parent category is not found or the subcategory slug already exists.
        """
        existing = self.get_categories(spreadsheet_id)
        cat = next((c for c in existing if c.slug == cat_slug), None)
        if cat is None:
            raise ValueError(f"Category '{cat_slug}' not found")
        if any(s.slug == sub_slug for s in cat.subcategories):
            raise ValueError(f"Subcategory '{sub_slug}' already exists in '{cat_slug}'")

        sheet = self._get_sheet(spreadsheet_id, SHEET_CATEGORIES)
        sheet.append_row([cat_slug, sub_slug, label, ""], value_input_option="RAW")

        _category_cache.pop(spreadsheet_id, None)
        logger.info("Added subcategory '%s/%s' to spreadsheet %s", cat_slug, sub_slug, spreadsheet_id)

    def delete_category(self, spreadsheet_id: str, cat_slug: str) -> bool:
        """Delete a category and all its subcategories from the Categories sheet.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            cat_slug:       Slug of the category to delete.

        Returns:
            True if any rows were deleted, False if category not found.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_CATEGORIES)
        all_values = sheet.get_all_values()
        rows_to_delete = [
            i + 1  # 1-based row index
            for i, row in enumerate(all_values)
            if len(row) > 0 and row[0] == cat_slug
        ]
        if not rows_to_delete:
            return False
        # Delete in reverse order to keep row indices valid
        for row_num in reversed(rows_to_delete):
            sheet.delete_rows(row_num)
        _category_cache.pop(spreadsheet_id, None)
        logger.info("Deleted category '%s' (%d rows) from %s", cat_slug, len(rows_to_delete), spreadsheet_id)
        return True

    def delete_subcategory(self, spreadsheet_id: str, cat_slug: str, sub_slug: str) -> bool:
        """Delete a single subcategory row from the Categories sheet.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            cat_slug:       Parent category slug.
            sub_slug:       Subcategory slug to delete.

        Returns:
            True if deleted, False if not found.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_CATEGORIES)
        all_values = sheet.get_all_values()
        for i, row in enumerate(all_values):
            if len(row) >= 2 and row[0] == cat_slug and row[1] == sub_slug:
                sheet.delete_rows(i + 1)
                _category_cache.pop(spreadsheet_id, None)
                logger.info("Deleted subcategory '%s/%s' from %s", cat_slug, sub_slug, spreadsheet_id)
                return True
        return False

    # ── Recurring expenses ───────────────────────────────────────────────────

    def get_recurring(self, spreadsheet_id: str) -> list[dict]:
        """Return all rows from the Recurring sheet as a list of dicts.

        Uses an in-memory TTL cache to collapse burst reads from parallel
        Mini App endpoints (e.g. /api/summary and /api/recurring arriving together).
        """
        now = time.monotonic()
        cached = _recurring_cache.get(spreadsheet_id)
        if cached and now < cached[1]:
            return cached[0]

        sheet = self._get_sheet(spreadsheet_id, SHEET_RECURRING)
        header = sheet.row_values(1)
        if not header:
            result: list[dict] = []
        else:
            result = sheet.get_all_records()

        _recurring_cache[spreadsheet_id] = (result, now + _RECURRING_TTL)
        return result

    def add_recurring(self, spreadsheet_id: str, entry: dict) -> None:
        """Append one recurring entry. Writes headers first if the sheet is empty."""
        _recurring_cache.pop(spreadsheet_id, None)
        import uuid
        sheet = self._get_sheet(spreadsheet_id, SHEET_RECURRING)
        if not sheet.row_values(1):
            sheet.append_row(RECURRING_HEADERS)
        row = [
            entry.get("id") or str(uuid.uuid4()),
            entry.get("category", ""),
            entry.get("subcategory", ""),
            entry.get("description", ""),
            entry.get("amount_local", ""),
            entry.get("local_currency", ""),
            entry.get("day_of_month", 1),
        ]
        sheet.append_row(row)

    def delete_recurring(self, spreadsheet_id: str, entry_id: str) -> bool:
        """Delete a recurring entry by its id value. Returns True if found and deleted."""
        _recurring_cache.pop(spreadsheet_id, None)
        sheet = self._get_sheet(spreadsheet_id, SHEET_RECURRING)
        all_values = sheet.get_all_values()
        for i, row in enumerate(all_values):
            if i == 0:
                continue  # skip header
            if row and row[0] == entry_id:
                sheet.delete_rows(i + 1)
                return True
        return False

    def clear_all_transactions(self, spreadsheet_id: str) -> int:
        """Delete every data row from the Transactions sheet, keeping the header.

        Args:
            spreadsheet_id: User's Spreadsheet ID.

        Returns:
            Number of rows deleted.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        all_values = sheet.get_all_values()
        num_data_rows = max(0, len(all_values) - 1)  # exclude header
        if num_data_rows == 0:
            return 0
        # Delete from last row upward to avoid index shifting.
        last_row = len(all_values)
        sheet.delete_rows(2, last_row)
        _transaction_cache.pop(spreadsheet_id, None)
        logger.info("Cleared %d transactions from spreadsheet %s", num_data_rows, spreadsheet_id)
        return num_data_rows

    # ── Spreadsheet initialisation ───────────────────────────────────────────

    def ensure_transactions_header(self, spreadsheet_id: str) -> None:
        """Write column headers to Transactions sheet, appending any missing columns.

        Safe to call on new or existing spreadsheets — preserves existing data
        and only adds columns that are not already present in row 1.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        expected = ExpenseRecord.sheet_headers()
        existing = sheet.row_values(1) if sheet.row_count > 0 else []
        if not existing:
            sheet.insert_row(expected, index=1)
        else:
            for i, col_name in enumerate(expected):
                col_num = i + 1
                if col_num > len(existing):
                    sheet.update_cell(1, col_num, col_name)
        _migrated_transactions_headers.add(spreadsheet_id)

    def ensure_registry_header(self) -> None:
        """Write column headers to Master Registry; append any missing columns."""
        sheet = self._get_sheet(self._registry_id, "Registry")
        expected = User.registry_headers()
        if sheet.row_count == 0 or not sheet.row_values(1):
            sheet.insert_row(expected, index=1)
        else:
            existing = sheet.row_values(1)
            for i, col_name in enumerate(expected):
                col_num = i + 1
                if col_num > len(existing):
                    sheet.update_cell(1, col_num, col_name)
