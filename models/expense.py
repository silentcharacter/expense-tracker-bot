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

    amount: float = Field(..., description="Expense amount")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")
    category: str = Field(..., description="Expense category slug")
    subcategory: str = Field(default="", description="Optional subcategory slug")
    description: str = Field(..., description="Short description (2-5 words)")

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v: float) -> float:
        """Ensure amount is positive."""
        if v <= 0:
            raise ValueError("amount must be greater than 0")
        return v

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
    base_currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 user's base currency")
    fx_rate: float = Field(..., description="Exchange rate local → base")
    category: str
    subcategory: str = ""
    description: str
    source: ExpenseSource
    raw_input: str = Field(default="", description="Original voice transcript or text")
    recurring: bool = Field(default=False, description="True if materialised by the recurring cron job")
    recurring_template_id: str = Field(default="", description="Source recurring template id (for cron idempotency)")

    @field_validator("recurring", mode="before")
    @classmethod
    def coerce_recurring(cls, v: object) -> bool:
        """Accept 'TRUE'/'FALSE' strings from Sheets, native bools, and empty cells."""
        if isinstance(v, bool):
            return v
        if v is None or v == "":
            return False
        if isinstance(v, str):
            return v.strip().upper() == "TRUE"
        return bool(v)

    def to_firestore_dict(self) -> dict:
        """Serialise record to a Firestore-compatible dict."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "amount_local": self.amount_local,
            "local_currency": self.local_currency,
            "amount_base": self.amount_base,
            "base_currency": self.base_currency,
            "fx_rate": self.fx_rate,
            "category": self.category,
            "subcategory": self.subcategory,
            "description": self.description,
            "source": self.source.value,
            "raw_input": self.raw_input,
            "recurring": self.recurring,
            "recurring_template_id": self.recurring_template_id,
        }

    @classmethod
    def from_firestore_dict(cls, data: dict) -> "ExpenseRecord":
        """Deserialise from a Firestore document dict."""
        d = dict(data)
        ts = d.get("timestamp")
        if ts is not None and hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            d["timestamp"] = ts.replace(tzinfo=None)
        return cls(**d)

    def to_sheet_row(self) -> list:
        """Serialise record to a flat list for Google Sheets append."""
        return [
            self.id,
            self.timestamp.isoformat(),
            self.amount_local,
            self.local_currency,
            self.amount_base,
            self.base_currency,
            self.fx_rate,
            self.category,
            self.subcategory,
            self.description,
            self.source.value,
            self.raw_input,
            "TRUE" if self.recurring else "FALSE",
            self.recurring_template_id,
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
            "base_currency",
            "fx_rate",
            "category",
            "subcategory",
            "description",
            "source",
            "raw_input",
            "recurring",
            "recurring_template_id",
        ]

    @classmethod
    def required_sheet_headers(cls) -> list[str]:
        """Subset of headers that must exist in every transactions sheet (original 12 columns).

        Used for backward-compatible reads of spreadsheets created before the
        recurring columns were introduced.
        """
        return [
            "id",
            "timestamp",
            "amount_local",
            "local_currency",
            "amount_base",
            "base_currency",
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
    spreadsheet_id: str = Field(default="", description="Personal Spreadsheet ID, or str(telegram_id) in Firestore mode")
    role: UserRole = UserRole.user
    base_currency: str = Field(..., description="Base currency for analytics and budgets")
    default_currency: str = Field(..., description="Fallback currency when none is mentioned")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: UserStatus = UserStatus.active
    budget_alerts: bool = Field(default=True, description="Notify when budget reaches 80%")
    weekly_summary: bool = Field(default=True, description="Send weekly summary every Monday")
    insights: bool = Field(default=True, description="Send spending pattern tips")

    @field_validator("base_currency", "default_currency")
    @classmethod
    def upper_currency(cls, v: str) -> str:
        return v.upper()

    @field_validator("budget_alerts", "weekly_summary", "insights", mode="before")
    @classmethod
    def coerce_bool(cls, v: object) -> bool:
        """Accept 'TRUE'/'FALSE' strings from Sheets as well as native bools."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.upper() == "TRUE"
        return bool(v)

    def to_firestore_dict(self) -> dict:
        """Serialise user to a Firestore-compatible dict."""
        return {
            "telegram_id": self.telegram_id,
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
            "spreadsheet_id": self.spreadsheet_id,
            "role": self.role.value,
            "base_currency": self.base_currency,
            "default_currency": self.default_currency,
            "created_at": self.created_at,
            "status": self.status.value,
            "budget_alerts": self.budget_alerts,
            "weekly_summary": self.weekly_summary,
            "insights": self.insights,
        }

    @classmethod
    def from_firestore_dict(cls, data: dict) -> "User":
        """Deserialise from a Firestore document dict."""
        d = dict(data)
        ts = d.get("created_at")
        if ts is not None and hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            d["created_at"] = ts.replace(tzinfo=None)
        return cls(**d)

    def to_registry_row(self) -> list:
        """Serialise to a flat list for the Master Registry sheet."""
        return [
            self.telegram_id,
            self.username,
            self.display_name,
            self.email,
            self.spreadsheet_id,
            self.role.value,
            self.base_currency,
            self.default_currency,
            self.created_at.isoformat(),
            self.status.value,
            str(self.budget_alerts).upper(),
            str(self.weekly_summary).upper(),
            str(self.insights).upper(),
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
            "role",
            "base_currency",
            "default_currency",
            "created_at",
            "status",
            "budget_alerts",
            "weekly_summary",
            "insights",
        ]

    @classmethod
    def required_registry_headers(cls) -> list[str]:
        """Subset of headers that must exist in every registry row (original 10 columns)."""
        return [
            "telegram_id",
            "username",
            "display_name",
            "email",
            "spreadsheet_id",
            "role",
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
