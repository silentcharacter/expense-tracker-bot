"""Inline keyboard callback handler."""

import logging
from typing import TYPE_CHECKING, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from models.expense import ExpenseRecord, ExpenseSource
from models.category import category_label, subcategory_label

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Callback data prefixes ──────────────────────────────────────────────────
# Format: "<PREFIX>:<payload>"

CB_UNDO = "undo"
CB_EDIT_CATEGORY = "edit_cat"
CB_SET_CATEGORY = "set_cat"
CB_SET_SUBCATEGORY = "set_sub"
CB_ONBOARD_BASE = "ob_base"
CB_ONBOARD_DEFAULT = "ob_default"
CB_SETTINGS_BASE = "set_base"
CB_SETTINGS_DEFAULT = "set_default"
CB_SHOW_SETTINGS_BASE = "show_settings_base"
CB_SHOW_SETTINGS_DEFAULT = "show_settings_default"
CB_EDIT_DESCRIPTION = "edit_desc"

# Popular currencies shown on inline keyboards
POPULAR_CURRENCIES = ["USD", "EUR", "THB", "GBP", "JPY", "GEL", "ILS", "AED"]


# ── Keyboard builders ────────────────────────────────────────────────────────

def saved_keyboard(record_id: str) -> InlineKeyboardMarkup:
    """Build the undo / edit-category / edit-description keyboard for a just-saved expense."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("↩ Undo", callback_data=f"{CB_UNDO}:{record_id}"),
                InlineKeyboardButton("✎ Category", callback_data=f"{CB_EDIT_CATEGORY}:{record_id}"),
            ],
            [
                InlineKeyboardButton("✏ Description", callback_data=f"{CB_EDIT_DESCRIPTION}:{record_id}"),
            ],
        ]
    )


async def category_keyboard(
    record_id: str,
    spreadsheet_id: str,
    sheets,
) -> InlineKeyboardMarkup:
    """Build a keyboard with the user's categories for editing."""
    from services.sheets import SheetsService as _SheetsService  # noqa: F401
    categories = sheets.get_categories(spreadsheet_id)
    buttons = [
        InlineKeyboardButton(
            cat.label,
            callback_data=f"{CB_SET_CATEGORY}:{record_id}:{cat.slug}",
        )
        for cat in categories
    ]
    # Arrange in two columns
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def subcategory_keyboard(record_id: str, subcategories: list) -> InlineKeyboardMarkup:
    """Build a keyboard with subcategory choices plus a skip option."""
    buttons = [
        InlineKeyboardButton(
            sub.label,
            callback_data=f"{CB_SET_SUBCATEGORY}:{record_id}:{sub.slug}",
        )
        for sub in subcategories
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([
        InlineKeyboardButton(
            "— Skip —",
            callback_data=f"{CB_SET_SUBCATEGORY}:{record_id}:_none_",
        )
    ])
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
        CB_UNDO: _handle_undo,
        CB_EDIT_CATEGORY: _handle_edit_category,
        CB_SET_CATEGORY: _handle_set_category,
        CB_SET_SUBCATEGORY: _handle_set_subcategory,
        CB_ONBOARD_BASE: _handle_onboard_base_currency,
        CB_ONBOARD_DEFAULT: _handle_onboard_default_currency,
        CB_SETTINGS_BASE: _handle_settings_base_currency,
        CB_SETTINGS_DEFAULT: _handle_settings_default_currency,
        CB_SHOW_SETTINGS_BASE: _handle_show_settings_base,
        CB_SHOW_SETTINGS_DEFAULT: _handle_show_settings_default,
        CB_EDIT_DESCRIPTION: _handle_edit_description,
    }

    handler = handlers.get(prefix)
    if handler:
        await handler(update, context, parts)
    else:
        logger.warning("Unknown callback prefix: %s", prefix)
        await query.edit_message_text("Unknown action.")


# ── Undo flow ────────────────────────────────────────────────────────────────

async def _handle_undo(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Delete the just-saved expense by ID."""
    query = update.callback_query
    record_id = parts[1] if len(parts) > 1 else ""

    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start to sign up.")
        return

    deleted = sheets.delete_transaction_by_id(user.spreadsheet_id, record_id)
    context.user_data.pop("last_expense", None)

    if deleted:
        await query.edit_message_text(
            f"Removed: {deleted.amount_local:,.2f} {deleted.local_currency} — {deleted.description}"
        )
    else:
        await query.edit_message_text("Could not find the expense to remove.")


async def _handle_edit_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Show the category selection keyboard."""
    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    query = update.callback_query
    record_id = parts[1] if len(parts) > 1 else ""

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start.")
        return

    markup = await category_keyboard(record_id, user.spreadsheet_id, sheets)
    await query.edit_message_text("Choose a category:", reply_markup=markup)


async def _apply_category_update(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    sheets,
    user,
    record_id: str,
    category: str,
    subcategory: str,
) -> None:
    """Persist category+subcategory to Sheets and redisplay the saved card."""
    ok = sheets.update_transaction_category(user.spreadsheet_id, record_id, category, subcategory)
    if not ok:
        await query.edit_message_text(
            "Could not update the category. The expense may have been removed."
        )
        return

    last = context.user_data.get("last_expense", {})
    record: Optional[ExpenseRecord] = last.get("record")
    if record:
        updated = record.model_copy(update={"category": category, "subcategory": subcategory})
        context.user_data["last_expense"] = {"record": updated}
    else:
        updated = None

    cat_label_str = category_label(category)
    sub_label_str = subcategory_label(category, subcategory) if subcategory else ""
    cat_display = f"{cat_label_str} / {sub_label_str}" if sub_label_str else cat_label_str

    if updated:
        from handlers.budget_alerts import check_and_send_budget_alert
        await check_and_send_budget_alert(context.bot, user, updated, context.bot_data["sheets"])
        await query.edit_message_text(
            f"{_format_confirmation(updated, user.base_currency, cat_display)}\n\n✓ Saved",
            reply_markup=saved_keyboard(record_id),
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            f"Category updated to {cat_display}.",
            reply_markup=saved_keyboard(record_id),
        )


async def _handle_set_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Show subcategory keyboard if available, otherwise save immediately."""
    query = update.callback_query
    if len(parts) < 3:
        await query.edit_message_text("Invalid action.")
        return

    record_id = parts[1]
    new_category = parts[2]

    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start.")
        return

    categories = sheets.get_categories(user.spreadsheet_id)
    cat_obj = next((c for c in categories if c.slug == new_category), None)
    subcats = cat_obj.subcategories if cat_obj else []

    if subcats:
        context.user_data["editing_category"] = new_category
        cat_label_str = category_label(new_category)
        await query.edit_message_text(
            f"Category: *{escape_markdown(cat_label_str)}*\nChoose a subcategory:",
            reply_markup=subcategory_keyboard(record_id, subcats),
            parse_mode="Markdown",
        )
    else:
        await _apply_category_update(query, context, sheets, user, record_id, new_category, "")


async def _handle_set_subcategory(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Save the chosen subcategory (or none) for an already-saved expense."""
    query = update.callback_query
    if len(parts) < 3:
        await query.edit_message_text("Invalid action.")
        return

    record_id = parts[1]
    sub_slug = parts[2]
    subcategory = "" if sub_slug == "_none_" else sub_slug
    category = context.user_data.pop("editing_category", "")

    if not category:
        await query.edit_message_text("Session expired. Please tap ✎ Category again.")
        return

    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start.")
        return

    await _apply_category_update(query, context, sheets, user, record_id, category, subcategory)


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

async def _handle_show_settings_base(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Show the currency keyboard for changing the base currency."""
    query = update.callback_query
    await query.edit_message_text(
        "Choose your new *base currency* (used for analytics and budgets):",
        parse_mode="Markdown",
        reply_markup=currency_keyboard(CB_SETTINGS_BASE),
    )


async def _handle_show_settings_default(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Show the currency keyboard for changing the default currency."""
    query = update.callback_query
    await query.edit_message_text(
        "Choose your new *default currency* (used when no currency is mentioned):",
        parse_mode="Markdown",
        reply_markup=currency_keyboard(CB_SETTINGS_DEFAULT),
    )


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


# ── Edit description flow ────────────────────────────────────────────────────

async def _handle_edit_description(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Prompt the user to type a new description for the expense."""
    query = update.callback_query
    record_id = parts[1] if len(parts) > 1 else ""

    context.user_data["awaiting"] = f"edit_description:{record_id}"
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("Send the new description for this expense:")


# ── Formatting helpers ───────────────────────────────────────────────────

def _esc(text: str) -> str:
    """Escape Markdown v1 special characters in user-facing text."""
    return escape_markdown(text, version=1)

def _format_confirmation(record: ExpenseRecord, base_currency: str, cat_label: str) -> str:
    """Format an expense confirmation message (Markdown v1)."""
    esc = _esc
    lines = [
        f"*{record.amount_local:,.2f} {esc(record.local_currency)}*",
        f"≈ {record.amount_base:,.2f} {esc(base_currency)} (rate {record.fx_rate:.4f})",
        f"Category: {esc(cat_label)}",
        f"Description: {esc(record.description)}",
    ]
    if record.subcategory:
        lines.insert(3, f"Subcategory: {esc(record.subcategory)}")
    return "\n".join(lines)
