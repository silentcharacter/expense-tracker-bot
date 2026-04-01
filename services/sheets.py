"""Google Sheets client — CRUD operations for per-user Spreadsheets."""

import logging
import os
import time
from datetime import datetime, date
from typing import Optional

import gspread
from gspread.utils import ValueRenderOption
from google.auth import default as google_auth_default
from google.oauth2.service_account import Credentials

from models.expense import ExpenseRecord, User
from models.category import UserCategory, UserSubcategory, default_user_categories

# Module-level category cache: spreadsheet_id → (list[UserCategory], expiry_timestamp)
_category_cache: dict[str, tuple[list[UserCategory], float]] = {}
_CATEGORY_TTL = 300.0  # 5 minutes

# Module-level transaction cache: spreadsheet_id → (list[ExpenseRecord], expiry_timestamp)
# Short TTL to collapse burst reads from the mini app without serving very stale data.
_transaction_cache: dict[str, tuple[list["ExpenseRecord"], float]] = {}
_TRANSACTION_TTL = 30.0  # 30 seconds


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
        return gspread.Client(auth=creds)

    # ── Low-level helpers ───────────────────────────────────────────────────

    def _get_spreadsheet(self, spreadsheet_id: str) -> gspread.Spreadsheet:
        """Return a cached or freshly opened Spreadsheet."""
        if spreadsheet_id not in self._spreadsheet_cache:
            self._spreadsheet_cache[spreadsheet_id] = self._client.open_by_key(spreadsheet_id)
        return self._spreadsheet_cache[spreadsheet_id]

    def _get_sheet(self, spreadsheet_id: str, sheet_name: str) -> gspread.Worksheet:
        """Return a named worksheet from a spreadsheet."""
        return self._get_spreadsheet(spreadsheet_id).worksheet(sheet_name)

    # ── Transactions ────────────────────────────────────────────────────────

    def append_transaction(self, spreadsheet_id: str, record: ExpenseRecord) -> None:
        """Append a single expense record to the Transactions sheet.

        Args:
            spreadsheet_id: User's personal Spreadsheet ID.
            record:         Fully populated ExpenseRecord.
        """
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

    def _get_all_transactions(self, spreadsheet_id: str) -> list[ExpenseRecord]:
        """Return every parsed record for a spreadsheet, with 30s TTL cache."""
        now = time.monotonic()
        cached = _transaction_cache.get(spreadsheet_id)
        if cached and now < cached[1]:
            return cached[0]

        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        rows = sheet.get_all_records(
            expected_headers=ExpenseRecord.sheet_headers(),
            value_render_option=ValueRenderOption.unformatted,
        )

        records: list[ExpenseRecord] = []
        for row in rows:
            try:
                records.append(ExpenseRecord(**row))
            except Exception:
                continue

        records.sort(key=lambda r: r.timestamp, reverse=True)
        _transaction_cache[spreadsheet_id] = (records, now + _TRANSACTION_TTL)
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

        Uses a short in-memory TTL cache to collapse burst reads from the
        mini app (multiple endpoints reading the same sheet in parallel).

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
                categories.append(UserCategory(slug=slug, label=label, budget=info["budget"], subcategories=subs))

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

        Returns:
            Dict mapping category slug → budget amount in base currency.
        """
        return {
            cat.slug: cat.budget
            for cat in self.get_categories(spreadsheet_id)
            if cat.budget is not None
        }

    # ── Master Registry ──────────────────────────────────────────────────────

    def find_user(self, telegram_id: int) -> Optional[User]:
        """Look up a user in the Master Registry by Telegram ID.

        Returns:
            User if found, None otherwise.
        """
        sheet = self._get_sheet(self._registry_id, "Registry")
        rows = sheet.get_all_records(expected_headers=User.registry_headers())
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
        rows = sheet.get_all_records(expected_headers=User.registry_headers())
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

    def update_user_settings(self, telegram_id: int, base_currency: str, default_currency: str) -> bool:
        """Update base_currency and default_currency for an existing user.

        Returns:
            True if the row was found and updated, False otherwise.
        """
        sheet = self._get_sheet(self._registry_id, "Registry")
        cell = sheet.find(str(telegram_id), in_column=1)
        if cell is None:
            return False
        headers = User.registry_headers()
        base_col = headers.index("base_currency") + 1
        default_col = headers.index("default_currency") + 1
        sheet.update_cell(cell.row, base_col, base_currency.upper())
        sheet.update_cell(cell.row, default_col, default_currency.upper())
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

    # ── Spreadsheet initialisation ───────────────────────────────────────────

    def ensure_transactions_header(self, spreadsheet_id: str) -> None:
        """Write column headers to Transactions sheet if it is empty.

        Safe to call on new or existing spreadsheets.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        if sheet.row_count == 0 or not sheet.row_values(1):
            sheet.insert_row(ExpenseRecord.sheet_headers(), index=1)

    def ensure_registry_header(self) -> None:
        """Write column headers to Master Registry if it is empty."""
        sheet = self._get_sheet(self._registry_id, "Registry")
        if sheet.row_count == 0 or not sheet.row_values(1):
            sheet.insert_row(User.registry_headers(), index=1)
