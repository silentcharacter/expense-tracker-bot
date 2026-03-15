"""Inline keyboard callback handler."""

import logging
from typing import TYPE_CHECKING

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from models.expense import ExpenseRecord, ExpenseSource
from models.category import category_label, subcategory_label, CATEGORIES

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Callback data prefixes ──────────────────────────────────────────────────
# Format: "<PREFIX>:<payload>"

CB_CONFIRM = "confirm"
CB_CANCEL = "cancel"
CB_EDIT_CATEGORY = "edit_cat"
CB_SET_CATEGORY = "set_cat"
CB_ONBOARD_BASE = "ob_base"
CB_ONBOARD_DEFAULT = "ob_default"
CB_SETTINGS_BASE = "set_base"
CB_SETTINGS_DEFAULT = "set_default"

# Popular currencies shown on inline keyboards
POPULAR_CURRENCIES = ["USD", "EUR", "THB", "GBP", "JPY", "GEL", "ILS", "AED"]


# ── Keyboard builders ────────────────────────────────────────────────────────

def confirm_keyboard(record_id: str) -> InlineKeyboardMarkup:
    """Build the confirm / edit / cancel keyboard for a pending expense."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✓ Save", callback_data=f"{CB_CONFIRM}:{record_id}"),
                InlineKeyboardButton("✎ Category", callback_data=f"{CB_EDIT_CATEGORY}:{record_id}"),
                InlineKeyboardButton("✕ Cancel", callback_data=f"{CB_CANCEL}:{record_id}"),
            ]
        ]
    )


def category_keyboard(record_id: str) -> InlineKeyboardMarkup:
    """Build a keyboard with all available categories for editing."""
    buttons = [
        InlineKeyboardButton(
            cat.label,
            callback_data=f"{CB_SET_CATEGORY}:{record_id}:{cat.slug}",
        )
        for cat in CATEGORIES
    ]
    # Arrange in two columns
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def currency_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """Build a keyboard with popular currencies plus a 'Other…' option."""
    buttons = [
        InlineKeyboardButton(c, callback_data=f"{prefix}:{c}")
        for c in POPULAR_CURRENCIES
    ]
    rows = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton("Other…", callback_data=f"{prefix}:OTHER")])
    return InlineKeyboardMarkup(rows)


# ── Main callback handler ───────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route inline button presses to the appropriate handler.

    Reads callback_data, splits on ':', and dispatches by prefix.
    """
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":", maxsplit=2)
    prefix = parts[0] if parts else ""

    handlers = {
        CB_CONFIRM: _handle_confirm,
        CB_CANCEL: _handle_cancel,
        CB_EDIT_CATEGORY: _handle_edit_category,
        CB_SET_CATEGORY: _handle_set_category,
        CB_ONBOARD_BASE: _handle_onboard_base_currency,
        CB_ONBOARD_DEFAULT: _handle_onboard_default_currency,
        CB_SETTINGS_BASE: _handle_settings_base_currency,
        CB_SETTINGS_DEFAULT: _handle_settings_default_currency,
    }

    handler = handlers.get(prefix)
    if handler:
        await handler(update, context, parts)
    else:
        logger.warning("Unknown callback prefix: %s", prefix)
        await query.edit_message_text("Unknown action.")


# ── Confirmation flow ────────────────────────────────────────────────────────

async def _handle_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Persist the pending expense and acknowledge the user."""
    query = update.callback_query
    pending: dict = context.user_data.get("pending_expense", {})

    if not pending:
        await query.edit_message_text("Session expired. Please re-send the expense.")
        return

    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start to sign up.")
        return

    record: ExpenseRecord = pending["record"]
    sheets.append_transaction(user.spreadsheet_id, record)
    context.user_data.pop("pending_expense", None)

    cat_label = category_label(record.category)
    sub_label = subcategory_label(record.category, record.subcategory) if record.subcategory else ""
    cat_display = f"{cat_label} / {sub_label}" if sub_label else cat_label

    await query.edit_message_text(
        f"Saved: {record.amount_local:,.2f} {record.local_currency}"
        f" ({record.amount_base:,.2f} {user.base_currency})\n"
        f"{cat_display} — {record.description}"
    )


async def _handle_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Discard the pending expense."""
    query = update.callback_query
    context.user_data.pop("pending_expense", None)
    await query.edit_message_text("Cancelled.")


async def _handle_edit_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Show the category selection keyboard."""
    query = update.callback_query
    record_id = parts[1] if len(parts) > 1 else ""
    await query.edit_message_text(
        "Choose a category:",
        reply_markup=category_keyboard(record_id),
    )


async def _handle_set_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Update the category on the pending expense and return to confirm view."""
    query = update.callback_query
    if len(parts) < 3:
        await query.edit_message_text("Invalid action.")
        return

    new_category = parts[2]
    pending: dict = context.user_data.get("pending_expense", {})
    if not pending:
        await query.edit_message_text("Session expired. Please re-send the expense.")
        return

    record: ExpenseRecord = pending["record"]
    updated = record.model_copy(update={"category": new_category, "subcategory": ""})
    pending["record"] = updated
    context.user_data["pending_expense"] = pending

    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    user = await registry.get_user(update.effective_user.id)
    base_currency = user.base_currency if user else "?"

    cat_label = category_label(new_category)
    await query.edit_message_text(
        _format_confirmation(updated, base_currency, cat_label),
        reply_markup=confirm_keyboard(updated.id),
    )


# ── Onboarding currency selection ───────────────────────────────────────────

async def _handle_onboard_base_currency(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Store the chosen base currency and ask for the default currency."""
    query = update.callback_query
    currency = parts[1] if len(parts) > 1 else ""

    if currency == "OTHER":
        context.user_data["awaiting"] = "onboard_base_currency"
        await query.edit_message_text(
            "Type your base currency code (3 letters, e.g. SGD):"
        )
        return

    context.user_data["onboard_base_currency"] = currency
    await query.edit_message_text(
        f"Base currency: *{currency}*\n\nNow choose your default currency "
        "(used when you don't mention a currency):",
        parse_mode="Markdown",
        reply_markup=currency_keyboard(CB_ONBOARD_DEFAULT),
    )


async def _handle_onboard_default_currency(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Store the chosen default currency and complete onboarding."""
    query = update.callback_query
    currency = parts[1] if len(parts) > 1 else ""

    if currency == "OTHER":
        context.user_data["awaiting"] = "onboard_default_currency"
        await query.edit_message_text(
            "Type your default currency code (3 letters, e.g. THB):"
        )
        return

    base_currency = context.user_data.get("onboard_base_currency", "USD")
    context.user_data["onboard_default_currency"] = currency
    await _finish_onboarding(update, context, base_currency, currency)


async def _finish_onboarding(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    base_currency: str,
    default_currency: str,
) -> None:
    """Create the user account and send the welcome message."""
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    tg_user = update.effective_user

    try:
        user = await registry.create_user(
            telegram_id=tg_user.id,
            username=tg_user.username or "",
            display_name=tg_user.full_name,
            base_currency=base_currency,
            default_currency=default_currency,
        )
    except (ValueError, Exception) as exc:
        logger.exception("Onboarding failed for %s: %s", tg_user.id, exc)
        query = update.callback_query
        await query.edit_message_text(f"Registration failed: {exc}\nSend /start to try again.")
        return

    query = update.callback_query
    await query.edit_message_text(
        f"All set!\n\n"
        f"Base currency: *{user.base_currency}*\n"
        f"Default currency: *{user.default_currency}*\n\n"
        f"Send a voice message or type an expense to get started.\n"
        f"To access your Spreadsheet, send /email your@gmail.com",
        parse_mode="Markdown",
    )
    context.user_data.pop("onboard_base_currency", None)
    context.user_data.pop("onboard_default_currency", None)


# ── Settings currency selection ──────────────────────────────────────────────

async def _handle_settings_base_currency(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Update the user's base currency via /settings inline flow."""
    await _apply_settings_currency(update, context, parts, field="base_currency")


async def _handle_settings_default_currency(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Update the user's default currency via /settings inline flow."""
    await _apply_settings_currency(update, context, parts, field="default_currency")


async def _apply_settings_currency(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    parts: list[str],
    field: str,
) -> None:
    """Persist a settings change and confirm to the user."""
    query = update.callback_query
    currency = parts[1] if len(parts) > 1 else ""

    if currency == "OTHER":
        context.user_data["awaiting"] = f"settings_{field}"
        await query.edit_message_text(f"Type the new {field.replace('_', ' ')} code (3 letters):")
        return

    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start.")
        return

    base = currency if field == "base_currency" else user.base_currency
    default = currency if field == "default_currency" else user.default_currency

    try:
        updated = await registry.update_settings(update.effective_user.id, base, default)
    except (ValueError, Exception) as exc:
        await query.edit_message_text(f"Error: {exc}")
        return

    await query.edit_message_text(
        f"Settings updated.\n"
        f"Base currency: *{updated.base_currency}*\n"
        f"Default currency: *{updated.default_currency}*",
        parse_mode="Markdown",
    )


# ── Formatting helpers ───────────────────────────────────────────────────────

def _format_confirmation(record: ExpenseRecord, base_currency: str, cat_label: str) -> str:
    """Format an expense confirmation message."""
    lines = [
        f"*{record.amount_local:,.2f} {record.local_currency}*",
        f"≈ {record.amount_base:,.2f} {base_currency} (rate {record.fx_rate:.4f})",
        f"Category: {cat_label}",
        f"Description: {record.description}",
    ]
    if record.subcategory:
        lines.insert(3, f"Subcategory: {record.subcategory}")
    return "\n".join(lines)
