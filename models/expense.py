"""Pydantic models for expenses, records, and users."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ExpenseSource(str, Enum):
    """Source of an expense entry."""

    voice = "voice"
    text = "text"
    photo = "photo"


class UserRole(str, Enum):
    """Role of a user in the system."""

    user = "user"
    admin = "admin"


class UserStatus(str, Enum):
    """Account status of a user."""

    active = "active"
    suspended = "suspended"


class Expense(BaseModel):
    """Parsed expense from Gemini (audio or text input).

    This is the schema returned by Gemini as structured JSON.
    """

    amount: float = Field(..., gt=0, description="Expense amount")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")
    category: str = Field(..., description="Expense category slug")
    subcategory: str = Field(default="", description="Optional subcategory slug")
    description: str = Field(..., description="Short description (2-5 words)")

    @field_validator("currency")
    @classmethod
    def upper_currency(cls, v: str) -> str:
        """Normalise currency codes to uppercase."""
        return v.upper()

    @field_validator("category")
    @classmethod
    def lower_category(cls, v: str) -> str:
        """Normalise category to lowercase."""
        return v.lower()

    @field_validator("subcategory")
    @classmethod
    def lower_subcategory(cls, v: str) -> str:
        """Normalise subcategory to lowercase."""
        return v.lower()


class ExpenseRecord(BaseModel):
    """Full expense record as stored in the Transactions sheet."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    amount_local: float = Field(..., description="Amount in original currency")
    local_currency: str = Field(..., description="ISO 4217 original currency")
    amount_base: float = Field(..., description="Amount converted to user's base currency")
    fx_rate: float = Field(..., description="Exchange rate local → base")
    category: str
    subcategory: str = ""
    description: str
    source: ExpenseSource
    raw_input: str = Field(default="", description="Original voice transcript or text")

    def to_sheet_row(self) -> list:
        """Serialise record to a flat list for Google Sheets append."""
        return [
            self.id,
            self.timestamp.isoformat(),
            self.amount_local,
            self.local_currency,
            self.amount_base,
            self.fx_rate,
            self.category,
            self.subcategory,
            self.description,
            self.source.value,
            self.raw_input,
        ]

    @classmethod
    def sheet_headers(cls) -> list[str]:
        """Column headers matching to_sheet_row() order."""
        return [
            "id",
            "timestamp",
            "amount_local",
            "local_currency",
            "amount_base",
            "fx_rate",
            "category",
            "subcategory",
            "description",
            "source",
            "raw_input",
        ]


class User(BaseModel):
    """User record from the Master Registry sheet."""

    telegram_id: int
    username: str = Field(default="", description="Telegram @username without @")
    display_name: str = Field(..., description="Full name from Telegram profile")
    email: str = Field(default="", description="Google email for Sheets ownership")
    spreadsheet_id: str = Field(..., description="Personal Spreadsheet ID")
    owner: UserRole = UserRole.user
    base_currency: str = Field(..., description="Base currency for analytics and budgets")
    default_currency: str = Field(..., description="Fallback currency when none is mentioned")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: UserStatus = UserStatus.active

    @field_validator("base_currency", "default_currency")
    @classmethod
    def upper_currency(cls, v: str) -> str:
        return v.upper()

    def to_registry_row(self) -> list:
        """Serialise to a flat list for the Master Registry sheet."""
        return [
            self.telegram_id,
            self.username,
            self.display_name,
            self.email,
            self.spreadsheet_id,
            self.owner.value,
            self.base_currency,
            self.default_currency,
            self.created_at.isoformat(),
            self.status.value,
        ]

    @classmethod
    def registry_headers(cls) -> list[str]:
        """Column headers matching to_registry_row() order."""
        return [
            "telegram_id",
            "username",
            "display_name",
            "email",
            "spreadsheet_id",
            "owner",
            "base_currency",
            "default_currency",
            "created_at",
            "status",
        ]


class UserSettings(BaseModel):
    """Mutable per-user settings (subset of User)."""

    base_currency: str
    default_currency: str

    @field_validator("base_currency", "default_currency")
    @classmethod
    def upper_currency(cls, v: str) -> str:
        return v.upper()
