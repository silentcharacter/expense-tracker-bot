"""Quick expenses: one-tap presets shown as a persistent reply keyboard.

Pressing a reply-keyboard button sends its text as a normal message.
``handle_text`` hands messages that start with an emoji to
``handle_quick_press``, which matches the text against the user's presets and
saves the expense straight away — no Gemini call. Presets without an amount ask
for it first. ``/quick`` lists the presets as inline buttons (for users who hid
the keyboard) and toggles the keyboard.
"""

import logging
import os
import re
from typing import Optional, Union

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import ContextTypes

from handlers.callbacks import (
    AWAITING_EDIT_AMOUNT,
    CB_QUICK_ADD,
    CB_QUICK_CANCEL,
    CB_QUICK_KEYBOARD,
    CB_QUICK_PRESS,
    saved_keyboard,
)
from handlers.expense_saving import save_expense
from models.expense import ExpenseRecord, ExpenseSource, User
from services.user_registry import UserRegistry
from models.quick_expense import (
    QUICK_EXPENSES_LIMIT,
    QuickExpense,
    find_duplicate_button,
    starts_with_symbol,
)

logger = logging.getLogger(__name__)

AWAITING_QUICK_AMOUNT = "quick_amount:"
"""``context.user_data["awaiting"]`` prefix; followed by the preset id."""

_UNSUPPORTED = "Quick expenses require the Firestore backend."
_PLACEHOLDER = "Amount and description, or tap a button"
_ROW_SIZE = 3

# "450", "450.5", "450,5", "1 500", "12 usd", "12usd"
_AMOUNT_RE = re.compile(r"^\s*(\d[\d\s]*(?:[.,]\d+)?)\s*([A-Za-z]{3})?\s*$")

ReplyMarkup = Union[ReplyKeyboardMarkup, ReplyKeyboardRemove]


def _supported() -> bool:
    return os.environ.get("STORAGE_BACKEND") == "firestore"


# ── Pure helpers ─────────────────────────────────────────────────────────────


def quick_reply_markup(user: User) -> ReplyMarkup:
    """Reply keyboard with the user's presets, or a removal when there is nothing to show."""
    if user.quick_keyboard_hidden or not user.quick_expenses:
        return ReplyKeyboardRemove()
    buttons = [
        KeyboardButton(q.button_text(user.default_currency)) for q in user.quick_expenses
    ]
    rows = [buttons[i : i + _ROW_SIZE] for i in range(0, len(buttons), _ROW_SIZE)]
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=_PLACEHOLDER,
    )


def match_quick_button(user: User, text: str) -> Optional[QuickExpense]:
    """Return the preset whose button text equals ``text`` (ignoring outer spaces)."""
    wanted = (text or "").strip()
    for preset in user.quick_expenses:
        if preset.button_text(user.default_currency) == wanted:
            return preset
    return None


def parse_amount(text: str) -> Optional[tuple[float, Optional[str]]]:
    """Parse "450", "450,5", "1 500" or "12 usd" into (amount, currency or None)."""
    m = _AMOUNT_RE.match(text or "")
    if not m:
        return None
    try:
        amount = float(m.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    if amount <= 0:
        return None
    currency = m.group(2).upper() if m.group(2) else None
    return amount, currency


def preset_from_record(record: ExpenseRecord) -> QuickExpense:
    """Turn a saved expense into a preset with the same category, amount and currency."""
    return QuickExpense(
        name=record.description or record.category,
        category=record.category,
        subcategory=record.subcategory,
        description=record.description,
        amount=record.amount_local,
        currency=record.local_currency,
    )


def presets_inline_keyboard(user: User) -> InlineKeyboardMarkup:
    """Inline version of the presets plus the show/hide toggle, for /quick."""
    buttons = [
        InlineKeyboardButton(
            q.button_text(user.default_currency), callback_data=f"{CB_QUICK_PRESS}:{q.id}"
        )
        for q in user.quick_expenses
    ]
    rows = [buttons[i : i + _ROW_SIZE] for i in range(0, len(buttons), _ROW_SIZE)]
    if user.quick_keyboard_hidden:
        rows.append([InlineKeyboardButton("⌨ Show keyboard", callback_data=f"{CB_QUICK_KEYBOARD}:show")])
    else:
        rows.append([InlineKeyboardButton("🙈 Hide keyboard", callback_data=f"{CB_QUICK_KEYBOARD}:hide")])
    return InlineKeyboardMarkup(rows)


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✖ Cancel", callback_data=CB_QUICK_CANCEL)]])


def _find_preset(user: User, preset_id: str) -> Optional[QuickExpense]:
    return next((q for q in user.quick_expenses if q.id == preset_id), None)


# ── Saving ───────────────────────────────────────────────────────────────────


async def _save_and_reply(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
    preset: QuickExpense,
    amount: float,
    currency: str,
) -> None:
    """Save one quick expense and reply with the usual confirmation card."""
    _, text, keyboard = await save_expense(
        context,
        user,
        amount=amount,
        currency=currency,
        category=preset.category,
        subcategory=preset.subcategory,
        description=preset.expense_description,
        source=ExpenseSource.quick,
        raw_input=preset.button_text(user.default_currency),
    )
    await message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def _press(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
    preset: QuickExpense,
) -> None:
    """Save a preset with a fixed amount, or ask for the amount."""
    currency = preset.effective_currency(user.default_currency)
    if preset.asks_amount:
        context.user_data["awaiting"] = f"{AWAITING_QUICK_AMOUNT}{preset.id}"
        await message.reply_text(
            f"{preset.emoji} {preset.name} — how much? ({currency})",
            reply_markup=_cancel_keyboard(),
        )
        return
    await _save_and_reply(message, context, user, preset, preset.amount, currency)


async def handle_quick_press(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """Handle a message that may be a quick-expense button press.

    Returns True if the message was consumed. Unmatched messages return False so
    "🍕 pizza 300" typed by hand still goes to Gemini.
    """
    if not starts_with_symbol(text):
        return False

    registry = context.bot_data["registry"]
    tg_id = update.effective_user.id
    user = await registry.get_user(tg_id)
    if user is None:
        return False

    preset = match_quick_button(user, text)
    if preset is None and _supported():
        # The cached user may predate an edit made in the Mini App on another
        # Cloud Function instance — re-read once before giving up.
        user = await registry.refresh_user(tg_id)
        preset = match_quick_button(user, text) if user else None

    if preset is None:
        if user is not None and text.rstrip().endswith("…"):
            # Looks exactly like one of our amount-less buttons but no longer exists.
            await update.message.reply_text(
                "That quick button no longer exists.", reply_markup=quick_reply_markup(user)
            )
            return True
        return False

    # A button press means the user moved on from whatever the bot was waiting for.
    context.user_data.pop("awaiting", None)
    await _press(update.message, context, user, preset)
    return True


async def handle_quick_amount_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, awaiting: str, text: str
) -> None:
    """Receive the amount for a preset that has none."""
    preset_id = awaiting[len(AWAITING_QUICK_AMOUNT):]
    registry = context.bot_data["registry"]
    tg_id = update.effective_user.id

    user = await registry.get_user(tg_id)
    preset = _find_preset(user, preset_id) if user else None
    if user is not None and preset is None and _supported():
        user = await registry.refresh_user(tg_id)
        preset = _find_preset(user, preset_id) if user else None
    if user is None or preset is None:
        context.user_data.pop("awaiting", None)
        await update.message.reply_text("That quick button no longer exists.")
        return

    parsed = parse_amount(text)
    if parsed is None:
        # Keep waiting: the prompt still stands.
        await update.message.reply_text(
            "Send just the amount, e.g. 450 — or tap ✖ Cancel.",
            reply_markup=_cancel_keyboard(),
        )
        return

    amount, currency = parsed
    if currency and not UserRegistry.validate_currency(currency):
        await update.message.reply_text(
            f"'{currency}' is not a currency code I know. Send e.g. 450 or 12 USD."
        )
        return

    context.user_data.pop("awaiting", None)
    await _save_and_reply(
        update.message,
        context,
        user,
        preset,
        amount,
        currency or preset.effective_currency(user.default_currency),
    )


# ── /quick ───────────────────────────────────────────────────────────────────


async def quick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/quick — list quick expenses as inline buttons and toggle the keyboard."""
    if not _supported():
        await update.message.reply_text(_UNSUPPORTED)
        return

    registry = context.bot_data["registry"]
    user = await registry.refresh_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("You are not registered yet. Send /start to sign up.")
        return

    if not user.quick_expenses:
        await update.message.reply_text(
            "You have no quick buttons yet.\n\n"
            "Tap ⚡ Quick button under any saved expense to turn it into a one-tap "
            "button, or set them up in the app (Settings → Quick expenses)."
        )
        return

    state = "hidden" if user.quick_keyboard_hidden else "shown under the input field"
    await update.message.reply_text(
        f"⚡ Quick expenses — tap to save. The keyboard is {state}.",
        reply_markup=presets_inline_keyboard(user),
    )


# ── Callbacks ────────────────────────────────────────────────────────────────


def callback_handlers() -> dict:
    """Map callback-data prefixes to handlers, for handlers/callbacks.py."""
    return {
        CB_QUICK_ADD: _cb_add,
        CB_QUICK_PRESS: _cb_press,
        CB_QUICK_KEYBOARD: _cb_keyboard,
        CB_QUICK_CANCEL: _cb_cancel,
    }


async def _cb_add(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Turn a saved expense into a quick-expense preset."""
    query = update.callback_query
    record_id = parts[1] if len(parts) > 1 else ""
    if not _supported():
        await query.message.reply_text(_UNSUPPORTED)
        return

    registry = context.bot_data["registry"]
    storage = context.bot_data["sheets"]
    tg_id = update.effective_user.id
    user = await registry.refresh_user(tg_id)
    if user is None:
        await query.message.reply_text("You are not registered. Send /start.")
        return

    # Read the stored record: the description or category may have been edited
    # since the card was shown, and user_data does not survive instance changes.
    record = storage.get_transaction(user.spreadsheet_id, record_id)
    if record is None:
        await query.message.reply_text("Could not find that expense. It may have been removed.")
        return

    if len(user.quick_expenses) >= QUICK_EXPENSES_LIMIT:
        await query.message.reply_text(
            f"You already have {QUICK_EXPENSES_LIMIT} quick buttons — the maximum. "
            "Remove one in the app (Settings → Quick expenses) first."
        )
        return

    preset = preset_from_record(record)
    items = [*user.quick_expenses, preset]
    if find_duplicate_button(items, user.default_currency):
        await query.message.reply_text(
            f"You already have the button {preset.button_text(user.default_currency)}."
        )
        return

    user = await registry.set_quick_expenses(tg_id, items)
    if user.quick_keyboard_hidden:
        user = await registry.set_quick_keyboard_hidden(tg_id, False)

    try:
        await query.edit_message_reply_markup(
            saved_keyboard(record.id, in_trip=bool(record.trip_id), can_add_quick=False)
        )
    except Exception as exc:  # message too old or unchanged — not worth failing over
        logger.debug("Could not drop the quick button from the card: %s", exc)

    await query.message.reply_text(
        f"⚡ Added quick button: {preset.button_text(user.default_currency)}\n"
        "Tap it below to save this expense again. /quick to manage.",
        reply_markup=quick_reply_markup(user),
    )


async def _cb_press(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Inline press from the /quick list."""
    query = update.callback_query
    preset_id = parts[1] if len(parts) > 1 else ""
    registry = context.bot_data["registry"]
    user = await registry.refresh_user(update.effective_user.id)
    preset = _find_preset(user, preset_id) if user else None
    if user is None or preset is None:
        await query.message.reply_text("That quick button no longer exists. Send /quick again.")
        return
    context.user_data.pop("awaiting", None)
    await _press(query.message, context, user, preset)


async def _cb_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Show or hide the reply keyboard."""
    query = update.callback_query
    hide = (parts[1] if len(parts) > 1 else "") == "hide"
    registry = context.bot_data["registry"]
    try:
        user = await registry.set_quick_keyboard_hidden(update.effective_user.id, hide)
    except NotImplementedError:
        await query.message.reply_text(_UNSUPPORTED)
        return

    try:
        await query.edit_message_reply_markup(presets_inline_keyboard(user))
    except Exception as exc:
        logger.debug("Could not refresh the /quick keyboard: %s", exc)

    if hide:
        await query.message.reply_text(
            "Quick buttons hidden. Send /quick to bring them back.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await query.message.reply_text(
            "Quick buttons are back under the input field.",
            reply_markup=quick_reply_markup(user),
        )


async def _cb_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Drop a pending amount prompt (quick-expense amount or amount edit)."""
    query = update.callback_query
    if (context.user_data.get("awaiting") or "").startswith(
        (AWAITING_QUICK_AMOUNT, AWAITING_EDIT_AMOUNT)
    ):
        context.user_data.pop("awaiting", None)
    await query.edit_message_text("Cancelled.")


# ── Sending the keyboard from outside a chat update (Mini App API) ───────────


async def send_keyboard_update(user: User) -> None:
    """Push the current quick keyboard to the user's chat after an edit in the Mini App.

    A reply keyboard only changes when the bot sends a message carrying it, so
    an edit made in the app needs a short message. Failures are logged, never
    raised: the edit itself has already been saved.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return
    from telegram import Bot

    if user.quick_expenses and not user.quick_keyboard_hidden:
        text = "⚡ Quick buttons updated."
    elif user.quick_expenses:
        text = "⚡ Quick buttons updated. They are hidden — send /quick to show them."
    else:
        text = "⚡ All quick buttons removed."
    try:
        async with Bot(token) as bot:
            await bot.send_message(
                chat_id=user.telegram_id, text=text, reply_markup=quick_reply_markup(user)
            )
    except Exception as exc:
        logger.warning("Could not send the quick keyboard to %s: %s", user.telegram_id, exc)
