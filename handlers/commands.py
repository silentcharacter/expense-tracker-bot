"""Command handlers: /start, /email, /settings, /last, /undo, /export, /cat, /broadcast."""

import asyncio
import csv
import io
import logging
from datetime import date, timedelta, datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

from models.category import category_label
from handlers.callbacks import currency_keyboard, CB_ONBOARD_BASE, CB_SHOW_SETTINGS_BASE, CB_SHOW_SETTINGS_DEFAULT

logger = logging.getLogger(__name__)


# ── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — register a new user or greet an existing one.

    New users are guided through currency selection via inline keyboards.
    Existing users receive a summary of their settings.
    """
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    tg_user = update.effective_user

    user = await registry.get_user(tg_user.id)

    if user is not None:
        await update.message.reply_text(
            f"Welcome back, {user.display_name}!\n"
            f"Base currency: *{user.base_currency}* | Default: *{user.default_currency}*\n\n"
            f"Send a voice message or type an expense.",
            parse_mode="Markdown",
        )
        return

    # ── New user: start onboarding ──────────────────────────────────────────
    await update.message.reply_text(
        f"Hello, {tg_user.full_name}! Let's set up your expense tracker.\n\n"
        f"First, choose your *base currency* (used for analytics and budgets):",
        parse_mode="Markdown",
        reply_markup=currency_keyboard(CB_ONBOARD_BASE),
    )


# ── /email ───────────────────────────────────────────────────────────────────

async def email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/email — prompt for a Google account address, then share the Spreadsheet."""
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    tg_user = update.effective_user

    user = await registry.get_user(tg_user.id)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
        return

    context.user_data["awaiting"] = "email_address"
    await update.message.reply_text(
        "Please enter your Google account email address.\n"
        "Your Spreadsheet will be shared and transferred to that account."
    )


# ── /settings ────────────────────────────────────────────────────────────────

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/settings [base|default <CURRENCY>] — view or update currency settings.

    Examples:
      /settings            → show current settings
      /settings base EUR   → set base currency to EUR
      /settings default THB → set default currency to THB
    """
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    tg_user = update.effective_user

    user = await registry.get_user(tg_user.id)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
        return

    args = context.args or []

    # ── View settings ───────────────────────────────────────────────────────
    if not args:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"Change base ({user.base_currency})",
                        callback_data=CB_SHOW_SETTINGS_BASE,
                    ),
                    InlineKeyboardButton(
                        f"Change default ({user.default_currency})",
                        callback_data=CB_SHOW_SETTINGS_DEFAULT,
                    ),
                ]
            ]
        )
        await update.message.reply_text(
            f"Current settings:\n"
            f"Base currency: *{user.base_currency}*\n"
            f"Default currency: *{user.default_currency}*",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return

    # ── Update via command args: /settings base EUR ─────────────────────────
    if len(args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "  /settings base <CURRENCY>\n"
            "  /settings default <CURRENCY>\n\n"
            "Example: /settings base USD"
        )
        return

    field = args[0].lower()
    new_code = args[1].upper()

    if field not in ("base", "default"):
        await update.message.reply_text("Field must be 'base' or 'default'.")
        return

    base = new_code if field == "base" else user.base_currency
    default = new_code if field == "default" else user.default_currency

    try:
        updated = await registry.update_settings(tg_user.id, base, default)
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    await update.message.reply_text(
        f"Updated!\nBase: *{updated.base_currency}* | Default: *{updated.default_currency}*",
        parse_mode="Markdown",
    )


# ── /last ────────────────────────────────────────────────────────────────────

async def last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/last [N] — show the last N transactions (default 10)."""
    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    args = context.args or []
    try:
        n = int(args[0]) if args else 10
        n = max(1, min(n, 50))
    except ValueError:
        n = 10

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
        return

    records = sheets.get_last_n_transactions(user.spreadsheet_id, n)
    if not records:
        await update.message.reply_text("No transactions yet.")
        return

    lines = [f"Last {len(records)} transactions:"]
    for i, r in enumerate(records, 1):
        ts = r.timestamp.strftime("%d %b %H:%M")
        lines.append(
            f"{i}. {ts} — {r.amount_local:,.2f} {r.local_currency} "
            f"[{category_label(r.category)}] {r.description}"
        )

    await update.message.reply_text("\n".join(lines))


# ── /undo ────────────────────────────────────────────────────────────────────

async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/undo — delete the most recent transaction."""
    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
        return

    deleted = sheets.delete_last_transaction(user.spreadsheet_id)
    if deleted is None:
        await update.message.reply_text("No transactions to undo.")
        return

    await update.message.reply_text(
        f"Deleted: {deleted.amount_local:,.2f} {deleted.local_currency} "
        f"— {category_label(deleted.category)} — {deleted.description}"
    )


# ── /cat ─────────────────────────────────────────────────────────────────────

async def cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cat <category> — show this month's spending for a specific category."""
    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
        return

    categories = sheets.get_categories(user.spreadsheet_id)
    args = context.args or []
    if not args:
        slugs = ", ".join(c.slug for c in categories)
        await update.message.reply_text(f"Usage: /cat <category>\nCategories: {slugs}")
        return

    cat_slug = args[0].lower()
    if not any(c.slug == cat_slug for c in categories):
        await update.message.reply_text(f"Unknown category: {cat_slug}")
        return

    today_date = date.today()
    start_of_month = today_date.replace(day=1)
    records = sheets.get_transactions(user.spreadsheet_id, since=start_of_month)
    cat_records = [r for r in records if r.category == cat_slug]

    if not cat_records:
        await update.message.reply_text(
            f"No {category_label(cat_slug)} expenses this month."
        )
        return

    total = sum(r.amount_base for r in cat_records)
    lines = [
        f"{category_label(cat_slug)} — {today_date.strftime('%B')}: "
        f"{total:,.2f} {user.base_currency} ({len(cat_records)} transactions)\n"
    ]
    for r in cat_records[:20]:  # cap to avoid overly long messages
        ts = r.timestamp.strftime("%d %b")
        lines.append(f"  {ts}  {r.amount_local:,.2f} {r.local_currency}  {r.description}")

    await update.message.reply_text("\n".join(lines))


# ── /export ──────────────────────────────────────────────────────────────────

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/export [YYYY-MM] — export transactions as a CSV file.

    Defaults to the current month when no period is specified.
    """
    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
        return

    args = context.args or []
    today_date = date.today()

    if args:
        try:
            period = datetime.strptime(args[0], "%Y-%m").date()
            since = period.replace(day=1)
            # Last day of month
            next_month = (since.replace(day=28) + timedelta(days=4)).replace(day=1)
            until = next_month - timedelta(days=1)
        except ValueError:
            await update.message.reply_text("Usage: /export [YYYY-MM]\nExample: /export 2024-03")
            return
    else:
        since = today_date.replace(day=1)
        until = today_date

    records = sheets.get_transactions(user.spreadsheet_id, since=since, until=until)
    if not records:
        await update.message.reply_text(
            f"No transactions between {since} and {until}."
        )
        return

    # Build CSV in memory
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "amount", "currency", "amount_base", "base_currency",
                     "fx_rate", "category", "subcategory", "description", "source"])
    for r in records:
        writer.writerow([
            r.timestamp.strftime("%Y-%m-%d %H:%M"),
            r.amount_local,
            r.local_currency,
            r.amount_base,
            user.base_currency,
            r.fx_rate,
            r.category,
            r.subcategory,
            r.description,
            r.source.value,
        ])

    csv_bytes = buf.getvalue().encode("utf-8")
    filename = f"expenses_{since}_{until}.csv"

    await update.message.reply_document(
        document=io.BytesIO(csv_bytes),
        filename=filename,
        caption=f"Expenses {since} → {until} ({len(records)} rows)",
    )


# ── /broadcast ────────────────────────────────────────────────────────────

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/broadcast <message> — send a message to all active users (admin only)."""
    from services.user_registry import UserRegistry
    from models.expense import UserRole

    registry: UserRegistry = context.bot_data["registry"]
    sender = await registry.get_user(update.effective_user.id)

    if not sender or sender.role != UserRole.admin:
        await update.message.reply_text("This command is only available to admins.")
        return

    text = update.message.text
    prefix = "/broadcast"
    message_body = text[len(prefix):].strip() if text.startswith(prefix) else ""

    if not message_body:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    users = await registry.get_all_active_users()
    sent, failed, blocked = 0, 0, 0

    for user in users:
        try:
            await context.bot.send_message(chat_id=user.telegram_id, text=message_body)
            sent += 1
        except Forbidden:
            blocked += 1
        except TelegramError as exc:
            logger.warning("Failed to send broadcast to %s: %s", user.telegram_id, exc)
            failed += 1
        await asyncio.sleep(0.05)  # ~20 msg/s, well within Telegram's rate limit

    report = f"Broadcast complete.\nSent: {sent}"
    if blocked:
        report += f"\nBlocked bot: {blocked}"
    if failed:
        report += f"\nFailed: {failed}"
    await update.message.reply_text(report)
