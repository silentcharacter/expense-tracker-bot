"""User registration, Spreadsheet provisioning, and ISO 4217 validation."""

import logging
import os
from datetime import datetime
from typing import Optional

from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from models.expense import User, UserRole, UserStatus
from services.sheets import SheetsService

logger = logging.getLogger(__name__)

_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
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

    Drive operations (copy template, transfer ownership) use the admin's
    OAuth2 credentials so that files are created under the admin's Drive
    quota — Service Accounts on consumer GCP projects have zero storage.
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
          2. Copy template Spreadsheet via Drive API (admin OAuth2).
          3. Share new Spreadsheet with SA for gspread access.
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
        self._share_with_service_account(spreadsheet_id)

        user = User(
            telegram_id=telegram_id,
            username=username,
            display_name=display_name,
            spreadsheet_id=spreadsheet_id,
            base_currency=base_currency.upper(),
            default_currency=default_currency.upper(),
            created_at=datetime.utcnow(),
            role=UserRole.user,
            status=UserStatus.active,
        )

        self._sheets.register_user(user)
        self._sheets.ensure_transactions_header(spreadsheet_id)
        self._sheets.ensure_categories_sheet(spreadsheet_id)
        self._cache[telegram_id] = user

        logger.info(
            "Created user %s (%s) with spreadsheet %s", telegram_id, display_name, spreadsheet_id
        )
        return user

    async def transfer_to_user(self, telegram_id: int, email: str) -> None:
        """Share the user's Spreadsheet with their Google account as editor.

        On consumer (non-Workspace) accounts, transferOwnership requires email
        consent from the recipient, which the API cannot handle. Instead we
        grant writer access so the user can view and edit their spreadsheet.

        Args:
            telegram_id: Telegram user ID.
            email:       Google email address to receive access.

        Raises:
            UserRegistryError: If the user is not found or Drive call fails.
        """
        user = await self.get_user(telegram_id)
        if user is None:
            raise UserRegistryError(f"User {telegram_id} not found in registry")

        try:
            self._drive.permissions().create(
                fileId=user.spreadsheet_id,
                body={
                    "type": "user",
                    "role": "writer",
                    "emailAddress": email,
                },
                sendNotificationEmail=True,
                fields="id",
            ).execute()
        except HttpError as exc:
            raise UserRegistryError(f"Drive API error sharing spreadsheet: {exc}") from exc

        self._sheets.update_user_email(telegram_id, email)
        if telegram_id in self._cache:
            self._cache[telegram_id] = self._cache[telegram_id].model_copy(update={"email": email})
        logger.info("Shared spreadsheet %s with %s", user.spreadsheet_id, email)

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

    def _share_with_service_account(self, spreadsheet_id: str) -> None:
        """Grant the SA editor access so gspread can read/write the new Spreadsheet."""
        sa_email = os.environ.get("SA_EMAIL")
        if not sa_email:
            return
        try:
            self._drive.permissions().create(
                fileId=spreadsheet_id,
                body={
                    "type": "user",
                    "role": "writer",
                    "emailAddress": sa_email,
                },
                sendNotificationEmail=False,
                fields="id",
            ).execute()
        except HttpError as exc:
            raise UserRegistryError(
                f"Failed to share spreadsheet with service account: {exc}"
            ) from exc

    @staticmethod
    def _build_drive_service():
        """Build a Google Drive API client using the admin's OAuth2 refresh token.

        SA on consumer GCP projects has zero Drive storage quota, so we use
        the admin's personal Google account for all file-creation operations.
        """
        creds = OAuthCredentials(
            token=None,
            refresh_token=os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"],
            client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
            token_uri="https://oauth2.googleapis.com/token",
            scopes=_DRIVE_SCOPES,
        )
        return build("drive", "v3", credentials=creds)
