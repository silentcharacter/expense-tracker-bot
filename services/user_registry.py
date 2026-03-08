"""User registration, Spreadsheet provisioning, and ISO 4217 validation."""

import logging
import os
from datetime import datetime
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth import default as google_auth_default

from models.expense import User, UserRole, UserStatus
from services.sheets import SheetsService

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

# Comprehensive ISO 4217 alphabetic currency codes
_ISO_4217_CODES: frozenset[str] = frozenset(
    {
        "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
        "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL",
        "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHF", "CLP", "CNY",
        "COP", "CRC", "CUP", "CVE", "CZK", "DJF", "DKK", "DOP", "DZD", "EGP",
        "ERN", "ETB", "EUR", "FJD", "FKP", "GBP", "GEL", "GHS", "GIP", "GMD",
        "GNF", "GTQ", "GYD", "HKD", "HNL", "HRK", "HTG", "HUF", "IDR", "ILS",
        "INR", "IQD", "IRR", "ISK", "JMD", "JOD", "JPY", "KES", "KGS", "KHR",
        "KMF", "KPW", "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR", "LRD",
        "LSL", "LYD", "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU",
        "MUR", "MVR", "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK",
        "NPR", "NZD", "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG",
        "QAR", "RON", "RSD", "RUB", "RWF", "SAR", "SBD", "SCR", "SDG", "SEK",
        "SGD", "SHP", "SLL", "SOS", "SRD", "STN", "SVC", "SYP", "SZL", "THB",
        "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX",
        "USD", "UYU", "UZS", "VES", "VND", "VUV", "WST", "XAF", "XCD", "XOF",
        "XPF", "YER", "ZAR", "ZMW", "ZWL",
    }
)


class UserRegistryError(Exception):
    """Raised on unrecoverable user registry errors."""


class UserRegistry:
    """Manages user registration and personal Spreadsheet creation.

    On first use, copies a template Spreadsheet, grants the service account
    editor access, and records the new user in the Master Registry sheet.
    Subsequent look-ups are served from an in-process cache.
    """

    def __init__(
        self,
        sheets_service: Optional[SheetsService] = None,
        drive_service=None,
    ) -> None:
        self._sheets = sheets_service or SheetsService()
        self._drive = drive_service or self._build_drive_service()
        self._template_id = os.environ["TEMPLATE_SHEET_ID"]
        self._folder_id = os.environ["USERS_FOLDER_ID"]
        self._admin_email = os.environ["ADMIN_EMAIL"]
        # telegram_id (int) → User
        self._cache: dict[int, User] = {}

    # ── Public API ──────────────────────────────────────────────────────────

    async def get_user(self, telegram_id: int) -> Optional[User]:
        """Return the User for a given Telegram ID (cache → Sheets).

        Returns:
            User if registered, None if not found.
        """
        if telegram_id in self._cache:
            return self._cache[telegram_id]
        user = self._sheets.find_user(telegram_id)
        if user:
            self._cache[telegram_id] = user
        return user

    async def create_user(
        self,
        telegram_id: int,
        username: str,
        display_name: str,
        base_currency: str,
        default_currency: str,
    ) -> User:
        """Register a new user and provision their personal Spreadsheet.

        Steps:
          1. Validate currency codes.
          2. Copy template Spreadsheet via Drive API.
          3. Transfer ownership to admin account.
          4. Write user row to Master Registry.
          5. Populate the Transactions header row.
          6. Cache and return the new User.

        Args:
            telegram_id:      Telegram user ID.
            username:         Telegram @username (without @).
            display_name:     Full name from Telegram profile.
            base_currency:    ISO 4217 base currency for analytics.
            default_currency: ISO 4217 fallback when none is mentioned.

        Returns:
            Newly created User.

        Raises:
            ValueError:          On invalid currency codes.
            UserRegistryError:   On Drive / Sheets API failures.
        """
        self.validate_currency(base_currency, raise_on_invalid=True)
        self.validate_currency(default_currency, raise_on_invalid=True)

        spreadsheet_id = self._copy_template(display_name)
        self._transfer_ownership_to_admin(spreadsheet_id)

        user = User(
            telegram_id=telegram_id,
            username=username,
            display_name=display_name,
            spreadsheet_id=spreadsheet_id,
            base_currency=base_currency.upper(),
            default_currency=default_currency.upper(),
            created_at=datetime.utcnow(),
            owner=UserRole.user,
            status=UserStatus.active,
        )

        self._sheets.register_user(user)
        self._sheets.ensure_transactions_header(spreadsheet_id)
        self._cache[telegram_id] = user

        logger.info(
            "Created user %s (%s) with spreadsheet %s", telegram_id, display_name, spreadsheet_id
        )
        return user

    async def transfer_to_user(self, telegram_id: int, email: str) -> None:
        """Share the user's Spreadsheet and transfer ownership to their Google account.

        Args:
            telegram_id: Telegram user ID.
            email:       Google email address to receive ownership.

        Raises:
            UserRegistryError: If the user is not found or Drive call fails.
        """
        user = await self.get_user(telegram_id)
        if user is None:
            raise UserRegistryError(f"User {telegram_id} not found in registry")

        try:
            self._drive.permissions().create(
                fileId=user.spreadsheet_id,
                transferOwnership=True,
                body={
                    "type": "user",
                    "role": "owner",
                    "emailAddress": email,
                },
                fields="id",
            ).execute()
        except HttpError as exc:
            raise UserRegistryError(f"Drive API error transferring ownership: {exc}") from exc

        self._sheets.update_user_email(telegram_id, email)
        if telegram_id in self._cache:
            self._cache[telegram_id] = self._cache[telegram_id].model_copy(update={"email": email})
        logger.info("Transferred spreadsheet %s to %s", user.spreadsheet_id, email)

    async def update_settings(
        self, telegram_id: int, base_currency: str, default_currency: str
    ) -> User:
        """Update a user's currency settings.

        Args:
            telegram_id:      Telegram user ID.
            base_currency:    New ISO 4217 base currency.
            default_currency: New ISO 4217 default currency.

        Returns:
            Updated User object.

        Raises:
            ValueError:        On invalid currency codes.
            UserRegistryError: If the user is not found.
        """
        self.validate_currency(base_currency, raise_on_invalid=True)
        self.validate_currency(default_currency, raise_on_invalid=True)

        user = await self.get_user(telegram_id)
        if user is None:
            raise UserRegistryError(f"User {telegram_id} not found")

        self._sheets.update_user_settings(telegram_id, base_currency, default_currency)
        updated = user.model_copy(
            update={
                "base_currency": base_currency.upper(),
                "default_currency": default_currency.upper(),
            }
        )
        self._cache[telegram_id] = updated
        return updated

    # ── Currency validation ──────────────────────────────────────────────────

    @staticmethod
    def validate_currency(code: str, *, raise_on_invalid: bool = False) -> bool:
        """Return True if code is a valid ISO 4217 alphabetic currency code.

        Args:
            code:             Currency code to validate (case-insensitive).
            raise_on_invalid: If True, raises ValueError instead of returning False.
        """
        valid = (
            isinstance(code, str)
            and len(code) == 3
            and code.isalpha()
            and code.upper() in _ISO_4217_CODES
        )
        if not valid and raise_on_invalid:
            raise ValueError(
                f"'{code}' is not a valid ISO 4217 currency code. "
                f"Use a 3-letter code like USD, EUR, THB."
            )
        return valid

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _copy_template(self, display_name: str) -> str:
        """Copy the template Spreadsheet and return the new file's ID.

        Raises:
            UserRegistryError: On Drive API failure.
        """
        try:
            result = self._drive.files().copy(
                fileId=self._template_id,
                body={
                    "name": f"Expenses — {display_name}",
                    "parents": [self._folder_id],
                },
                fields="id",
            ).execute()
            return result["id"]
        except HttpError as exc:
            raise UserRegistryError(f"Failed to copy template Spreadsheet: {exc}") from exc

    def _transfer_ownership_to_admin(self, spreadsheet_id: str) -> None:
        """Grant the admin account owner permissions on a Spreadsheet.

        Raises:
            UserRegistryError: On Drive API failure.
        """
        try:
            self._drive.permissions().create(
                fileId=spreadsheet_id,
                transferOwnership=True,
                body={
                    "type": "user",
                    "role": "owner",
                    "emailAddress": self._admin_email,
                },
                fields="id",
            ).execute()
        except HttpError as exc:
            raise UserRegistryError(f"Failed to transfer ownership to admin: {exc}") from exc

    @staticmethod
    def _build_drive_service():
        """Build a Google Drive API service client using ADC."""
        creds, _ = google_auth_default(scopes=_SCOPES)
        return build("drive", "v3", credentials=creds)
