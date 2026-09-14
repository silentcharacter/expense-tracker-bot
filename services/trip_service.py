"""Shared trip helpers used by both the bot handlers and the Mini App API."""

import logging
from datetime import date
from typing import Optional

from models.expense import ExpenseRecord, User
from models.trip import Trip

logger = logging.getLogger(__name__)


def resolve_active_trip(storage, user: User, today: Optional[date] = None) -> Optional[Trip]:
    """Return the trip new expenses should be tagged with, or None.

    Self-heals the pointer: if the referenced trip is gone or its end date has
    passed (the user closed it in the Mini App, or simply forgot to end it), the
    marker is cleared so expenses stop silently landing in a finished trip.
    """
    trip_id = (user.active_trip_id or "").strip()
    if not trip_id:
        return None

    try:
        trip = storage.get_trip(user.spreadsheet_id, trip_id)
    except Exception as exc:
        logger.warning("Could not read active trip %s: %s", trip_id, exc)
        return None

    if trip is None or trip.is_over(today):
        _clear_active_trip(storage, user)
        return None
    return trip


def _clear_active_trip(storage, user: User) -> None:
    """Best-effort reset of a stale active-trip pointer."""
    try:
        storage.set_active_trip(user.telegram_id, "")
        user.active_trip_id = ""
    except Exception as exc:
        logger.warning("Could not clear stale active trip for %s: %s", user.telegram_id, exc)


def active_trip_id(storage, user: User, today: Optional[date] = None) -> str:
    """Trip id to stamp on a new expense — empty string when not travelling."""
    trip = resolve_active_trip(storage, user, today)
    return trip.id if trip else ""


def trip_totals(
    trip: Trip, records: list[ExpenseRecord], today: Optional[date] = None
) -> dict:
    """Aggregate a trip's expenses into the figures every surface shows.

    Args:
        trip:    The trip being summarised.
        records: Expenses already filtered down to this trip.
        today:   Override for "now" (tests).

    Returns:
        Dict with total/count/days/daily average and budget progress.
    """
    total_base = round(sum(r.amount_base for r in records), 4)
    days = max(trip.day_count(today), 1)
    budget = trip.budget

    return {
        "total_base": total_base,
        "transaction_count": len(records),
        "days": days,
        "total_days": trip.total_days(),
        "daily_average": round(total_base / days, 4),
        "budget": budget,
        "budget_remaining": round(budget - total_base, 4) if budget else None,
        "budget_percentage": round(total_base / budget * 100, 1) if budget else None,
    }
