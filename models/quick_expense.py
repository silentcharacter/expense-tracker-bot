"""Pydantic model for quick expenses — one-tap presets shown as chat buttons.

A quick expense is a template (category, description, amount, currency). The
bot renders each one as a reply-keyboard button; pressing it sends the button
text back as a plain message, which the bot matches against the presets and
saves without calling Gemini.
"""

import unicodedata
import uuid
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from models.category import category_emoji

QUICK_EXPENSES_LIMIT = 9
"""At most three rows of three buttons — more would cover half of the chat."""

NAME_MAX_LEN = 16
"""Keeps three buttons per row readable on a phone."""


def starts_with_symbol(text: str) -> bool:
    """True if ``text`` starts with an emoji-like symbol (Unicode category So).

    Every quick-expense button starts with an emoji, so this cheaply tells a
    button press apart from a typed expense like "кафе 100".
    """
    return bool(text) and unicodedata.category(text[0]) == "So"


def format_amount(amount: float) -> str:
    """Render an amount compactly: ``100`` rather than ``100.00``, else ``2.5``."""
    if float(amount).is_integer():
        return f"{int(amount)}"
    return f"{amount:.2f}".rstrip("0").rstrip(".")


class QuickExpense(BaseModel):
    """A one-tap expense preset."""

    # Short on purpose: travels inside Telegram callback_data (64 bytes).
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = Field(..., description="Button caption, e.g. 'Cafe'")
    emoji: str = Field(default="", description="Leading emoji; defaults to the category's")
    category: str = Field(..., description="Category slug")
    subcategory: str = Field(default="", description="Optional subcategory slug")
    description: str = Field(default="", description="Saved expense description; defaults to name")
    amount: Optional[float] = Field(
        default=None, description="Fixed amount; None means ask for it on every press"
    )
    currency: str = Field(
        default="", description="ISO 4217 code; empty means the user's default currency"
    )

    @field_validator("id")
    @classmethod
    def non_empty_id(cls, v: str) -> str:
        return (v or "").strip()[:8] or uuid.uuid4().hex[:8]

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        """Collapse whitespace and cap the length so buttons stay narrow."""
        name = " ".join((v or "").split())
        if not name:
            raise ValueError("name must not be empty")
        return name[:NAME_MAX_LEN].rstrip()

    @field_validator("category", "subcategory")
    @classmethod
    def lower_slug(cls, v: str) -> str:
        return (v or "").strip().lower()

    @field_validator("category")
    @classmethod
    def non_empty_category(cls, v: str) -> str:
        if not v:
            raise ValueError("category must not be empty")
        return v

    @field_validator("description")
    @classmethod
    def clean_description(cls, v: str) -> str:
        return " ".join((v or "").split())[:100]

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if v <= 0:
            raise ValueError("amount must be greater than 0")
        return round(float(v), 2)

    @field_validator("currency")
    @classmethod
    def upper_currency(cls, v: str) -> str:
        code = (v or "").strip().upper()
        if code and (len(code) != 3 or not code.isalpha()):
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return code

    def model_post_init(self, __context: object) -> None:
        """Fill the emoji from the category when it is missing or not a symbol.

        The button text must start with a symbol: that is how incoming messages
        are recognised as button presses (see ``starts_with_symbol``).
        """
        emoji = (self.emoji or "").strip()
        if not starts_with_symbol(emoji):
            emoji = category_emoji(self.category)
        self.emoji = emoji[:4]

    # ── Derived ──────────────────────────────────────────────────────────────

    @property
    def asks_amount(self) -> bool:
        """True when the preset has no fixed amount."""
        return self.amount is None

    @property
    def expense_description(self) -> str:
        """Description stored on the saved expense."""
        return self.description or self.name

    def effective_currency(self, default_currency: str) -> str:
        """Preset currency, or the user's default when the preset has none."""
        return self.currency or default_currency.upper()

    def button_text(self, default_currency: str) -> str:
        """Text of the chat button — also the key used to recognise a press.

        The currency code is shown only when it differs from the user's default,
        and presets without an amount end with an ellipsis ("🛒 Groceries…").
        """
        label = f"{self.emoji} {self.name}"
        if self.amount is None:
            return f"{label}…"
        text = f"{label} {format_amount(self.amount)}"
        currency = self.effective_currency(default_currency)
        if currency != default_currency.upper():
            text += f" {currency}"
        return text

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialise for Firestore and the Mini App API."""
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "category": self.category,
            "subcategory": self.subcategory,
            "description": self.description,
            "amount": self.amount,
            "currency": self.currency,
        }


def find_duplicate_button(items: list[QuickExpense], default_currency: str) -> Optional[str]:
    """Return the first button text used by more than one preset, if any."""
    seen: set[str] = set()
    for item in items:
        text = item.button_text(default_currency)
        if text in seen:
            return text
        seen.add(text)
    return None
