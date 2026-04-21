"""Weekly cron job: send a spending summary for the previous week to opted-in users."""

import asyncio
import calendar as _cal
import logging
import os
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from telegram import Bot
from telegram.error import Forbidden, TelegramError

from models.category import category_label
from models.expense import ExpenseRecord, User
from services.sheets import SheetsService

logger = logging.getLogger(__name__)

_CATEGORY_EMOJI: dict[str, str] = {
    "food": "🍔",
    "transport": "🚌",
    "housing": "🏠",
    "health": "💊",
    "entertainment": "🎬",
    "shopping": "🛍",
    "education": "📚",
    "services": "🔧",
    "subscriptions": "📱",
    "travel": "✈️",
    "other": "📦",
}

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _week_dates(weeks_ago: int) -> tuple[date, date]:
    today = date.today()
    monday = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks_ago)
    return monday, monday + timedelta(days=6)


def _fmt(amount: float, currency: str) -> str:
    if amount >= 1000:
        return f"{amount:,.0f} {currency}"
    return f"{amount:.2f} {currency}"


def _mini_bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _esc(text: str) -> str:
    """Escape text for Telegram MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


def _build_message(
    user: User,
    week_records: list[ExpenseRecord],
    prev_records: list[ExpenseRecord],
    month_records: list[ExpenseRecord],
    budgets: dict[str, float],
    since: date,
    until: date,
) -> str:
    cur = user.base_currency
    total = sum(r.amount_base for r in week_records)
    prev_total = sum(r.amount_base for r in prev_records)
    count = len(week_records)
    daily_avg = total / 7

    # Date label "14–20 Apr" or "28 Mar–3 Apr"
    if since.month == until.month:
        date_label = f"{since.day}–{until.day} {_MONTHS[until.month - 1]}"
    else:
        date_label = f"{since.day} {_MONTHS[since.month - 1]}–{until.day} {_MONTHS[until.month - 1]}"

    # Week-over-week comparison
    if prev_total > 0:
        change_pct = (total - prev_total) / prev_total * 100
        arrow = "↑" if change_pct > 0 else "↓"
        change_part = f"  {arrow}{abs(change_pct):.0f}% vs last week"
    else:
        change_part = ""

    lines: list[str] = [
        f"📊 *Your week — {_esc(date_label)}*",
        "",
        f"Spent: *{_esc(_fmt(total, cur))}*{_esc(change_part)}",
        f"Transactions: {count}  ·  Daily avg: {_esc(_fmt(daily_avg, cur))}",
    ]

    # Top-3 categories
    cat_totals: dict[str, float] = defaultdict(float)
    for r in week_records:
        cat_totals[r.category] += r.amount_base

    top3 = sorted(cat_totals.items(), key=lambda x: -x[1])[:3]
    if top3:
        lines += ["", "*Top categories:*"]
        for slug, amt in top3:
            emoji = _CATEGORY_EMOJI.get(slug, "•")
            label = category_label(slug)
            pct = amt / total * 100 if total else 0
            bar = _mini_bar(pct)
            lines.append(
                f"{emoji} {_esc(label)}: {_esc(_fmt(amt, cur))}  "
                f"{_esc(f'{pct:.0f}%')}  {bar}"
            )

    # Month budget block (only if budgets are configured)
    budget_total = sum(budgets.values())
    if budget_total > 0:
        month_spent = sum(r.amount_base for r in month_records)
        today = date.today()
        days_remaining = _cal.monthrange(today.year, today.month)[1] - today.day
        pace_pct = month_spent / budget_total * 100
        status = "on track ✅" if pace_pct < 90 else "over budget ⚠️"
        lines += [
            "",
            f"💰 *Month budget:* {_esc(_fmt(month_spent, cur))} / {_esc(_fmt(budget_total, cur))}"
            f"  \\({days_remaining} days left\\)",
            f"   {_esc(f'{pace_pct:.0f}%')} used — {status}",
        ]

    # Biggest single expense of the week
    biggest = max(week_records, key=lambda r: r.amount_base)
    day_name = _DAYS[biggest.timestamp.weekday()]
    desc = (biggest.description or category_label(biggest.category)).strip()
    lines += [
        "",
        f"💸 Biggest: {_esc(desc)} — {_esc(_fmt(biggest.amount_base, cur))} \\({_esc(day_name)}\\)",
    ]

    return "\n".join(lines)


async def run_weekly_summary(
    sheets: Optional[SheetsService] = None,
    bot: Optional[Bot] = None,
) -> dict:
    """Send weekly spending summaries to all opted-in active users.

    Returns:
        ``{"sent": int, "skipped": int, "errors": int}``
    """
    sheets = sheets or SheetsService()

    summary = {"sent": 0, "skipped": 0, "errors": 0}

    try:
        users = sheets.get_all_active_users()
    except Exception as exc:
        logger.exception("Could not list active users: %s", exc)
        summary["errors"] += 1
        return summary

    since, until = _week_dates(weeks_ago=1)
    prev_since, prev_until = _week_dates(weeks_ago=2)

    async with (bot or Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])) as tg_bot:
        for user in users:
            if not user.weekly_summary:
                summary["skipped"] += 1
                continue

            try:
                week_records = sheets.get_transactions(
                    user.spreadsheet_id, since=since, until=until
                )

                if not week_records:
                    summary["skipped"] += 1
                    continue

                prev_records = sheets.get_transactions(
                    user.spreadsheet_id, since=prev_since, until=prev_until
                )

                today = date.today()
                month_records = sheets.get_transactions(
                    user.spreadsheet_id, since=today.replace(day=1), until=today
                )

                budgets = sheets.get_budgets(user.spreadsheet_id)

                msg = _build_message(
                    user, week_records, prev_records, month_records, budgets, since, until
                )
                await tg_bot.send_message(
                    chat_id=user.telegram_id, text=msg, parse_mode="MarkdownV2"
                )
                summary["sent"] += 1
                logger.info("Weekly summary sent to user %s", user.telegram_id)

            except Forbidden:
                logger.warning("User %s has blocked the bot — skipping", user.telegram_id)
                summary["skipped"] += 1
            except TelegramError as exc:
                logger.warning("Telegram error for user %s: %s", user.telegram_id, exc)
                summary["errors"] += 1
            except Exception as exc:
                logger.exception(
                    "Weekly summary failed for user %s: %s", user.telegram_id, exc
                )
                summary["errors"] += 1

            await asyncio.sleep(0.05)

    logger.info("Weekly summary cron complete: %s", summary)
    return summary
