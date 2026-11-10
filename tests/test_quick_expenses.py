"""Tests for quick expenses: model, button matching, bot flow and /api/quick-expenses."""

from datetime import date, datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

from handlers import quick
from handlers.callbacks import CB_QUICK_ADD, saved_keyboard
from models.category import UserCategory, UserSubcategory
from models.expense import ExpenseRecord, ExpenseSource, User, UserRole, UserStatus
from models.quick_expense import QUICK_EXPENSES_LIMIT, QuickExpense, starts_with_symbol
from models.trip import Trip
from services.user_registry import UserRegistry
from tests.test_api import _call

TG_ID = 42


# ── Fakes ────────────────────────────────────────────────────────────────────


class FakeStorage:
    """In-memory storage covering what the quick-expense flow touches."""

    def __init__(self, user: User, categories: Optional[list[UserCategory]] = None) -> None:
        self.user = user
        self.records: dict[str, ExpenseRecord] = {}
        self.trips: dict[str, Trip] = {}
        self.categories = categories or [
            UserCategory(
                slug="food",
                label="Food & Drinks",
                subcategories=[UserSubcategory(slug="cafe", label="Cafe")],
            ),
            UserCategory(slug="transport", label="Transport", subcategories=[]),
        ]
        self.find_calls = 0

    # users
    def find_user(self, telegram_id: int) -> Optional[User]:
        self.find_calls += 1
        return self.user if telegram_id == self.user.telegram_id else None

    def get_quick_expenses(self, telegram_id: int) -> list[QuickExpense]:
        return list(self.user.quick_expenses)

    def set_quick_expenses(self, telegram_id: int, items: list[QuickExpense]) -> bool:
        self.user = self.user.model_copy(update={"quick_expenses": list(items)})
        return True

    def set_quick_keyboard_hidden(self, telegram_id: int, hidden: bool) -> bool:
        self.user = self.user.model_copy(update={"quick_keyboard_hidden": hidden})
        return True

    # transactions
    def append_transaction(self, user_id: str, record: ExpenseRecord) -> None:
        self.records[record.id] = record

    def get_transaction(self, user_id: str, expense_id: str) -> Optional[ExpenseRecord]:
        return self.records.get(expense_id)

    def get_transactions(self, user_id, since=None, until=None, limit=None, trip_id=None):
        return list(self.records.values())

    def get_categories(self, user_id: str) -> list[UserCategory]:
        return self.categories

    # trips
    def get_trip(self, user_id: str, trip_id: str) -> Optional[Trip]:
        return self.trips.get(trip_id)

    def set_active_trip(self, telegram_id: int, trip_id: str) -> bool:
        self.user = self.user.model_copy(update={"active_trip_id": trip_id})
        return True


def _user(**kwargs) -> User:
    defaults = dict(
        telegram_id=TG_ID,
        display_name="Alice",
        spreadsheet_id=str(TG_ID),
        base_currency="USD",
        default_currency="THB",
        role=UserRole.user,
        status=UserStatus.active,
        created_at=datetime(2026, 1, 1),
        budget_alerts=False,
    )
    defaults.update(kwargs)
    return User(**defaults)


def _cafe(**kwargs) -> QuickExpense:
    defaults = dict(id="cafe0001", name="Cafe", emoji="☕", category="food", subcategory="cafe", amount=100)
    defaults.update(kwargs)
    return QuickExpense(**defaults)


def _groceries(**kwargs) -> QuickExpense:
    defaults = dict(id="groc0001", name="Groceries", emoji="🛒", category="food")
    defaults.update(kwargs)
    return QuickExpense(**defaults)


def _context(storage: FakeStorage, rate: float = 0.03) -> MagicMock:
    """PTB-like context with a real UserRegistry on top of the fake storage."""
    currency = MagicMock()
    currency.convert = AsyncMock(side_effect=lambda amount, src, dst: (round(amount * rate, 4), rate))
    ctx = MagicMock()
    ctx.bot_data = {
        "registry": UserRegistry(sheets_service=storage),
        "sheets": storage,
        "currency": currency,
    }
    ctx.user_data = {}
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def _message_update(text: str = "") -> MagicMock:
    update = MagicMock()
    update.effective_user.id = TG_ID
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _callback_update(data: str) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = TG_ID
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()
    update.callback_query.message.reply_text = AsyncMock()
    return update


@pytest.fixture(autouse=True)
def _firestore_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "firestore")


# ── Model ────────────────────────────────────────────────────────────────────


def test_button_text_hides_default_currency_and_shows_others() -> None:
    assert _cafe().button_text("THB") == "☕ Cafe 100"
    assert _cafe(currency="THB").button_text("THB") == "☕ Cafe 100"
    assert _cafe(currency="usd", amount=2.5).button_text("THB") == "☕ Cafe 2.5 USD"


def test_button_text_without_amount_ends_with_ellipsis() -> None:
    assert _groceries().button_text("THB") == "🛒 Groceries…"
    assert _groceries().asks_amount


def test_missing_or_textual_emoji_falls_back_to_category_emoji() -> None:
    assert QuickExpense(name="Taxi", category="transport", emoji="").emoji == "🚗"
    assert QuickExpense(name="Taxi", category="transport", emoji="T").emoji == "🚗"
    assert QuickExpense(name="Thing", category="my_custom").emoji == "⚡"


def test_name_is_trimmed_and_capped() -> None:
    q = QuickExpense(name="  Very   long name for a button  ", category="food")
    assert q.name == "Very long name f"
    assert len(q.name) <= 16


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "   "},
        {"amount": 0},
        {"amount": -5},
        {"currency": "DOLLARS"},
        {"category": ""},
    ],
)
def test_invalid_presets_are_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        _cafe(**kwargs)


def test_description_defaults_to_name() -> None:
    assert _cafe().expense_description == "Cafe"
    assert _cafe(description="Flat white").expense_description == "Flat white"


def test_user_round_trips_quick_expenses_and_skips_malformed_ones() -> None:
    user = _user(quick_expenses=[_cafe(), _groceries()], quick_keyboard_hidden=True)
    data = user.to_firestore_dict()
    data["quick_expenses"].append({"name": "", "category": "food"})  # corrupted entry

    restored = User.from_firestore_dict(data)

    assert [q.id for q in restored.quick_expenses] == ["cafe0001", "groc0001"]
    assert restored.quick_keyboard_hidden is True


def test_users_without_the_fields_still_load() -> None:
    data = _user().to_firestore_dict()
    del data["quick_expenses"], data["quick_keyboard_hidden"]
    restored = User.from_firestore_dict(data)
    assert restored.quick_expenses == []
    assert restored.quick_keyboard_hidden is False


def test_starts_with_symbol() -> None:
    assert starts_with_symbol("☕ Cafe 100")
    assert starts_with_symbol("🛍️ Shopping…")
    assert not starts_with_symbol("кафе 100")
    assert not starts_with_symbol("100 cafe")
    assert not starts_with_symbol("")


# ── Matching, keyboard, amount parsing ───────────────────────────────────────


def test_match_requires_exact_button_text() -> None:
    user = _user(quick_expenses=[_cafe(), _groceries()])
    assert quick.match_quick_button(user, "☕ Cafe 100").id == "cafe0001"
    assert quick.match_quick_button(user, "  🛒 Groceries…  ").id == "groc0001"
    assert quick.match_quick_button(user, "кафе 100") is None
    assert quick.match_quick_button(user, "☕ Cafe 150") is None


def test_reply_keyboard_has_three_buttons_per_row() -> None:
    items = [_cafe(id=f"id{i:06d}", name=f"Item {i}") for i in range(7)]
    markup = quick.quick_reply_markup(_user(quick_expenses=items))

    assert isinstance(markup, ReplyKeyboardMarkup)
    assert [len(row) for row in markup.keyboard] == [3, 3, 1]
    assert markup.keyboard[0][0].text == "☕ Item 0 100"
    assert markup.is_persistent and markup.resize_keyboard


def test_reply_keyboard_is_removed_when_empty_or_hidden() -> None:
    assert isinstance(quick.quick_reply_markup(_user()), ReplyKeyboardRemove)
    hidden = _user(quick_expenses=[_cafe()], quick_keyboard_hidden=True)
    assert isinstance(quick.quick_reply_markup(hidden), ReplyKeyboardRemove)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("450", (450.0, None)),
        ("450.5", (450.5, None)),
        ("450,5", (450.5, None)),
        ("1 500", (1500.0, None)),
        ("12 usd", (12.0, "USD")),
        ("12EUR", (12.0, "EUR")),
        ("abc", None),
        ("0", None),
        ("12 coffees", None),
        ("", None),
    ],
)
def test_parse_amount(text: str, expected: Optional[tuple]) -> None:
    assert quick.parse_amount(text) == expected


def test_quick_callback_data_fits_telegram_limit() -> None:
    record_id = "12345678-1234-1234-1234-123456789012"
    markup = saved_keyboard(record_id)
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"{CB_QUICK_ADD}:{record_id}" in datas
    assert all(len(d.encode()) <= 64 for d in datas)


def test_saved_keyboard_can_omit_the_quick_button() -> None:
    markup = saved_keyboard("rec", can_add_quick=False)
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert not any(d.startswith(f"{CB_QUICK_ADD}:") for d in datas)


# ── Bot flow: pressing a button ──────────────────────────────────────────────


async def test_pressing_a_button_saves_without_gemini() -> None:
    storage = FakeStorage(_user(quick_expenses=[_cafe()]))
    ctx = _context(storage)
    update = _message_update("☕ Cafe 100")

    consumed = await quick.handle_quick_press(update, ctx, "☕ Cafe 100")

    assert consumed
    (record,) = storage.records.values()
    assert record.source == ExpenseSource.quick
    assert record.amount_local == 100
    assert record.local_currency == "THB"
    assert record.amount_base == pytest.approx(3.0)
    assert (record.category, record.subcategory, record.description) == ("food", "cafe", "Cafe")
    assert record.raw_input == "☕ Cafe 100"
    assert record.trip_id == ""
    update.message.reply_text.assert_awaited_once()
    # The card offers Undo etc., but not "make a quick button" again.
    keyboard = update.message.reply_text.call_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert any(d.startswith("undo:") for d in datas)
    assert not any(d.startswith(f"{CB_QUICK_ADD}:") for d in datas)


async def test_preset_currency_is_used_for_the_expense() -> None:
    storage = FakeStorage(_user(quick_expenses=[_cafe(currency="USD", amount=4)]))
    ctx = _context(storage, rate=1.0)

    assert await quick.handle_quick_press(_message_update(), ctx, "☕ Cafe 4 USD")

    (record,) = storage.records.values()
    assert (record.amount_local, record.local_currency) == (4, "USD")


async def test_quick_expense_is_tagged_with_the_active_trip() -> None:
    trip = Trip(id="tripabcd", name="Georgia", start_date=date(2020, 1, 1))
    storage = FakeStorage(_user(quick_expenses=[_cafe()], active_trip_id=trip.id))
    storage.trips[trip.id] = trip
    ctx = _context(storage)

    await quick.handle_quick_press(_message_update(), ctx, "☕ Cafe 100")

    (record,) = storage.records.values()
    assert record.trip_id == "tripabcd"


async def test_ordinary_text_is_not_consumed() -> None:
    storage = FakeStorage(_user(quick_expenses=[_cafe()]))
    ctx = _context(storage)

    assert not await quick.handle_quick_press(_message_update(), ctx, "кафе 100")
    # Plain text does not start with an emoji, so the user is not even looked up.
    assert storage.find_calls == 0

    assert not await quick.handle_quick_press(_message_update(), ctx, "🍕 pizza 300")
    assert storage.records == {}


async def test_button_added_elsewhere_is_found_after_a_fresh_read() -> None:
    storage = FakeStorage(_user())
    ctx = _context(storage)
    await ctx.bot_data["registry"].get_user(TG_ID)  # cache the user without presets
    storage.user = storage.user.model_copy(update={"quick_expenses": [_cafe()]})  # Mini App edit

    assert await quick.handle_quick_press(_message_update(), ctx, "☕ Cafe 100")
    assert len(storage.records) == 1


async def test_deleted_amountless_button_gets_a_fresh_keyboard() -> None:
    storage = FakeStorage(_user(quick_expenses=[_cafe()]))
    ctx = _context(storage)
    update = _message_update()

    assert await quick.handle_quick_press(update, ctx, "🛒 Groceries…")

    assert storage.records == {}
    text = update.message.reply_text.call_args.args[0]
    assert "no longer exists" in text
    markup = update.message.reply_text.call_args.kwargs["reply_markup"]
    assert markup.keyboard[0][0].text == "☕ Cafe 100"


async def test_pressing_a_button_cancels_a_pending_prompt() -> None:
    storage = FakeStorage(_user(quick_expenses=[_cafe()]))
    ctx = _context(storage)
    ctx.user_data["awaiting"] = "trip_name"

    assert await quick.handle_quick_press(_message_update(), ctx, "☕ Cafe 100")
    assert "awaiting" not in ctx.user_data
    assert len(storage.records) == 1


async def test_handle_text_routes_button_presses_before_gemini() -> None:
    from handlers.text import handle_text

    storage = FakeStorage(_user(quick_expenses=[_cafe()]))
    ctx = _context(storage)
    ctx.bot_data["gemini"] = MagicMock()
    ctx.bot_data["gemini"].parse_text = AsyncMock(side_effect=AssertionError("Gemini must not run"))
    update = _message_update("☕ Cafe 100")

    await handle_text(update, ctx)

    assert len(storage.records) == 1


async def test_handle_text_ignores_buttons_during_onboarding() -> None:
    from handlers.text import handle_text

    storage = FakeStorage(_user(quick_expenses=[_cafe()]))
    ctx = _context(storage)
    ctx.user_data["awaiting"] = "onboard_base_currency"
    update = _message_update("☕ Cafe 100")

    await handle_text(update, ctx)

    assert storage.records == {}
    assert ctx.user_data["awaiting"] == "onboard_base_currency"


# ── Bot flow: presets without an amount ──────────────────────────────────────


async def test_amountless_button_asks_then_saves_the_amount() -> None:
    from handlers.text import handle_text

    storage = FakeStorage(_user(quick_expenses=[_groceries()]))
    ctx = _context(storage)
    ctx.bot_data["gemini"] = MagicMock()

    ask = _message_update("🛒 Groceries…")
    await handle_text(ask, ctx)
    assert storage.records == {}
    assert ctx.user_data["awaiting"] == "quick_amount:groc0001"
    assert "how much? (THB)" in ask.message.reply_text.call_args.args[0]

    await handle_text(_message_update("450,5"), ctx)

    (record,) = storage.records.values()
    assert (record.amount_local, record.local_currency) == (450.5, "THB")
    assert record.description == "Groceries"
    assert "awaiting" not in ctx.user_data


async def test_amount_reply_may_carry_a_currency() -> None:
    from handlers.text import handle_text

    storage = FakeStorage(_user(quick_expenses=[_groceries()]))
    ctx = _context(storage)
    ctx.user_data["awaiting"] = "quick_amount:groc0001"

    await handle_text(_message_update("12 usd"), ctx)

    (record,) = storage.records.values()
    assert (record.amount_local, record.local_currency) == (12, "USD")


@pytest.mark.parametrize("reply", ["abc", "12 XYZ"])
async def test_bad_amount_keeps_waiting(reply: str) -> None:
    from handlers.text import handle_text

    storage = FakeStorage(_user(quick_expenses=[_groceries()]))
    ctx = _context(storage)
    ctx.user_data["awaiting"] = "quick_amount:groc0001"
    update = _message_update(reply)

    await handle_text(update, ctx)

    assert storage.records == {}
    assert ctx.user_data["awaiting"] == "quick_amount:groc0001"
    update.message.reply_text.assert_awaited_once()


async def test_cancel_drops_the_prompt() -> None:
    from handlers.callbacks import handle_callback

    storage = FakeStorage(_user(quick_expenses=[_groceries()]))
    ctx = _context(storage)
    ctx.user_data["awaiting"] = "quick_amount:groc0001"
    update = _callback_update("qe_cancel")

    await handle_callback(update, ctx)

    assert "awaiting" not in ctx.user_data
    update.callback_query.edit_message_text.assert_awaited_once_with("Cancelled.")


# ── Bot flow: "⚡ Quick button" under a saved expense ─────────────────────────


def _saved_record(**kwargs) -> ExpenseRecord:
    defaults = dict(
        id="rec-1",
        amount_local=120,
        local_currency="THB",
        amount_base=3.6,
        base_currency="USD",
        fx_rate=0.03,
        category="food",
        subcategory="cafe",
        description="Coffee",
        source=ExpenseSource.text,
    )
    defaults.update(kwargs)
    return ExpenseRecord(**defaults)


async def test_quick_button_creates_preset_from_the_stored_record() -> None:
    from handlers.callbacks import handle_callback

    storage = FakeStorage(_user(quick_keyboard_hidden=True))
    storage.records["rec-1"] = _saved_record()
    ctx = _context(storage)
    update = _callback_update("qe_add:rec-1")

    await handle_callback(update, ctx)

    (preset,) = storage.user.quick_expenses
    assert (preset.name, preset.category, preset.subcategory) == ("Coffee", "food", "cafe")
    assert (preset.amount, preset.currency, preset.emoji) == (120, "THB", "🍕")
    # Adding a button brings the keyboard back and shows it right away.
    assert storage.user.quick_keyboard_hidden is False
    reply = update.callback_query.message.reply_text.call_args
    assert "🍕 Coffee 120" in reply.args[0]
    assert reply.kwargs["reply_markup"].keyboard[0][0].text == "🍕 Coffee 120"
    # The card loses its "⚡ Quick button".
    update.callback_query.edit_message_reply_markup.assert_awaited_once()


async def test_quick_button_respects_the_limit() -> None:
    from handlers.callbacks import handle_callback

    items = [_cafe(id=f"id{i:06d}", name=f"Item {i}") for i in range(QUICK_EXPENSES_LIMIT)]
    storage = FakeStorage(_user(quick_expenses=items))
    storage.records["rec-1"] = _saved_record()
    update = _callback_update("qe_add:rec-1")

    await handle_callback(update, _context(storage))

    assert len(storage.user.quick_expenses) == QUICK_EXPENSES_LIMIT
    assert "maximum" in update.callback_query.message.reply_text.call_args.args[0]


async def test_quick_button_refuses_a_duplicate() -> None:
    from handlers.callbacks import handle_callback

    storage = FakeStorage(_user(quick_expenses=[_cafe(emoji="🍕", name="Coffee", amount=120)]))
    storage.records["rec-1"] = _saved_record()
    update = _callback_update("qe_add:rec-1")

    await handle_callback(update, _context(storage))

    assert len(storage.user.quick_expenses) == 1
    assert "already have" in update.callback_query.message.reply_text.call_args.args[0]


async def test_quick_button_for_missing_record() -> None:
    from handlers.callbacks import handle_callback

    storage = FakeStorage(_user())
    update = _callback_update("qe_add:nope")

    await handle_callback(update, _context(storage))

    assert storage.user.quick_expenses == []


# ── /quick ───────────────────────────────────────────────────────────────────


async def test_quick_command_lists_presets_inline() -> None:
    storage = FakeStorage(_user(quick_expenses=[_cafe(), _groceries()]))
    update = _message_update("/quick")

    await quick.quick_command(update, _context(storage))

    markup = update.message.reply_text.call_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert datas == ["qe:cafe0001", "qe:groc0001", "qe_kb:hide"]


async def test_quick_command_without_presets_explains_how_to_add() -> None:
    storage = FakeStorage(_user())
    update = _message_update("/quick")

    await quick.quick_command(update, _context(storage))

    assert "⚡ Quick button" in update.message.reply_text.call_args.args[0]


async def test_quick_command_on_sheets_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "sheets")
    update = _message_update("/quick")

    await quick.quick_command(update, _context(FakeStorage(_user())))

    assert "Firestore" in update.message.reply_text.call_args.args[0]


async def test_inline_press_from_quick_list_saves() -> None:
    from handlers.callbacks import handle_callback

    storage = FakeStorage(_user(quick_expenses=[_cafe()]))

    await handle_callback(_callback_update("qe:cafe0001"), _context(storage))

    assert len(storage.records) == 1


async def test_hide_and_show_keyboard() -> None:
    from handlers.callbacks import handle_callback

    storage = FakeStorage(_user(quick_expenses=[_cafe()]))
    ctx = _context(storage)

    hide = _callback_update("qe_kb:hide")
    await handle_callback(hide, ctx)
    assert storage.user.quick_keyboard_hidden is True
    assert isinstance(hide.callback_query.message.reply_text.call_args.kwargs["reply_markup"], ReplyKeyboardRemove)

    show = _callback_update("qe_kb:show")
    await handle_callback(show, ctx)
    assert storage.user.quick_keyboard_hidden is False
    assert isinstance(show.callback_query.message.reply_text.call_args.kwargs["reply_markup"], ReplyKeyboardMarkup)


async def test_start_attaches_the_quick_keyboard() -> None:
    from handlers.commands import start

    storage = FakeStorage(_user(quick_expenses=[_cafe()]))
    update = _message_update("/start")

    await start(update, _context(storage))

    markup = update.message.reply_text.call_args.kwargs["reply_markup"]
    assert isinstance(markup, ReplyKeyboardMarkup)


# ── /api/quick-expenses ──────────────────────────────────────────────────────


def _registry_for(user: User) -> AsyncMock:
    m = AsyncMock()
    m.get_user.return_value = user
    return m


async def test_api_get_returns_presets_and_limit() -> None:
    user = _user(quick_expenses=[_cafe(), _groceries()])
    body, status = await _call("GET", "/api/quick-expenses", FakeStorage(user), _registry_for(user))

    assert status == 200
    assert body["limit"] == QUICK_EXPENSES_LIMIT
    assert [i["id"] for i in body["items"]] == ["cafe0001", "groc0001"]
    assert body["items"][1]["amount"] is None


async def test_api_is_501_on_sheets_backend() -> None:
    storage = MagicMock()
    storage.get_quick_expenses.side_effect = NotImplementedError
    storage.set_quick_expenses.side_effect = NotImplementedError
    storage.get_categories.return_value = FakeStorage(_user()).categories
    user = _user()

    _, get_status = await _call("GET", "/api/quick-expenses", storage, _registry_for(user))
    _, put_status = await _call(
        "PUT", "/api/quick-expenses", storage, _registry_for(user), json_body={"items": []}
    )
    assert (get_status, put_status) == (501, 501)


async def test_api_put_replaces_list_and_sends_keyboard() -> None:
    user = _user(quick_expenses=[_cafe()])
    storage = FakeStorage(user)
    items = [
        {"name": "Taxi", "category": "transport", "amount": 150},
        {"id": "cafe0001", "name": "Cafe", "emoji": "☕", "category": "food", "subcategory": "cafe", "amount": 90},
    ]

    with patch("handlers.quick.send_keyboard_update", new=AsyncMock()) as send:
        body, status = await _call(
            "PUT", "/api/quick-expenses", storage, _registry_for(user), json_body={"items": items}
        )

    assert status == 200, body
    assert [q.name for q in storage.user.quick_expenses] == ["Taxi", "Cafe"]
    assert storage.user.quick_expenses[0].emoji == "🚗"
    assert len(storage.user.quick_expenses[0].id) == 8
    assert storage.user.quick_expenses[1].amount == 90
    assert [i["name"] for i in body["items"]] == ["Taxi", "Cafe"]
    sent_user = send.await_args.args[0]
    assert [q.name for q in sent_user.quick_expenses] == ["Taxi", "Cafe"]


@pytest.mark.parametrize(
    ("items", "fragment"),
    [
        ("nope", "must be a list"),
        ([{"name": f"N{i}", "category": "food"} for i in range(QUICK_EXPENSES_LIMIT + 1)], "at most"),
        ([{"name": "", "category": "food"}], "items[0]"),
        ([{"name": "X", "category": "pets"}], "unknown category"),
        ([{"name": "X", "category": "food", "subcategory": "sushi"}], "unknown subcategory"),
        ([{"name": "X", "category": "food", "currency": "ABC"}], "ISO 4217"),
        ([{"name": "X", "category": "food", "amount": -1}], "items[0]"),
        (
            [{"name": "X", "emoji": "☕", "category": "food"}, {"name": "X", "emoji": "☕", "category": "food"}],
            "same button",
        ),
        (
            [{"id": "same0001", "name": "A", "category": "food"}, {"id": "same0001", "name": "B", "category": "food"}],
            "unique",
        ),
    ],
)
async def test_api_put_validation(items: object, fragment: str) -> None:
    user = _user()
    storage = FakeStorage(user)

    with patch("handlers.quick.send_keyboard_update", new=AsyncMock()) as send:
        body, status = await _call(
            "PUT", "/api/quick-expenses", storage, _registry_for(user), json_body={"items": items}
        )

    assert status == 400
    assert fragment in body["error"]
    assert storage.user.quick_expenses == []
    send.assert_not_awaited()


async def test_send_keyboard_update_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    failing_bot = MagicMock()
    failing_bot.__aenter__ = AsyncMock(side_effect=RuntimeError("network down"))
    failing_bot.__aexit__ = AsyncMock(return_value=False)

    with patch("telegram.Bot", return_value=failing_bot):
        await quick.send_keyboard_update(_user(quick_expenses=[_cafe()]))
