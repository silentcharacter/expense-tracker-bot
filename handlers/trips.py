"""/trip command and the trip-related inline callbacks.

A trip is a named date range that new expenses are tagged with while it is
active. Creating one takes a single message — ``/trip Georgia`` — because the
moment you need it you are usually standing in an airport, not browsing a form.
"""

import logging
from datetime import date
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from handlers.callbacks import (
    CB_TRIP_END,
    CB_TRIP_LIST,
    CB_TRIP_PICK_FOR_RECORD,
    CB_TRIP_RESUME,
    CB_TRIP_SET_ON_RECORD,
    CB_TRIP_START,
)
from models.expense import ExpenseRecord, User
from models.trip import Trip
from services.trip_service import resolve_active_trip, trip_totals

logger = logging.getLogger(__name__)

# user_data key: set while the bot waits for a trip name typed in chat.
AWAITING_TRIP_NAME = "trip_name"

# Callback payload meaning "detach this expense from every trip".
NO_TRIP = "-"

# Keep inline keyboards short; the Mini App is the place for long lists.
_MAX_PICKER_TRIPS = 6
_MAX_RESUME_TRIPS = 4

_UNSUPPORTED = (
    "Trips need the Firestore storage backend. "
    "Set STORAGE_BACKEND=firestore to use them."
)


def _esc(text: str) -> str:
    """Escape user-supplied text for Markdown v1."""
    return escape_markdown(str(text))


def _money(amount: float, currency: str) -> str:
    return f"{amount:,.2f} {currency}"


# ── /trip ────────────────────────────────────────────────────────────────────


async def trip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/trip — trip status, ``/trip <name>`` — start one, ``/trip end`` — finish it.

    Without arguments it shows the active trip (or offers to start one) with
    inline buttons, so the command is discoverable without reading help text.
    """
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    sheets = context.bot_data["sheets"]

    user = await registry.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("You are not registered yet. Send /start to sign up.")
        return

    arg = " ".join(context.args).strip() if context.args else ""
    lowered = arg.lower()

    try:
        if lowered in ("end", "stop", "finish"):
            text, markup = _end_active_trip(sheets, user)
        elif lowered in ("list", "all"):
            text, markup = _trips_list(sheets, user)
        elif arg:
            text, markup = _start_trip(sheets, user, arg)
        else:
            text, markup = _trip_status(sheets, user)
    except NotImplementedError:
        await update.message.reply_text(_UNSUPPORTED)
        return
    except Exception as exc:
        logger.exception("/trip failed for user %s: %s", user.telegram_id, exc)
        await update.message.reply_text("Could not load your trips. Please try again.")
        return

    await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")


# ── Message builders ─────────────────────────────────────────────────────────


def _start_trip(sheets, user: User, name: str) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    """Create a trip starting today and make it the active one."""
    previous = resolve_active_trip(sheets, user)
    if previous is not None:
        sheets.update_trip(user.spreadsheet_id, previous.id, {"end_date": date.today().isoformat()})

    trip = Trip(name=name, start_date=date.today())
    sheets.add_trip(user.spreadsheet_id, trip)
    sheets.set_active_trip(user.telegram_id, trip.id)
    user.active_trip_id = trip.id

    lines = []
    if previous is not None:
        lines.append(f"Finished {_esc(previous.label())}.")
    lines.append(f"🧳 *{_esc(trip.name)}* started {trip.start_date.strftime('%d %b')}.")
    lines.append("")
    lines.append("Every expense you add now is tagged with this trip.")
    lines.append("Send /trip end when you are back home.")
    return "\n".join(lines), _status_keyboard(active=True)


def _end_active_trip(sheets, user: User) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    """Close the active trip and report its totals."""
    trip = resolve_active_trip(sheets, user)
    if trip is None:
        return "You have no active trip.", _status_keyboard(active=False)

    today = date.today()
    sheets.update_trip(user.spreadsheet_id, trip.id, {"end_date": today.isoformat()})
    sheets.set_active_trip(user.telegram_id, "")
    user.active_trip_id = ""

    records = sheets.get_transactions(user.spreadsheet_id, trip_id=trip.id)
    closed = trip.model_copy(update={"end_date": today})
    stats = trip_totals(closed, records, today)

    lines = [
        f"🧳 *{_esc(trip.name)}* finished.",
        "",
        f"{closed.start_date.strftime('%d %b')} – {today.strftime('%d %b %Y')} "
        f"({stats['days']} days)",
        f"Total: *{_money(stats['total_base'], user.base_currency)}* "
        f"({stats['transaction_count']} expenses)",
        f"Average: {_money(stats['daily_average'], user.base_currency)}/day",
    ]
    if stats["budget"]:
        lines.append(
            f"Budget: {_money(stats['budget'], user.base_currency)} "
            f"· {stats['budget_percentage']:.0f}% used"
        )
    lines.append("")
    lines.append("New expenses are no longer tagged with a trip.")
    return "\n".join(lines), _status_keyboard(active=False)


def _trip_status(sheets, user: User) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    """Status card for the active trip, or an invitation to start one."""
    trip = resolve_active_trip(sheets, user)
    if trip is None:
        trips = sheets.get_trips(user.spreadsheet_id)
        lines = [
            "No active trip — expenses are recorded as usual.",
            "",
            "Start one with `/trip Georgia`, or reopen a previous trip below.",
        ]
        return "\n".join(lines), _status_keyboard(active=False, resumable=trips)

    records = sheets.get_transactions(user.spreadsheet_id, trip_id=trip.id)
    stats = trip_totals(trip, records)

    day_line = f"Day {stats['days']}"
    if stats["total_days"]:
        day_line += f" of {stats['total_days']}"
    day_line += f" · since {trip.start_date.strftime('%d %b')}"

    lines = [
        f"🧳 *{_esc(trip.name)}*",
        day_line,
        "",
        f"Spent: *{_money(stats['total_base'], user.base_currency)}* "
        f"({stats['transaction_count']} expenses)",
        f"Average: {_money(stats['daily_average'], user.base_currency)}/day",
    ]
    if stats["budget"]:
        remaining = stats["budget_remaining"]
        lines.append(
            f"Budget: {_money(stats['budget'], user.base_currency)} "
            f"· {stats['budget_percentage']:.0f}% used"
        )
        lines.append(
            f"Left: {_money(remaining, user.base_currency)}"
            if remaining >= 0
            else f"Over by: {_money(abs(remaining), user.base_currency)}"
        )
    return "\n".join(lines), _status_keyboard(active=True)


def _trips_list(sheets, user: User) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    """All trips with their totals, newest first."""
    trips = sheets.get_trips(user.spreadsheet_id)
    if not trips:
        return (
            "No trips yet. Start one with `/trip Georgia`.",
            _status_keyboard(active=False),
        )

    # One read, grouped in memory — a per-trip query would be N round-trips.
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for r in sheets.get_transactions(user.spreadsheet_id):
        if r.trip_id:
            totals[r.trip_id] = totals.get(r.trip_id, 0.0) + r.amount_base
            counts[r.trip_id] = counts.get(r.trip_id, 0) + 1

    active_id = (user.active_trip_id or "").strip()
    lines = ["*Your trips*", ""]
    for trip in trips:
        span = trip.start_date.strftime("%d %b %Y")
        if trip.end_date:
            span += f" – {trip.end_date.strftime('%d %b %Y')}"
        else:
            span += " – now"
        marker = " ← active" if trip.id == active_id else ""
        lines.append(f"{trip.emoji} *{_esc(trip.name)}*{marker}")
        lines.append(
            f"   {span} · {_money(totals.get(trip.id, 0.0), user.base_currency)}"
            f" · {counts.get(trip.id, 0)} expenses"
        )
    return "\n".join(lines), _status_keyboard(active=bool(active_id), resumable=trips)


# ── Keyboards ────────────────────────────────────────────────────────────────


def _status_keyboard(
    active: bool, resumable: Optional[list[Trip]] = None
) -> InlineKeyboardMarkup:
    """Buttons under a trip status message."""
    rows: list[list[InlineKeyboardButton]] = []
    if active:
        rows.append([
            InlineKeyboardButton("⏹ End trip", callback_data=CB_TRIP_END),
            InlineKeyboardButton("📋 All trips", callback_data=CB_TRIP_LIST),
        ])
    else:
        rows.append([
            InlineKeyboardButton("▶️ Start a trip", callback_data=CB_TRIP_START),
            InlineKeyboardButton("📋 All trips", callback_data=CB_TRIP_LIST),
        ])
        for trip in (resumable or [])[:_MAX_RESUME_TRIPS]:
            rows.append([
                InlineKeyboardButton(
                    f"↻ Resume {trip.name}"[:40],
                    callback_data=f"{CB_TRIP_RESUME}:{trip.id}",
                )
            ])
    return InlineKeyboardMarkup(rows)


def trip_picker_keyboard(
    record_id: str, trips: list[Trip], current_trip_id: str
) -> InlineKeyboardMarkup:
    """Keyboard for attaching one expense to a trip (or detaching it)."""
    rows: list[list[InlineKeyboardButton]] = []
    for trip in trips[:_MAX_PICKER_TRIPS]:
        mark = "✓ " if trip.id == current_trip_id else ""
        rows.append([
            InlineKeyboardButton(
                f"{mark}{trip.emoji} {trip.name}"[:40],
                callback_data=f"{CB_TRIP_SET_ON_RECORD}:{record_id}:{trip.id}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            ("✓ " if not current_trip_id else "") + "— No trip —",
            callback_data=f"{CB_TRIP_SET_ON_RECORD}:{record_id}:{NO_TRIP}",
        )
    ])
    return InlineKeyboardMarkup(rows)


# ── Callback handlers ────────────────────────────────────────────────────────


def callback_handlers() -> dict:
    """Map callback-data prefixes to handlers, for handlers/callbacks.py."""
    return {
        CB_TRIP_START: _cb_start,
        CB_TRIP_END: _cb_end,
        CB_TRIP_LIST: _cb_list,
        CB_TRIP_RESUME: _cb_resume,
        CB_TRIP_PICK_FOR_RECORD: _cb_pick_for_record,
        CB_TRIP_SET_ON_RECORD: _cb_set_on_record,
    }


async def _current_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    return await registry.get_user(update.effective_user.id)


async def _cb_start(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Ask for a trip name; handlers/text.py picks the answer up."""
    context.user_data["awaiting"] = AWAITING_TRIP_NAME
    await update.callback_query.edit_message_text(
        "What should the trip be called? Send me a name, for example: Georgia"
    )


async def _cb_end(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    query = update.callback_query
    user = await _current_user(update, context)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start.")
        return
    try:
        text, markup = _end_active_trip(context.bot_data["sheets"], user)
    except NotImplementedError:
        await query.edit_message_text(_UNSUPPORTED)
        return
    await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")


async def _cb_list(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    query = update.callback_query
    user = await _current_user(update, context)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start.")
        return
    try:
        text, markup = _trips_list(context.bot_data["sheets"], user)
    except NotImplementedError:
        await query.edit_message_text(_UNSUPPORTED)
        return
    await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")


async def _cb_resume(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Reopen a finished trip and make it active again."""
    query = update.callback_query
    trip_id = parts[1] if len(parts) > 1 else ""
    user = await _current_user(update, context)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start.")
        return

    sheets = context.bot_data["sheets"]
    try:
        trip = sheets.get_trip(user.spreadsheet_id, trip_id)
        if trip is None:
            await query.edit_message_text("That trip no longer exists.")
            return
        # Resuming means "I am on this trip again", so the old end date goes away.
        if trip.end_date is not None:
            sheets.update_trip(user.spreadsheet_id, trip.id, {"end_date": ""})
        sheets.set_active_trip(user.telegram_id, trip.id)
        user.active_trip_id = trip.id
    except NotImplementedError:
        await query.edit_message_text(_UNSUPPORTED)
        return

    await query.edit_message_text(
        f"🧳 *{_esc(trip.name)}* is active again.\nNew expenses are tagged with it.",
        reply_markup=_status_keyboard(active=True),
        parse_mode="Markdown",
    )


async def _cb_pick_for_record(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Show the trip picker for one saved expense."""
    query = update.callback_query
    record_id = parts[1] if len(parts) > 1 else ""
    user = await _current_user(update, context)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start.")
        return

    try:
        trips = context.bot_data["sheets"].get_trips(user.spreadsheet_id)
    except NotImplementedError:
        await query.edit_message_text(_UNSUPPORTED)
        return

    if not trips:
        await query.edit_message_text(
            "You have no trips yet. Start one with `/trip Georgia`, "
            "then you can move expenses into it.",
            parse_mode="Markdown",
        )
        return

    last = context.user_data.get("last_expense", {})
    record: Optional[ExpenseRecord] = last.get("record")
    current = record.trip_id if record and record.id == record_id else ""
    await query.edit_message_text(
        "Which trip does this expense belong to?",
        reply_markup=trip_picker_keyboard(record_id, trips, current),
    )


async def _cb_set_on_record(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Attach the expense to the chosen trip (or detach it) and redraw the card."""
    from handlers.callbacks import _format_confirmation, saved_keyboard
    from models.category import category_label, subcategory_label

    query = update.callback_query
    if len(parts) < 3:
        await query.edit_message_text("Invalid action.")
        return

    record_id, raw_trip_id = parts[1], parts[2]
    trip_id = "" if raw_trip_id == NO_TRIP else raw_trip_id

    user = await _current_user(update, context)
    if user is None:
        await query.edit_message_text("You are not registered. Send /start.")
        return

    sheets = context.bot_data["sheets"]
    try:
        ok = sheets.set_transaction_trip(user.spreadsheet_id, record_id, trip_id)
        trip = sheets.get_trip(user.spreadsheet_id, trip_id) if trip_id else None
    except NotImplementedError:
        await query.edit_message_text(_UNSUPPORTED)
        return

    if not ok:
        await query.edit_message_text(
            "Could not update the expense. It may have been removed."
        )
        return

    status = f"✓ Saved to {trip.label()}" if trip else "✓ Saved (no trip)"

    last = context.user_data.get("last_expense", {})
    record: Optional[ExpenseRecord] = last.get("record")
    if record and record.id == record_id:
        record = record.model_copy(update={"trip_id": trip_id})
        context.user_data["last_expense"] = {"record": record}

        cat = category_label(record.category)
        sub = subcategory_label(record.category, record.subcategory) if record.subcategory else ""
        cat_display = f"{cat} / {sub}" if sub else cat
        await query.edit_message_text(
            f"{_format_confirmation(record, user.base_currency, cat_display)}\n\n{status}",
            reply_markup=saved_keyboard(record_id, in_trip=bool(trip_id)),
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            status, reply_markup=saved_keyboard(record_id, in_trip=bool(trip_id))
        )


# ── Free-text trip name (called from handlers/text.py) ───────────────────────


async def handle_trip_name_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, name: str
) -> None:
    """Finish the "Start a trip" button flow with the name typed in chat."""
    user = await _current_user(update, context)
    if user is None:
        await update.message.reply_text("You are not registered. Send /start first.")
        return

    name = name.strip()
    if not name:
        await update.message.reply_text("A trip needs a name. Try again, e.g. Georgia")
        context.user_data["awaiting"] = AWAITING_TRIP_NAME
        return

    try:
        text, markup = _start_trip(context.bot_data["sheets"], user, name)
    except NotImplementedError:
        await update.message.reply_text(_UNSUPPORTED)
        return
    except Exception as exc:
        logger.exception("Could not start trip for user %s: %s", user.telegram_id, exc)
        await update.message.reply_text("Could not start the trip. Please try again.")
        return

    await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
