"""Google Sheets client — CRUD operations for per-user Spreadsheets."""

import logging
import os
from datetime import datetime, date
from typing import Optional

import gspread
from google.auth import default as google_auth_default
from google.oauth2.service_account import Credentials

from models.expense import ExpenseRecord, User

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
        sheet.append_row(record.to_sheet_row(), value_input_option="USER_ENTERED")
        logger.info("Appended transaction %s to %s", record.id, spreadsheet_id)

    def delete_last_transaction(self, spreadsheet_id: str) -> Optional[ExpenseRecord]:
        """Delete the most recent transaction row and return it.

        Returns:
            The deleted ExpenseRecord, or None if the sheet is empty.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        all_values = sheet.get_all_values()
        if len(all_values) <= 1:  # header only
            return None

        last_row_index = len(all_values)  # 1-based, header = row 1
        last_row = all_values[-1]
        sheet.delete_rows(last_row_index)

        headers = ExpenseRecord.sheet_headers()
        row_dict = dict(zip(headers, last_row))
        try:
            return ExpenseRecord(**row_dict)
        except Exception as exc:
            logger.warning("Could not parse deleted row into ExpenseRecord: %s", exc)
            return None

    def get_transactions(
        self,
        spreadsheet_id: str,
        since: Optional[date] = None,
        until: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[ExpenseRecord]:
        """Fetch transactions optionally filtered by date range.

        Args:
            spreadsheet_id: User's Spreadsheet ID.
            since:          Inclusive start date (UTC).
            until:          Inclusive end date (UTC).
            limit:          Maximum number of rows to return (most recent first).

        Returns:
            List of ExpenseRecord ordered by timestamp descending.
        """
        sheet = self._get_sheet(spreadsheet_id, SHEET_TRANSACTIONS)
        rows = sheet.get_all_records(expected_headers=ExpenseRecord.sheet_headers())

        records: list[ExpenseRecord] = []
        for row in rows:
            try:
                record = ExpenseRecord(**row)
            except Exception:
                continue
            if since and record.timestamp.date() < since:
                continue
            if until and record.timestamp.date() > until:
                continue
            records.append(record)

        # Sort descending by timestamp
        records.sort(key=lambda r: r.timestamp, reverse=True)

        if limit:
            records = records[:limit]
        return records

    def get_last_n_transactions(self, spreadsheet_id: str, n: int = 10) -> list[ExpenseRecord]:
        """Return the n most recent transactions."""
        return self.get_transactions(spreadsheet_id, limit=n)

    # ── Budget (Categories sheet) ────────────────────────────────────────────

    def get_budgets(self, spreadsheet_id: str) -> dict[str, float]:
        """Read category budgets from the Categories sheet.

        Returns:
            Dict mapping category slug → budget amount in base currency.
        """
        try:
            sheet = self._get_sheet(spreadsheet_id, SHEET_CATEGORIES)
            rows = sheet.get_all_records()
            return {
                row["category"]: float(row["budget"])
                for row in rows
                if row.get("category") and row.get("budget")
            }
        except Exception as exc:
            logger.warning("Could not read budgets: %s", exc)
            return {}

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

    def register_user(self, user: User) -> None:
        """Append a new user row to the Master Registry.

        Args:
            user: Fully populated User model.
        """
        sheet = self._get_sheet(self._registry_id, "Registry")
        sheet.append_row(user.to_registry_row(), value_input_option="USER_ENTERED")
        logger.info("Registered user %s (%s)", user.telegram_id, user.display_name)

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
