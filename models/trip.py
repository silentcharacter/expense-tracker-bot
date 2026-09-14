"""Pydantic model for trips — a scope tag layered over expenses.

A trip is orthogonal to categories: a meal abroad stays ``food/restaurant`` and
additionally carries ``trip_id``. That keeps category analytics intact while
letting every report be filtered down to a single journey.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Trip(BaseModel):
    """A named date range that expenses can be attributed to."""

    # Short id on purpose: trip ids travel inside Telegram callback_data, which
    # is capped at 64 bytes and already carries a full expense uuid.
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = Field(..., description="Human-readable trip name, e.g. 'Georgia, October'")
    emoji: str = Field(default="🧳", description="Emoji shown next to the trip name")
    start_date: date = Field(..., description="First day of the trip (inclusive)")
    end_date: Optional[date] = Field(
        default=None, description="Last day (inclusive); None while the trip is still running"
    )
    trip_currency: str = Field(
        default="", description="Optional ISO 4217 code of the destination currency"
    )
    budget: Optional[float] = Field(
        default=None, description="Optional trip budget in the user's base currency"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("name")
    @classmethod
    def non_empty_name(cls, v: str) -> str:
        """Trips are picked from lists by name, so an empty one is not useful."""
        name = v.strip()
        if not name:
            raise ValueError("name must not be empty")
        return name[:60]

    @field_validator("emoji")
    @classmethod
    def default_emoji(cls, v: str) -> str:
        return (v or "").strip()[:4] or "🧳"

    @field_validator("trip_currency")
    @classmethod
    def upper_currency(cls, v: str) -> str:
        return (v or "").strip().upper()

    @field_validator("budget")
    @classmethod
    def positive_budget(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if v <= 0:
            return None
        return float(v)

    @model_validator(mode="after")
    def end_after_start(self) -> "Trip":
        """Reject inverted ranges — they would silently match zero expenses."""
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self

    # ── Derived state ────────────────────────────────────────────────────────

    @property
    def is_open(self) -> bool:
        """True while the trip has no end date (still running)."""
        return self.end_date is None

    def covers(self, day: date) -> bool:
        """True if ``day`` falls inside the trip's date range."""
        if day < self.start_date:
            return False
        if self.end_date is not None and day > self.end_date:
            return False
        return True

    def is_over(self, today: Optional[date] = None) -> bool:
        """True once the trip's end date is in the past."""
        if self.end_date is None:
            return False
        return self.end_date < (today or date.today())

    def day_count(self, today: Optional[date] = None) -> int:
        """Number of days elapsed so far (open trips count up to today)."""
        today = today or date.today()
        last = self.end_date or today
        if last < self.start_date:
            return 0
        return (last - self.start_date).days + 1

    def total_days(self) -> Optional[int]:
        """Planned length in days, or None while the trip is open-ended."""
        if self.end_date is None:
            return None
        return (self.end_date - self.start_date).days + 1

    def label(self) -> str:
        """Emoji + name, as shown in bot messages and pickers."""
        return f"{self.emoji} {self.name}".strip()

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_firestore_dict(self) -> dict:
        """Serialise to a Firestore-compatible dict.

        Dates are stored as ISO strings rather than timestamps: Firestore has no
        date-only type, and strings keep range comparisons readable in the console.
        """
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else "",
            "trip_currency": self.trip_currency,
            "budget": self.budget,
            "created_at": self.created_at,
        }

    @classmethod
    def from_firestore_dict(cls, data: dict) -> "Trip":
        """Deserialise from a Firestore document dict."""
        d = dict(data)
        if not d.get("end_date"):
            d["end_date"] = None
        ts = d.get("created_at")
        if ts is not None and hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            d["created_at"] = ts.replace(tzinfo=None)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Serialise for the Mini App REST API."""
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "trip_currency": self.trip_currency,
            "budget": self.budget,
            "is_open": self.is_open,
            "total_days": self.total_days(),
            "created_at": self.created_at.isoformat(),
        }
