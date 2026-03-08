"""Command handlers: /start, /email, /settings, /today, /week, /month,
/last, /undo, /budget, /export, /cat.
"""

import csv
import io
import logging
import os
from datetime import date, timedelta, datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from models.category import category_label, CATEGORIES
from handlers.callbacks import currency_keyboard, CB_ONBOARD_BASE, CB_SETTINGS_BASE, CB_SETTINGS_DEFAULT

logger = logging.getLogger(__name__)

_TIMEZONE = os.environ.get("TIMEZONE", "Asia/Bangkok")


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
    """/email <address> — share and transfer the Spreadsheet to the user's Google account."""
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    tg_user = update.effective_user

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /email your@gmail.com\n"
            "Your Spreadsheet will be shared and transferred to that Google account."
        )
        return

    google_email = args[0].strip()
    user = await registry.get_user(tg_user.id)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
        return

    await update.message.reply_text("Sharing your Spreadsheet…")
    try:
        await registry.transfer_to_user(tg_user.id, google_email)
    except Exception as exc:
        logger.error("Failed to transfer spreadsheet for %s: %s", tg_user.id, exc)
        await update.message.reply_text(f"Error: {exc}")
        return

    await update.message.reply_text(
        f"Done! Your Spreadsheet has been shared with *{google_email}*.\n"
        f"You can now find it in Google Drive.",
        parse_mode="Markdown",
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
                        callback_data=f"show_settings_base",
                    ),
                    InlineKeyboardButton(
                        f"Change default ({user.default_currency})",
                        callback_data=f"show_settings_default",
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


# ── /today ───────────────────────────────────────────────────────────────────

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/today — show total and breakdown of today's expenses."""
    await _period_summary(update, context, days=0, label="Today")


# ── /week ────────────────────────────────────────────────────────────────────

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/week — show this week's expense summary."""
    await _period_summary(update, context, days=6, label="This week")


# ── /month ───────────────────────────────────────────────────────────────────

async def month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/month — show this month's expense summary grouped by category."""
    today_date = date.today()
    start_of_month = today_date.replace(day=1)
    await _period_summary(
        update, context, since=start_of_month, label="This month"
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


# ── /budget ──────────────────────────────────────────────────────────────────

async def budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/budget — show current month's spending vs configured category budgets."""
    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
        return

    today_date = date.today()
    start_of_month = today_date.replace(day=1)
    records = sheets.get_transactions(user.spreadsheet_id, since=start_of_month)
    budgets = sheets.get_budgets(user.spreadsheet_id)

    if not budgets:
        await update.message.reply_text(
            "No budgets configured.\n"
            "Open your Spreadsheet → Categories sheet and add budget amounts."
        )
        return

    # Aggregate spending per category
    spent: dict[str, float] = {}
    for r in records:
        spent[r.category] = spent.get(r.category, 0.0) + r.amount_base

    lines = [f"Budget — {today_date.strftime('%B %Y')} ({user.base_currency}):\n"]
    for cat_slug, limit in sorted(budgets.items()):
        used = spent.get(cat_slug, 0.0)
        pct = (used / limit * 100) if limit else 0
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        over = " ⚠ OVER BUDGET" if used > limit else ""
        lines.append(
            f"{category_label(cat_slug)}: {used:,.2f}/{limit:,.2f} ({pct:.0f}%) {bar}{over}"
        )

    await update.message.reply_text("\n".join(lines))


# ── /cat ─────────────────────────────────────────────────────────────────────

async def cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cat <category> — show this month's spending for a specific category."""
    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    args = context.args or []
    if not args:
        slugs = ", ".join(c.slug for c in CATEGORIES)
        await update.message.reply_text(f"Usage: /cat <category>\nCategories: {slugs}")
        return

    cat_slug = args[0].lower()
    if not any(c.slug == cat_slug for c in CATEGORIES):
        await update.message.reply_text(f"Unknown category: {cat_slug}")
        return

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
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


# ── Shared period summary helper ─────────────────────────────────────────────

async def _period_summary(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    label: str,
    days: Optional[int] = None,
    since: Optional[date] = None,
) -> None:
    """Compute and send a totals + per-category breakdown for a date range.

    Args:
        update:  Telegram Update.
        context: PTB context.
        label:   Header label for the reply (e.g. "This week").
        days:    Number of days back from today (0 = today only). Mutually
                 exclusive with `since`.
        since:   Explicit start date. Mutually exclusive with `days`.
    """
    from services.sheets import SheetsService
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets: SheetsService = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
        return

    today_date = date.today()
    if since is None:
        since = today_date - timedelta(days=days or 0)

    records = sheets.get_transactions(user.spreadsheet_id, since=since, until=today_date)

    if not records:
        await update.message.reply_text(f"{label}: no expenses.")
        return

    total_base = sum(r.amount_base for r in records)

    # Group by category
    by_cat: dict[str, float] = {}
    for r in records:
        by_cat[r.category] = by_cat.get(r.category, 0.0) + r.amount_base

    top_cats = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)

    lines = [
        f"{label}: *{total_base:,.2f} {user.base_currency}* ({len(records)} transactions)\n"
    ]
    for cat_slug, amount in top_cats:
        pct = amount / total_base * 100
        lines.append(f"  {category_label(cat_slug)}: {amount:,.2f} ({pct:.0f}%)")

    if days and days > 0:
        daily_avg = total_base / (days + 1)
        lines.append(f"\nDaily avg: {daily_avg:,.2f} {user.base_currency}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
