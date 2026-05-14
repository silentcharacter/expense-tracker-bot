"""Unit tests for handlers/budget_alerts.py.

All external services are replaced with MagicMock / AsyncMock so tests run
offline and instantaneously.
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handlers.budget_alerts import check_and_send_budget_alert
from models.category import UserCategory, UserSubcategory
from models.expense import ExpenseRecord, ExpenseSource, User, UserRole, UserStatus

# ── Helpers ───────────────────────────────────────────────────────────────────

TG_ID = 99
SPREADSHEET_ID = "sheet-xyz"


def _make_user(**kwargs) -> User:
    defaults = dict(
        telegram_id=TG_ID,
        display_name="Bob",
        spreadsheet_id=SPREADSHEET_ID,
        base_currency="USD",
        default_currency="USD",
        role=UserRole.user,
        status=UserStatus.active,
        created_at=datetime(2026, 1, 1),
        budget_alerts=True,
    )
    defaults.update(kwargs)
    return User(**defaults)


def _make_record(**kwargs) -> ExpenseRecord:
    defaults = dict(
        amount_local=100.0,
        local_currency="USD",
        amount_base=100.0,
        base_currency="USD",
        fx_rate=1.0,
        category="food",
        subcategory="restaurant",
        description="lunch",
        source=ExpenseSource.text,
        timestamp=datetime(2026, 4, 15, 12, 0, 0),
    )
    defaults.update(kwargs)
    return ExpenseRecord(**defaults)


def _make_tx(category: str, amount_base: float) -> ExpenseRecord:
    """Shorthand for a transaction in the given category."""
    return _make_record(category=category, amount_base=amount_base)


def _make_sheets(transactions: list, categories: list) -> MagicMock:
    m = MagicMock()
    m.get_transactions.return_value = transactions
    m.get_categories.return_value = categories
    return m


def _food_cat(budget: float | None = 1000.0, subcats: list | None = None) -> UserCategory:
    if subcats is None and budget is not None:
        subcats = [UserSubcategory(slug="restaurant", label="Restaurant", budget=budget)]
    return UserCategory(
        slug="food",
        label="Food & Drinks",
        budget=budget,
        subcategories=subcats or [],
    )


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


# ── Early-exit guards ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_alert_when_budget_alerts_disabled():
    user = _make_user(budget_alerts=False)
    bot = _make_bot()
    sheets = _make_sheets([], [_food_cat()])

    await check_and_send_budget_alert(bot, user, _make_record(), sheets)

    bot.send_message.assert_not_called()
    sheets.get_transactions.assert_not_called()


@pytest.mark.asyncio
async def test_no_alert_when_amount_base_is_zero():
    user = _make_user()
    bot = _make_bot()
    sheets = _make_sheets([], [_food_cat()])

    await check_and_send_budget_alert(bot, user, _make_record(amount_base=0.0), sheets)

    bot.send_message.assert_not_called()
    sheets.get_transactions.assert_not_called()


@pytest.mark.asyncio
async def test_no_alert_when_category_not_found():
    user = _make_user()
    bot = _make_bot()
    # Categories list has no "food" entry
    sheets = _make_sheets(
        [_make_tx("food", 900.0)],
        [UserCategory(slug="transport", label="Transport", budget=500.0)],
    )

    await check_and_send_budget_alert(bot, user, _make_record(amount_base=100.0), sheets)

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_no_alert_when_no_budget_set():
    user = _make_user()
    bot = _make_bot()
    sheets = _make_sheets([_make_tx("food", 900.0)], [_food_cat(budget=None)])

    await check_and_send_budget_alert(bot, user, _make_record(amount_base=100.0), sheets)

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_no_alert_when_budget_is_zero():
    user = _make_user()
    bot = _make_bot()
    sheets = _make_sheets([_make_tx("food", 900.0)], [_food_cat(budget=0.0)])

    await check_and_send_budget_alert(bot, user, _make_record(amount_base=100.0), sheets)

    bot.send_message.assert_not_called()


# ── Below threshold ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_alert_when_below_80_percent():
    """700/1000 = 70% before, 770/1000 = 77% after → no threshold crossed."""
    user = _make_user()
    bot = _make_bot()
    existing = [_make_tx("food", 700.0)]
    record = _make_record(amount_base=70.0)
    sheets = _make_sheets(existing + [record], [_food_cat(budget=1000.0)])

    await check_and_send_budget_alert(bot, user, record, sheets)

    bot.send_message.assert_not_called()


# ── 80% threshold ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alert_sent_when_crossing_80_percent():
    """700/1000 = 70% before, 800/1000 = 80% after → ⚠️ alert."""
    user = _make_user()
    bot = _make_bot()
    existing = [_make_tx("food", 700.0)]
    record = _make_record(amount_base=100.0)
    sheets = _make_sheets(existing + [record], [_food_cat(budget=1000.0)])

    await check_and_send_budget_alert(bot, user, record, sheets)

    bot.send_message.assert_called_once()
    call_kwargs = bot.send_message.call_args
    assert call_kwargs.kwargs["chat_id"] == TG_ID
    assert call_kwargs.kwargs["parse_mode"] == "Markdown"
    text = call_kwargs.kwargs["text"]
    assert "⚠️" in text
    assert "Food & Drinks" in text
    assert "800" in text
    assert "1,000" in text
    assert "USD" in text


@pytest.mark.asyncio
async def test_no_alert_when_already_above_80_before_expense():
    """850/1000 = 85% before, 950/1000 = 95% after → already over 80%, no new crossing."""
    user = _make_user()
    bot = _make_bot()
    existing = [_make_tx("food", 850.0)]
    record = _make_record(amount_base=100.0)
    sheets = _make_sheets(existing + [record], [_food_cat(budget=1000.0)])

    await check_and_send_budget_alert(bot, user, record, sheets)

    bot.send_message.assert_not_called()


# ── 100% threshold ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alert_sent_when_crossing_100_percent():
    """900/1000 = 90% before, 1000/1000 = 100% after → 🚨 alert."""
    user = _make_user()
    bot = _make_bot()
    existing = [_make_tx("food", 900.0)]
    record = _make_record(amount_base=100.0)
    sheets = _make_sheets(existing + [record], [_food_cat(budget=1000.0)])

    await check_and_send_budget_alert(bot, user, record, sheets)

    bot.send_message.assert_called_once()
    text = bot.send_message.call_args.kwargs["text"]
    assert "🚨" in text


@pytest.mark.asyncio
async def test_no_alert_when_already_exceeded_before_expense():
    """1050/1000 before, 1150/1000 after → already over 100%, no new crossing."""
    user = _make_user()
    bot = _make_bot()
    existing = [_make_tx("food", 1050.0)]
    record = _make_record(amount_base=100.0)
    sheets = _make_sheets(existing + [record], [_food_cat(budget=1000.0)])

    await check_and_send_budget_alert(bot, user, record, sheets)

    bot.send_message.assert_not_called()


# ── Both thresholds crossed in one transaction ────────────────────────────────


@pytest.mark.asyncio
async def test_both_thresholds_crossed_in_one_expense():
    """100/1000 = 10% before, 1050/1000 = 105% after → both ⚠️ and 🚨."""
    user = _make_user()
    bot = _make_bot()
    existing = [_make_tx("food", 100.0)]
    record = _make_record(amount_base=950.0)
    sheets = _make_sheets(existing + [record], [_food_cat(budget=1000.0)])

    await check_and_send_budget_alert(bot, user, record, sheets)

    assert bot.send_message.call_count == 2
    texts = [call.kwargs["text"] for call in bot.send_message.call_args_list]
    assert any("⚠️" in t for t in texts)
    assert any("🚨" in t for t in texts)


# ── Category budget derived from subcategories ────────────────────────────────


@pytest.mark.asyncio
async def test_effective_budget_from_subcategories():
    """Sum subcategory budgets (400+600=1000)."""
    user = _make_user()
    bot = _make_bot()
    subcats = [
        UserSubcategory(slug="restaurant", label="Restaurant", budget=400.0),
        UserSubcategory(slug="cafe", label="Cafe", budget=600.0),
    ]
    cat = _food_cat(budget=None, subcats=subcats)
    existing = [_make_tx("food", 700.0)]
    record = _make_record(amount_base=100.0)
    sheets = _make_sheets(existing + [record], [cat])

    await check_and_send_budget_alert(bot, user, record, sheets)

    bot.send_message.assert_called_once()
    text = bot.send_message.call_args.kwargs["text"]
    assert "⚠️" in text


@pytest.mark.asyncio
async def test_category_budget_field_is_ignored():
    """A stale category.budget must not override the subcategory budget sum."""
    user = _make_user()
    bot = _make_bot()
    subcats = [
        UserSubcategory(slug="restaurant", label="Restaurant", budget=400.0),
        UserSubcategory(slug="cafe", label="Cafe", budget=600.0),
    ]
    cat = _food_cat(budget=2000.0, subcats=subcats)
    existing = [_make_tx("food", 700.0)]
    record = _make_record(amount_base=100.0)
    sheets = _make_sheets(existing + [record], [cat])

    await check_and_send_budget_alert(bot, user, record, sheets)

    bot.send_message.assert_called_once()
    text = bot.send_message.call_args.kwargs["text"]
    assert "⚠️" in text
    assert "1,000" in text


@pytest.mark.asyncio
async def test_no_alert_when_subcategory_budgets_sum_to_zero():
    """All subcategory budgets are None → effective budget 0 → no alert."""
    user = _make_user()
    bot = _make_bot()
    subcats = [
        UserSubcategory(slug="restaurant", label="Restaurant", budget=None),
        UserSubcategory(slug="cafe", label="Cafe", budget=None),
    ]
    cat = _food_cat(budget=None, subcats=subcats)
    existing = [_make_tx("food", 900.0)]
    record = _make_record(amount_base=200.0)
    sheets = _make_sheets(existing + [record], [cat])

    await check_and_send_budget_alert(bot, user, record, sheets)

    bot.send_message.assert_not_called()


# ── Only the affected category is checked ────────────────────────────────────


@pytest.mark.asyncio
async def test_only_affected_category_spending_counted():
    """Transactions from other categories are ignored in the threshold check."""
    user = _make_user()
    bot = _make_bot()
    # "transport" spending is high but shouldn't affect "food" budget check
    existing = [
        _make_tx("food", 700.0),
        _make_tx("transport", 9000.0),
    ]
    record = _make_record(category="food", amount_base=100.0)
    sheets = _make_sheets(existing + [record], [_food_cat(budget=1000.0)])

    await check_and_send_budget_alert(bot, user, record, sheets)

    bot.send_message.assert_called_once()
    text = bot.send_message.call_args.kwargs["text"]
    assert "⚠️" in text


# ── Error resilience ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exception_in_sheets_does_not_propagate():
    """If sheets.get_transactions raises, the function returns silently."""
    user = _make_user()
    bot = _make_bot()
    sheets = MagicMock()
    sheets.get_transactions.side_effect = RuntimeError("network error")

    # Should not raise
    await check_and_send_budget_alert(bot, user, _make_record(), sheets)

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_exception_in_bot_send_does_not_propagate():
    """If bot.send_message raises, the function swallows the error."""
    user = _make_user()
    bot = _make_bot()
    bot.send_message.side_effect = RuntimeError("Telegram API error")
    existing = [_make_tx("food", 700.0)]
    record = _make_record(amount_base=100.0)
    sheets = _make_sheets(existing + [record], [_food_cat(budget=1000.0)])

    # Should not raise
    await check_and_send_budget_alert(bot, user, record, sheets)


# ── sheets.get_transactions called with correct month range ───────────────────


@pytest.mark.asyncio
async def test_get_transactions_called_with_current_month_range():
    """Verify that since=month_start and until=today are passed correctly."""
    from datetime import date

    user = _make_user()
    bot = _make_bot()
    record = _make_record(amount_base=100.0)
    sheets = _make_sheets([record], [_food_cat(budget=1000.0)])

    fixed_today = date(2026, 4, 15)
    with patch("handlers.budget_alerts.date") as mock_date:
        mock_date.today.return_value = fixed_today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        await check_and_send_budget_alert(bot, user, record, sheets)

    sheets.get_transactions.assert_called_once_with(
        SPREADSHEET_ID,
        since=date(2026, 4, 1),
        until=fixed_today,
    )
