"""Shared "convert → save → budget alert → confirmation card" flow.

Used by text, voice and quick-expense input so the three stay identical.
"""

import logging
from contextlib import nullcontext
from typing import Optional

from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes

from handlers.callbacks import _format_confirmation, saved_keyboard
from models.category import category_label, subcategory_label
from models.expense import ExpenseRecord, ExpenseSource, User
from services.trip_service import resolve_active_trip

logger = logging.getLogger(__name__)


async def save_expense(
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
    *,
    amount: float,
    currency: str,
    category: str,
    subcategory: str,
    description: str,
    source: ExpenseSource,
    raw_input: str = "",
    tracer: Optional[object] = None,
) -> tuple[ExpenseRecord, str, InlineKeyboardMarkup]:
    """Convert, store and announce one expense.

    Returns the saved record plus the confirmation text (Markdown v1) and its
    inline keyboard; the caller decides whether to send a new message or edit
    a "Parsing…" placeholder.
    """
    from handlers.budget_alerts import check_and_send_budget_alert

    currency_svc = context.bot_data["currency"]
    storage = context.bot_data["sheets"]

    def step(name: str):
        return tracer.step(name) if tracer is not None else nullcontext()

    try:
        with step("currency_convert"):
            amount_base, fx_rate = await currency_svc.convert(amount, currency, user.base_currency)
    except Exception as exc:
        logger.exception("Currency conversion failed %s→%s: %s", currency, user.base_currency, exc)
        amount_base = amount
        fx_rate = 1.0

    with step("active_trip_lookup"):
        trip = resolve_active_trip(storage, user)

    record = ExpenseRecord(
        trip_id=trip.id if trip else "",
        amount_local=amount,
        local_currency=currency,
        amount_base=amount_base,
        base_currency=user.base_currency,
        fx_rate=fx_rate,
        category=category,
        subcategory=subcategory,
        description=description,
        source=source,
        raw_input=raw_input,
    )
    with step("sheets_write"):
        storage.append_transaction(user.spreadsheet_id, record)
    context.user_data["last_expense"] = {"record": record}

    await check_and_send_budget_alert(context.bot, user, record, storage)

    text, keyboard = render_card(record, user, trip.label() if trip else "")
    return record, text, keyboard


def render_card(
    record: ExpenseRecord, user: User, trip_label: str = "", status: str = ""
) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation card text (Markdown v1) and its inline keyboard for one expense."""
    cat_label = category_label(record.category)
    sub_label = subcategory_label(record.category, record.subcategory) if record.subcategory else ""
    cat_display = f"{cat_label} / {sub_label}" if sub_label else cat_label

    if not status:
        status = f"✓ Saved to {trip_label}" if trip_label else "✓ Saved"
    text = f"{_format_confirmation(record, user.base_currency, cat_display)}\n\n{status}"
    keyboard = saved_keyboard(
        record.id,
        in_trip=bool(record.trip_id),
        can_add_quick=record.source != ExpenseSource.quick,
    )
    return text, keyboard


async def update_expense_amount(
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
    record_id: str,
    amount: float,
    currency: Optional[str] = None,
) -> Optional[ExpenseRecord]:
    """Change an expense's amount (and optionally currency), re-converting to base.

    Returns the updated record, or None if it no longer exists.

    Raises:
        NotImplementedError: On a storage backend that cannot update records.
    """
    from handlers.budget_alerts import check_and_send_budget_alert

    storage = context.bot_data["sheets"]
    if not hasattr(storage, "update_transaction"):
        raise NotImplementedError("Editing amounts requires STORAGE_BACKEND=firestore")

    current = storage.get_transaction(user.spreadsheet_id, record_id)
    if current is None:
        return None

    currency = (currency or current.local_currency).upper()
    try:
        amount_base, fx_rate = await context.bot_data["currency"].convert(
            amount, currency, user.base_currency
        )
    except Exception as exc:
        logger.exception("Currency conversion failed %s→%s: %s", currency, user.base_currency, exc)
        if currency == current.local_currency:
            # Keep the rate the expense was recorded with.
            fx_rate = current.fx_rate
            amount_base = round(amount * fx_rate, 4)
        else:
            amount_base, fx_rate = amount, 1.0

    updated = storage.update_transaction(
        user.spreadsheet_id,
        record_id,
        {
            "amount_local": amount,
            "local_currency": currency,
            "amount_base": amount_base,
            "fx_rate": fx_rate,
        },
    )
    if updated is None:
        return None

    last = context.user_data.get("last_expense", {})
    if last.get("record") is not None and last["record"].id == record_id:
        context.user_data["last_expense"] = {"record": updated}

    # The alert treats record.amount_base as "what was just added": pass only the increase.
    increase = round(updated.amount_base - current.amount_base, 4)
    if increase > 0:
        await check_and_send_budget_alert(
            context.bot, user, updated.model_copy(update={"amount_base": increase}), storage
        )
    return updated
