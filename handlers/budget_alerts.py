"""Budget threshold alert: notify when spending crosses 80% or 100% of category budget."""

import logging
from datetime import date

from telegram import Bot

from models.expense import ExpenseRecord, User

logger = logging.getLogger(__name__)

_THRESHOLDS = [
    (0.80, "⚠️ *{label}* budget is 80% used — {spent:,.0f}/{budget:,.0f} {currency}"),
    (1.00, "🚨 *{label}* budget exceeded — {spent:,.0f}/{budget:,.0f} {currency}"),
]


async def check_and_send_budget_alert(
    bot: Bot,
    user: User,
    record: ExpenseRecord,
    sheets,
) -> None:
    """Send a Telegram alert if the new expense pushed a category past a budget threshold.

    Only fires when the threshold is newly crossed (spending was below before this expense).
    Silently ignores errors so the calling handler is never interrupted.
    """
    if not user.budget_alerts or not record.amount_base:
        return
    try:
        today = date.today()
        month_start = today.replace(day=1)
        transactions = sheets.get_transactions(user.spreadsheet_id, since=month_start, until=today)
        categories = sheets.get_categories(user.spreadsheet_id)

        cat_obj = next((c for c in categories if c.slug == record.category), None)
        if cat_obj is None:
            return

        # Effective budget: category-level value, or sum of subcategory budgets
        if cat_obj.budget:
            budget = cat_obj.budget
        else:
            budget = sum(s.budget or 0.0 for s in cat_obj.subcategories)
        if budget <= 0:
            return

        spent_now = sum(t.amount_base for t in transactions if t.category == record.category)
        spent_before = spent_now - record.amount_base

        for threshold, template in _THRESHOLDS:
            if spent_before / budget < threshold <= spent_now / budget:
                msg = template.format(
                    label=cat_obj.label,
                    spent=spent_now,
                    budget=budget,
                    currency=user.base_currency,
                )
                await bot.send_message(chat_id=user.telegram_id, text=msg, parse_mode="Markdown")
    except Exception:
        logger.exception("Budget alert check failed for user %s", user.telegram_id)
