"""Integration tests for GeminiService.

These tests call the real Gemini API and require:
  - .env.yaml with GOOGLE_API_KEY
  - test audio fixtures in tests/fixtures/

Run:
  pytest tests/test_gemini_integration.py -m integration -v
"""

from pathlib import Path

import pytest

from models.expense import Expense
from models.category import default_user_categories

FIXTURES = Path(__file__).parent / "fixtures"


# ── Audio parsing ────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_parse_audio_returns_valid_expense(gemini_service):
    """A real voice message should be parsed into a valid Expense."""
    audio_path = FIXTURES / "expense_voice.ogg"
    if not audio_path.exists():
        pytest.skip(
            f"Place a test OGG voice file at {audio_path}. "
            "Record a Telegram voice message like '200 бат такси' and save it there."
        )

    categories = default_user_categories()
    audio_bytes = audio_path.read_bytes()
    expense = await gemini_service.parse_audio(audio_bytes, default_currency="THB", categories=categories)

    assert isinstance(expense, Expense)
    assert expense.amount > 0
    assert len(expense.currency) == 3
    assert expense.category in {c.slug for c in categories}
    assert isinstance(expense.description, str) and expense.description


# ── Text parsing ─────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_parse_text_simple(gemini_service):
    """A simple text expense should be parsed correctly."""
    categories = default_user_categories()
    expense = await gemini_service.parse_text("350 baht taxi grab", default_currency="THB", categories=categories)

    assert isinstance(expense, Expense)
    assert expense.amount == pytest.approx(350, abs=1)
    assert expense.currency == "THB"
    assert expense.category in {c.slug for c in categories}
    assert expense.description


@pytest.mark.integration
async def test_parse_text_infers_default_currency(gemini_service):
    """When no currency is mentioned, should use the provided default."""
    categories = default_user_categories()
    expense = await gemini_service.parse_text("500 groceries", default_currency="USD", categories=categories)

    assert isinstance(expense, Expense)
    assert expense.amount == pytest.approx(500, abs=1)
    assert expense.currency == "USD"


@pytest.mark.integration
async def test_parse_text_different_language(gemini_service):
    """Russian text input should be parsed correctly."""
    categories = default_user_categories()
    expense = await gemini_service.parse_text("200 рублей кофе старбакс", default_currency="RUB", categories=categories)

    assert isinstance(expense, Expense)
    assert expense.amount == pytest.approx(200, abs=1)
    assert expense.currency == "RUB"
    assert expense.category in {c.slug for c in categories}
