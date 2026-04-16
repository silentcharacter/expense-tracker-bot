"""Daily cron job: materialise recurring expenses into each user's Transactions sheet.

The Recurring sheet stores templates only. Once per day this job iterates every
active user, finds the templates whose ``day_of_month`` matches today, and
appends a real ``ExpenseRecord`` (with ``recurring=True`` and the template id
stored in ``recurring_template_id``) to that user's Transactions sheet.

Idempotency: before inserting, we check whether a record already exists for the
same ``(recurring_template_id, year, month)``. Running the cron twice on the
same day is therefore a no-op.
"""

import logging
from datetime import date, datetime
from typing import Optional

from models.expense import ExpenseRecord, ExpenseSource, User
from services.currency import CurrencyService
from services.sheets import SheetsService

logger = logging.getLogger(__name__)


async def run_recurring_cron(
    sheets: Optional[SheetsService] = None,
    currency: Optional[CurrencyService] = None,
    today: Optional[date] = None,
) -> dict:
    """Materialise today's recurring expenses for every active user.

    Args:
        sheets:   Optional pre-built SheetsService (injected by tests).
        currency: Optional pre-built CurrencyService (injected by tests).
        today:    Override the "today" date (injected by tests).

    Returns:
        Summary dict: ``{"users": int, "inserted": int, "skipped": int, "errors": int}``.
    """
    sheets = sheets or SheetsService()
    currency = currency or CurrencyService()
    today = today or date.today()

    summary = {"users": 0, "inserted": 0, "skipped": 0, "errors": 0}

    try:
        users = sheets.get_all_active_users()
    except Exception as exc:
        logger.exception("Could not list active users: %s", exc)
        summary["errors"] += 1
        return summary

    for user in users:
        summary["users"] += 1
        try:
            inserted, skipped = await _process_user(sheets, currency, user, today)
            summary["inserted"] += inserted
            summary["skipped"] += skipped
        except Exception as exc:
            logger.exception("Recurring cron failed for user %s: %s", user.telegram_id, exc)
            summary["errors"] += 1

    logger.info("Recurring cron complete: %s", summary)
    return summary


async def _process_user(
    sheets: SheetsService,
    currency: CurrencyService,
    user: User,
    today: date,
) -> tuple[int, int]:
    """Process one user. Returns (inserted_count, skipped_count)."""
    items = sheets.get_recurring(user.spreadsheet_id)
    due = [it for it in items if int(it.get("day_of_month", 0) or 0) == today.day]
    if not due:
        return 0, 0

    # Pre-fetch this month's existing transactions for idempotency check.
    month_start = today.replace(day=1)
    existing = sheets.get_transactions(
        user.spreadsheet_id, since=month_start, until=today
    )
    existing_template_ids = {
        r.recurring_template_id
        for r in existing
        if r.recurring and r.recurring_template_id
    }

    inserted = 0
    skipped = 0
    for item in due:
        template_id = str(item.get("id", "")).strip()
        if not template_id:
            logger.warning("Skipping recurring item without id for user %s", user.telegram_id)
            continue
        if template_id in existing_template_ids:
            skipped += 1
            continue

        record = await _build_record(currency, user, item, today)
        if record is None:
            continue
        sheets.append_transaction(user.spreadsheet_id, record)
        inserted += 1
        logger.info(
            "Inserted recurring expense %s for user %s (template %s)",
            record.id, user.telegram_id, template_id,
        )

    return inserted, skipped


async def _build_record(
    currency: CurrencyService,
    user: User,
    item: dict,
    today: date,
) -> Optional[ExpenseRecord]:
    """Build an ExpenseRecord from a recurring template row.

    The template stores the amount in its local currency (``amount_local`` +
    ``local_currency``). The base-currency value is computed here via the FX
    service so it reflects the current rate when the expense is materialised.
    """
    local_currency = str(item.get("local_currency", "") or user.default_currency).upper()
    raw_amount_local = item.get("amount_local")
    if raw_amount_local in (None, ""):
        # Legacy rows without amount_local — fall back to the old amount column.
        raw_amount_local = item.get("amount")
    try:
        amount_local = float(raw_amount_local) if raw_amount_local not in (None, "") else 0.0
    except (TypeError, ValueError):
        logger.warning(
            "Recurring item %s has invalid amount_local: %r",
            item.get("id"), raw_amount_local,
        )
        return None
    if amount_local <= 0:
        return None

    base_currency = user.base_currency.upper()

    if local_currency == base_currency:
        fx_rate = 1.0
        amount_base = amount_local
    else:
        try:
            amount_base, fx_rate = await currency.convert(
                amount_local, local_currency, base_currency
            )
        except Exception as exc:
            logger.warning(
                "FX rate fetch failed for recurring item %s (%s→%s): %s — storing in local currency",
                item.get("id"), local_currency, base_currency, exc,
            )
            fx_rate = 1.0
            amount_base = amount_local
            local_currency = base_currency

    return ExpenseRecord(
        timestamp=datetime(today.year, today.month, today.day, 0, 0, 0),
        amount_local=amount_local,
        local_currency=local_currency,
        amount_base=amount_base,
        base_currency=base_currency,
        fx_rate=fx_rate,
        category=str(item.get("category", "") or "").lower(),
        subcategory=str(item.get("subcategory", "") or "").lower(),
        description=str(item.get("description", "") or "Recurring expense"),
        source=ExpenseSource.text,
        recurring=True,
        recurring_template_id=str(item.get("id", "")),
    )
