"""Tests for "💰 Amount": changing the amount of a saved expense from the chat."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from handlers.callbacks import CB_EDIT_AMOUNT, handle_callback, saved_keyboard
from handlers.text import handle_text
from models.category import UserCategory, UserSubcategory
from models.expense import ExpenseRecord, ExpenseSource
from models.trip import Trip
from tests.test_quick_expenses import (
    FakeStorage,
    _callback_update,
    _context,
    _message_update,
    _user,
)


def _record(**kwargs) -> ExpenseRecord:
    defaults = dict(
        id="rec-1",
        amount_local=100,
        local_currency="THB",
        amount_base=3.0,
        base_currency="USD",
        fx_rate=0.03,
        category="food",
        subcategory="cafe",
        description="Coffee",
        source=ExpenseSource.text,
    )
    defaults.update(kwargs)
    return ExpenseRecord(**defaults)


def _storage(**user_kwargs) -> FakeStorage:
    storage = FakeStorage(_user(**user_kwargs))
    storage.records["rec-1"] = _record()
    return storage


def _datas(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_saved_card_has_an_amount_button() -> None:
    assert f"{CB_EDIT_AMOUNT}:rec-1" in _datas(saved_keyboard("rec-1"))
    assert f"{CB_EDIT_AMOUNT}:rec-1" in _datas(saved_keyboard("rec-1", can_add_quick=False))


async def test_amount_button_asks_and_shows_the_current_amount() -> None:
    storage = _storage()
    ctx = _context(storage)
    update = _callback_update(f"{CB_EDIT_AMOUNT}:rec-1")

    await handle_callback(update, ctx)

    assert ctx.user_data["awaiting"] == "edit_amount:rec-1"
    prompt = update.callback_query.message.reply_text.call_args.args[0]
    assert "100.00 THB" in prompt


async def test_new_amount_is_saved_and_reconverted() -> None:
    storage = _storage()
    ctx = _context(storage, rate=0.03)
    ctx.user_data["awaiting"] = "edit_amount:rec-1"
    update = _message_update("150")

    await handle_text(update, ctx)

    record = storage.records["rec-1"]
    assert (record.amount_local, record.local_currency) == (150, "THB")
    assert record.amount_base == pytest.approx(4.5)
    # Everything else stays.
    assert (record.category, record.description, record.source) == ("food", "Coffee", ExpenseSource.text)
    assert "awaiting" not in ctx.user_data
    card = update.message.reply_text.call_args
    assert "150.00 THB" in card.args[0]
    assert "Amount updated" in card.args[0]
    assert f"{CB_EDIT_AMOUNT}:rec-1" in _datas(card.kwargs["reply_markup"])


async def test_new_amount_can_change_the_currency() -> None:
    storage = _storage()
    ctx = _context(storage, rate=1.0)
    ctx.user_data["awaiting"] = "edit_amount:rec-1"

    await handle_text(_message_update("12,5 usd"), ctx)

    record = storage.records["rec-1"]
    assert (record.amount_local, record.local_currency, record.fx_rate) == (12.5, "USD", 1.0)


async def test_failed_conversion_keeps_the_recorded_rate() -> None:
    storage = _storage()
    ctx = _context(storage)
    ctx.bot_data["currency"].convert = AsyncMock(side_effect=RuntimeError("FX down"))
    ctx.user_data["awaiting"] = "edit_amount:rec-1"

    await handle_text(_message_update("200"), ctx)

    record = storage.records["rec-1"]
    assert record.fx_rate == 0.03
    assert record.amount_base == pytest.approx(6.0)


@pytest.mark.parametrize("reply", ["abc", "0", "12 XYZ"])
async def test_invalid_amount_keeps_the_prompt(reply: str) -> None:
    storage = _storage()
    ctx = _context(storage)
    ctx.user_data["awaiting"] = "edit_amount:rec-1"
    update = _message_update(reply)

    await handle_text(update, ctx)

    assert storage.records["rec-1"].amount_local == 100
    assert ctx.user_data["awaiting"] == "edit_amount:rec-1"
    update.message.reply_text.assert_awaited_once()


async def test_cancel_drops_the_amount_prompt() -> None:
    storage = _storage()
    ctx = _context(storage)
    ctx.user_data["awaiting"] = "edit_amount:rec-1"

    await handle_callback(_callback_update("qe_cancel"), ctx)

    assert "awaiting" not in ctx.user_data


async def test_missing_expense_is_reported() -> None:
    storage = _storage()
    ctx = _context(storage)
    ctx.user_data["awaiting"] = "edit_amount:gone"
    update = _message_update("150")

    await handle_text(update, ctx)

    assert "Could not find" in update.message.reply_text.call_args.args[0]
    assert "awaiting" not in ctx.user_data


async def test_card_keeps_the_trip_label() -> None:
    trip = Trip(id="tripabcd", name="Georgia", start_date=date(2020, 1, 1))
    storage = _storage()
    storage.trips[trip.id] = trip
    storage.records["rec-1"] = _record(trip_id=trip.id)
    ctx = _context(storage)
    ctx.user_data["awaiting"] = "edit_amount:rec-1"
    update = _message_update("150")

    await handle_text(update, ctx)

    assert "Georgia" in update.message.reply_text.call_args.args[0]


async def test_raising_the_amount_can_trigger_a_budget_alert() -> None:
    storage = _storage(budget_alerts=True)
    storage.categories = [
        UserCategory(
            slug="food",
            label="Food & Drinks",
            subcategories=[UserSubcategory(slug="cafe", label="Cafe", budget=5.0)],
        )
    ]
    ctx = _context(storage, rate=0.03)
    ctx.user_data["awaiting"] = "edit_amount:rec-1"

    # 3.0 → 4.5 USD of a 5 USD budget: crosses 80%.
    await handle_text(_message_update("150"), ctx)

    ctx.bot.send_message.assert_awaited_once()
    assert "80%" in ctx.bot.send_message.call_args.kwargs["text"]


async def test_lowering_the_amount_sends_no_alert() -> None:
    storage = _storage(budget_alerts=True)
    storage.categories = [
        UserCategory(
            slug="food",
            label="Food & Drinks",
            subcategories=[UserSubcategory(slug="cafe", label="Cafe", budget=5.0)],
        )
    ]
    ctx = _context(storage)
    ctx.user_data["awaiting"] = "edit_amount:rec-1"

    await handle_text(_message_update("50"), ctx)

    ctx.bot.send_message.assert_not_awaited()
