"""REST API for Telegram Mini App, served alongside the existing webhook."""

import csv
import hashlib
import io
import logging
import os
import re as _re
from collections import defaultdict

_CYRILLIC_MAP = str.maketrans({
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
    'е': 'e', 'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i',
    'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
    'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
})


def _slugify(label: str) -> str:
    s = label.lower().strip().translate(_CYRILLIC_MAP)
    s = s.replace(" ", "_")
    s = _re.sub(r"[^a-z0-9_]", "", s)
    s = _re.sub(r"_+", "_", s).strip("_")
    return s
from datetime import date, timedelta
from typing import Optional

import flask
from flask import jsonify

from models.expense import ExpenseRecord, User
from services.auth import validate_init_data
from services.currency import CurrencyService
from services.storage import get_storage
from services.user_registry import UserRegistry

logger = logging.getLogger(__name__)

# ── Lazy service singletons ─────────────────────────────────────────────────
# Re-using the same instances across Cloud Function warm invocations.

_registry_singleton: Optional[UserRegistry] = None
_currency_singleton: Optional[CurrencyService] = None


def _get_sheets():
    return get_storage()


def _get_registry() -> UserRegistry:
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = UserRegistry(sheets_service=get_storage())
    return _registry_singleton


def _get_currency() -> CurrencyService:
    global _currency_singleton
    if _currency_singleton is None:
        _currency_singleton = CurrencyService()
    return _currency_singleton


# ── Authentication ──────────────────────────────────────────────────────────


async def authenticate_mini_app(request: flask.Request) -> Optional[User]:
    """Validate 'Authorization: tma <initData>' header and return the User.

    Returns:
        User if auth is valid and user is registered, None otherwise.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("tma "):
        return None

    init_data = auth[4:]
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    user_dict = validate_init_data(init_data, bot_token)
    if not user_dict:
        return None

    telegram_id = user_dict.get("id")
    if not telegram_id:
        return None

    return await _get_registry().get_user(int(telegram_id))


# ── Entry point (called from main.py via asyncio.run) ───────────────────────


async def handle_api_request(request: flask.Request) -> tuple:
    """Authenticate and dispatch /api/* requests.

    Returns a tuple suitable for returning from the Cloud Function handler.
    """
    if request.method == "OPTIONS":
        return _cors_preflight_response()

    user = await authenticate_mini_app(request)
    if user is None:
        return jsonify({"error": "unauthorized"}), 401

    return await _dispatch(request, user)


def _cors_preflight_response() -> tuple:
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "3600",
    }
    return "", 204, headers


async def _dispatch(request: flask.Request, user: User) -> tuple:
    """Route to the appropriate handler based on path and HTTP method."""
    path = request.path.removeprefix("/api")
    method = request.method

    if path == "/summary" and method == "GET":
        return await _api_summary(request, user)
    elif path == "/expenses" and method == "GET":
        return await _api_expenses_list(request, user)
    elif path.startswith("/expenses/") and method == "DELETE":
        expense_id = path.split("/")[-1]
        return await _api_expense_delete(expense_id, user)
    elif path.startswith("/expenses/") and method == "PATCH":
        expense_id = path.split("/")[-1]
        return await _api_expense_update(request, expense_id, user)
    elif path == "/budgets" and method == "GET":
        return await _api_budgets_get(request, user)
    elif path == "/budgets" and method == "PUT":
        return await _api_budgets_update(request, user)
    elif path == "/settings" and method == "GET":
        return _api_settings_get(user)
    elif path == "/settings" and method == "PUT":
        return await _api_settings_update(request, user)
    elif path == "/expenses" and method == "DELETE":
        return await _api_expenses_clear(user)
    elif path == "/export" and method == "GET":
        return await _api_export(request, user)
    elif path == "/categories" and method == "GET":
        return _api_categories_get(user)
    elif path == "/categories" and method == "POST":
        return await _api_categories_create(request, user)
    elif path.startswith("/categories/") and path.endswith("/subcategories") and method == "POST":
        cat_slug = path.split("/")[2]
        return await _api_subcategory_create(request, user, cat_slug)
    elif path.startswith("/categories/") and "/subcategories/" in path and method == "DELETE":
        parts = path.split("/")  # ['', 'categories', cat_slug, 'subcategories', sub_slug]
        cat_slug, sub_slug = parts[2], parts[4]
        return await _api_subcategory_delete(user, cat_slug, sub_slug)
    elif path.startswith("/categories/") and method == "DELETE":
        cat_slug = path.split("/")[2]
        return await _api_category_delete(user, cat_slug)
    elif path == "/recurring" and method == "GET":
        return await _api_recurring_get(user)
    elif path == "/recurring" and method == "POST":
        return await _api_recurring_add(request, user)
    elif path.startswith("/recurring/") and path.endswith("/log") and method == "POST":
        entry_id = path[len("/recurring/"):-len("/log")]
        return await _api_recurring_log(user, entry_id)
    elif path.startswith("/recurring/") and method == "PUT":
        entry_id = path[len("/recurring/"):]
        return await _api_recurring_update(request, user, entry_id)
    elif path.startswith("/recurring/") and method == "DELETE":
        entry_id = path[len("/recurring/"):]
        return await _api_recurring_delete(user, entry_id)
    else:
        return jsonify({"error": "not found"}), 404


# ── Period helpers ──────────────────────────────────────────────────────────


def _period_dates(period: str, offset: int = 0) -> tuple[date, date]:
    """Return inclusive (since, until) dates for the named period.

    offset=0 → current period (until capped at today).
    offset=-1 → one period back (full range), offset=-2 → two periods back, etc.
    """
    import calendar as _cal

    today = date.today()

    if offset == 0:
        if period == "today":
            return today, today
        elif period == "week":
            return today - timedelta(days=today.weekday()), today
        elif period == "month":
            return today.replace(day=1), today
        elif period == "year":
            return today.replace(month=1, day=1), today
        else:
            raise ValueError(f"Unknown period {period!r}; must be today|week|month|year")

    # Past periods (offset < 0): return full period range
    n = abs(offset)
    if period == "today":
        anchor = today - timedelta(days=n)
        return anchor, anchor
    elif period == "week":
        monday = today - timedelta(days=today.weekday()) - timedelta(weeks=n)
        return monday, monday + timedelta(days=6)
    elif period == "month":
        # Go back n months
        month = today.month - n
        year = today.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        last_day = _cal.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)
    elif period == "year":
        y = today.year - n
        return date(y, 1, 1), date(y, 12, 31)
    else:
        raise ValueError(f"Unknown period {period!r}; must be today|week|month|year")


def _previous_period_dates(period: str, since: date, until: date) -> tuple[date, date]:
    """Return the full previous period for comparison.

    month — full previous calendar month (e.g. Apr → Mar 1–31).
    year  — full previous calendar year (e.g. 2026 → Jan 1–Dec 31 2025).
    week  — full previous week Mon–Sun.
    today — yesterday.
    """
    if period == "month":
        prev_month_last = since - timedelta(days=1)
        return prev_month_last.replace(day=1), prev_month_last
    if period == "year":
        return date(since.year - 1, 1, 1), date(since.year - 1, 12, 31)
    if period == "week":
        prev_since = since - timedelta(weeks=1)
        return prev_since, prev_since + timedelta(days=6)
    # today → yesterday
    yesterday = since - timedelta(days=1)
    return yesterday, yesterday


# ── Serialisation ───────────────────────────────────────────────────────────


def _amount_default(
    r: ExpenseRecord,
    default_currency: str,
    base_to_default_rate: float | None,
) -> float:
    """Return the amount in the user's default currency.

    Always converts the base-currency amount at the current FX rate, so every
    default-currency figure equals ``amount_base × current_rate`` and the totals
    reconcile by construction. When no live rate is available, falls back to the
    stored ``amount_local`` for same-currency rows, otherwise to ``amount_base``.
    """
    if base_to_default_rate:
        return round(r.amount_base * base_to_default_rate, 4)
    if r.local_currency.upper() == default_currency.upper():
        return r.amount_local
    return r.amount_base


def _record_to_dict(
    r: ExpenseRecord,
    default_currency: str | None = None,
    base_to_default_rate: float | None = None,
) -> dict:
    d = {
        "id": r.id,
        "timestamp": r.timestamp.isoformat(),
        "amount_local": r.amount_local,
        "local_currency": r.local_currency,
        "amount_base": r.amount_base,
        "base_currency": r.base_currency,
        "fx_rate": r.fx_rate,
        "category": r.category,
        "subcategory": r.subcategory,
        "description": r.description,
        "source": r.source.value,
        "is_recurring": bool(r.recurring),
    }
    if default_currency is not None:
        d["amount_default"] = _amount_default(r, default_currency, base_to_default_rate)
    return d


# ── Spending pace ───────────────────────────────────────────────────────────


async def _compute_spending_pace(
    sheets,
    user: User,
    records: list[ExpenseRecord],
    total_base: float,
    total_default: float,
    base_to_default_rate: float | None,
    since: date,
    until: date,
) -> dict | None:
    """Build the spending_pace block for the current-month summary.

    Splits spending into recurring (templates materialised by the cron) and
    discretionary (everything else). Projects discretionary forward from fully
    completed days only, so the current day does not make the morning forecast
    look artificially low. Recurring is excluded from the projection because it
    does not scale linearly with time.
    """
    import calendar as _cal

    today = date.today()
    days_in_month = _cal.monthrange(today.year, today.month)[1]
    completed_days = today.day - 1
    if completed_days == 0:
        return None
    days_remaining = max(days_in_month - completed_days, 0)

    # All default-currency figures are base × current_rate, so they reconcile
    # with total_default and with each other by construction.
    rate = base_to_default_rate if base_to_default_rate is not None else 1.0

    recurring_spent = round(sum(r.amount_base for r in records if r.recurring), 4)
    discretionary_spent = round(total_base - recurring_spent, 4)
    recurring_spent_default = round(recurring_spent * rate, 4)
    discretionary_spent_default = round(discretionary_spent * rate, 4)
    today_discretionary_spent = round(
        sum(
            r.amount_base
            for r in records
            if not r.recurring and r.timestamp.date() == today
        ),
        4,
    )
    completed_discretionary_spent = round(
        max(discretionary_spent - today_discretionary_spent, 0.0),
        4,
    )
    today_discretionary_spent_default = round(today_discretionary_spent * rate, 4)
    completed_discretionary_spent_default = round(
        max(discretionary_spent_default - today_discretionary_spent_default, 0.0),
        4,
    )

    # Recurring template total (base currency) for the month. Templates already
    # materialised this month contribute their recorded amount_base (locked at
    # the FX rate of the day they fired); the rest are converted at the current
    # rate. Otherwise mid-month FX moves would retroactively re-price expenses
    # that already happened. The default-currency figure is derived below by a
    # single live conversion so every default total equals base × current_rate.
    materialised_base_by_template = {
        r.recurring_template_id: r.amount_base
        for r in records
        if r.recurring and r.recurring_template_id
    }
    try:
        recurring_items = sheets.get_recurring(user.spreadsheet_id)
        recurring_total = await _recurring_base_total(
            recurring_items,
            user.base_currency,
            user.default_currency,
            materialised_base_by_template,
        )
    except Exception as exc:
        logger.warning("Could not read recurring sheet for pace calc: %s", exc)
        recurring_total = 0.0

    recurring_total_default = (
        round(recurring_total * base_to_default_rate, 4)
        if base_to_default_rate is not None
        else recurring_total
    )

    # Total budget = sum of effective category budgets (subcategory sums).
    try:
        budgets_map = sheets.get_budgets(user.spreadsheet_id)
        budget_total = round(sum(budgets_map.values()), 4)
    except Exception as exc:
        logger.warning("Could not read budgets for pace calc: %s", exc)
        budget_total = 0.0

    discretionary_budget = round(max(budget_total - recurring_total, 0.0), 4)
    # Every default-currency figure is base × current_rate, so the identity
    # budget_total = recurring_total + discretionary_budget holds automatically
    # in the default currency too.
    if base_to_default_rate is not None:
        budget_total_default = round(budget_total * base_to_default_rate, 4)
        discretionary_budget_default = round(
            discretionary_budget * base_to_default_rate, 4
        )
    else:
        budget_total_default = None
        discretionary_budget_default = None

    projected_discretionary = round(
        completed_discretionary_spent / completed_days * days_in_month, 4
    )
    projected_discretionary_default = round(
        completed_discretionary_spent_default / completed_days * days_in_month,
        4,
    )

    available_per_day = round(
        max(discretionary_budget - completed_discretionary_spent, 0.0)
        / max(days_remaining, 1),
        4,
    )
    available_per_day_default = (
        round(
            max(discretionary_budget_default - completed_discretionary_spent_default, 0.0)
            / max(days_remaining, 1),
            4,
        )
        if discretionary_budget_default is not None
        else None
    )

    if discretionary_budget > 0:
        status = "on_track" if projected_discretionary <= discretionary_budget * 1.1 else "over_pace"
    else:
        status = "on_track"

    return {
        "days_elapsed": completed_days,
        "days_in_month": days_in_month,
        "total_spent": round(total_base, 4),
        "recurring_spent": recurring_spent,
        "recurring_spent_default": recurring_spent_default,
        "discretionary_spent": discretionary_spent,
        "discretionary_spent_default": discretionary_spent_default,
        "recurring_total": recurring_total,
        "recurring_total_default": recurring_total_default,
        "discretionary_budget": discretionary_budget,
        "discretionary_budget_default": discretionary_budget_default,
        "budget_total": budget_total,
        "budget_total_default": budget_total_default,
        "projected_discretionary": projected_discretionary,
        "projected_discretionary_default": projected_discretionary_default,
        "available_per_day": available_per_day,
        "available_per_day_default": available_per_day_default,
        "status": status,
    }


# ── GET /api/summary ────────────────────────────────────────────────────────


async def _api_summary(request: flask.Request, user: User) -> tuple:
    period = request.args.get("period", "week")
    compare = request.args.get("compare", "false").lower() == "true"
    try:
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        offset = 0

    try:
        since, until = _period_dates(period, offset)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    sheets = _get_sheets()
    records = sheets.get_transactions(user.spreadsheet_id, since=since, until=until)

    # ── Fetch base→default rate up front so aggregations can use it ────────
    default_currency = user.default_currency
    if default_currency.upper() == user.base_currency.upper():
        base_to_default_rate: float | None = 1.0
    else:
        try:
            base_to_default_rate = round(
                await _get_currency().get_rate(user.base_currency, default_currency), 6
            )
        except Exception as exc:
            logger.warning("Could not fetch default_currency_rate: %s", exc)
            base_to_default_rate = None

    total_base = sum(r.amount_base for r in records)
    discretionary_base = sum(r.amount_base for r in records if not r.recurring)
    # Default-currency totals are the base totals at the current rate, so the
    # header's Total Spent equals total_base × current_rate exactly (no drift
    # from rounding each row independently). Per-row amount_default values are
    # still base × rate, so category breakdowns reconcile to within rounding.
    if base_to_default_rate is not None:
        total_default = total_base * base_to_default_rate
        discretionary_default = discretionary_base * base_to_default_rate
    else:
        total_default = sum(
            _amount_default(r, default_currency, base_to_default_rate) for r in records
        )
        discretionary_default = sum(
            _amount_default(r, default_currency, base_to_default_rate)
            for r in records
            if not r.recurring
        )
    days = max((until - since).days + 1, 1)

    # By category
    cat_totals: dict[str, dict] = defaultdict(
        lambda: {"amount_base": 0.0, "amount_default": 0.0, "count": 0}
    )
    for r in records:
        cat_totals[r.category]["amount_base"] += r.amount_base
        cat_totals[r.category]["amount_default"] += _amount_default(
            r, default_currency, base_to_default_rate
        )
        cat_totals[r.category]["count"] += 1

    by_category = sorted(
        [
            {
                "category": slug,
                "amount_base": round(vals["amount_base"], 4),
                "amount_default": round(vals["amount_default"], 4),
                "percentage": (
                    round(vals["amount_base"] / total_base * 100, 1) if total_base else 0.0
                ),
                "transaction_count": vals["count"],
            }
            for slug, vals in cat_totals.items()
        ],
        key=lambda x: -x["amount_base"],
    )

    # By currency
    curr_totals: dict[str, dict] = defaultdict(
        lambda: {"amount_local": 0.0, "amount_base": 0.0}
    )
    for r in records:
        curr_totals[r.local_currency]["amount_local"] += r.amount_local
        curr_totals[r.local_currency]["amount_base"] += r.amount_base

    by_currency = [
        {
            "currency": curr,
            "amount_local": round(vals["amount_local"], 4),
            "amount_base": round(vals["amount_base"], 4),
        }
        for curr, vals in curr_totals.items()
    ]

    # Daily totals
    daily_base: dict[str, float] = defaultdict(float)
    daily_default: dict[str, float] = defaultdict(float)
    for r in records:
        day_key = r.timestamp.date().isoformat()
        daily_base[day_key] += r.amount_base
        daily_default[day_key] += _amount_default(
            r, default_currency, base_to_default_rate
        )

    daily_totals = [
        {
            "date": d,
            "amount_base": round(daily_base[d], 4),
            "amount_default": round(daily_default[d], 4),
        }
        for d in sorted(daily_base)
    ]

    today = date.today()
    if period == "month" and offset == 0:
        completed_days = today.day - 1
        if completed_days > 0:
            today_discretionary_base = sum(
                r.amount_base
                for r in records
                if not r.recurring and r.timestamp.date() == today
            )
            today_discretionary_default = sum(
                _amount_default(r, default_currency, base_to_default_rate)
                for r in records
                if not r.recurring and r.timestamp.date() == today
            )
            completed_discretionary_base = max(
                discretionary_base - today_discretionary_base,
                0.0,
            )
            completed_discretionary_default = max(
                discretionary_default - today_discretionary_default,
                0.0,
            )
            daily_average = round(completed_discretionary_base / completed_days, 4)
            daily_average_default = round(
                completed_discretionary_default / completed_days,
                4,
            )
        else:
            daily_average = None
            daily_average_default = None
    else:
        daily_average = round(discretionary_base / days, 4)
        daily_average_default = round(discretionary_default / days, 4)

    if offset < 0:
        days_remaining = 0
    else:
        if period == "today":
            period_end = today
        elif period == "week":
            period_end = today - timedelta(days=today.weekday()) + timedelta(days=6)
        elif period == "month":
            import calendar as _cal
            period_end = today.replace(day=_cal.monthrange(today.year, today.month)[1])
        elif period == "year":
            period_end = today.replace(month=12, day=31)
        else:
            period_end = until
        days_remaining = max((period_end - today).days, 0)

    result: dict = {
        "period": period,
        "date_range": {"start": since.isoformat(), "end": until.isoformat()},
        "total_base": round(total_base, 4),
        "total_default": round(total_default, 4),
        "base_currency": user.base_currency,
        "default_currency": default_currency,
        "default_currency_rate": base_to_default_rate,
        "transaction_count": len(records),
        "daily_average": daily_average,
        "daily_average_default": daily_average_default,
        "days_remaining": days_remaining,
        "by_category": by_category,
        "by_currency": by_currency,
        "daily_totals": daily_totals,
    }

    # ── spending_pace (current month only) ──────────────────────────────────
    if period == "month" and offset == 0:
        spending_pace = await _compute_spending_pace(
            sheets,
            user,
            records,
            total_base,
            total_default,
            base_to_default_rate,
            since,
            until,
        )
        if spending_pace is not None:
            result["spending_pace"] = spending_pace

    if compare:
        prev_since, prev_until = _previous_period_dates(period, since, until)
        prev_records = sheets.get_transactions(
            user.spreadsheet_id, since=prev_since, until=prev_until
        )
        prev_total = sum(r.amount_base for r in prev_records)
        if prev_total > 0:
            change_pct = round((total_base - prev_total) / prev_total * 100, 1)
            result["comparison"] = {
                "previous_total": round(prev_total, 4),
                "change_percent": change_pct,
                "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
            }

        prev_cat_totals: dict[str, float] = defaultdict(float)
        for r in prev_records:
            prev_cat_totals[r.category] += r.amount_base

        for cat in result["by_category"]:
            prev_amt = round(prev_cat_totals.get(cat["category"], 0.0), 4)
            cat["previous_amount_base"] = prev_amt
            cat["change_percent"] = (
                round((cat["amount_base"] - prev_amt) / prev_amt * 100, 1)
                if prev_amt > 0
                else 0.0
            )

    return jsonify(result), 200


# ── GET /api/expenses ───────────────────────────────────────────────────────


async def _api_expenses_list(request: flask.Request, user: User) -> tuple:
    since_str = request.args.get("since")
    until_str = request.args.get("until")
    category_filter = request.args.get("category")

    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    try:
        since = date.fromisoformat(since_str) if since_str else None
        until = date.fromisoformat(until_str) if until_str else None
    except ValueError:
        return jsonify({"error": "since and until must be ISO dates (YYYY-MM-DD)"}), 400

    sheets = _get_sheets()
    records = sheets.get_transactions(user.spreadsheet_id, since=since, until=until)

    if category_filter:
        records = [r for r in records if r.category == category_filter]

    # Fetch base→default rate for amount_default computation.
    default_currency = user.default_currency
    if default_currency.upper() == user.base_currency.upper():
        base_to_default_rate: float | None = 1.0
    else:
        try:
            base_to_default_rate = round(
                await _get_currency().get_rate(user.base_currency, default_currency), 6
            )
        except Exception as exc:
            logger.warning("Could not fetch default_currency_rate for expenses: %s", exc)
            base_to_default_rate = None

    total = len(records)
    page = records[offset: offset + limit]

    return jsonify({
        "expenses": [
            _record_to_dict(r, default_currency, base_to_default_rate) for r in page
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }), 200


# ── DELETE /api/expenses/:id ────────────────────────────────────────────────


async def _api_expense_delete(expense_id: str, user: User) -> tuple:
    sheets = _get_sheets()
    deleted = sheets.delete_transaction_by_id(user.spreadsheet_id, expense_id)
    if deleted is None:
        return jsonify({"error": "expense not found"}), 404
    return jsonify({"deleted": True, "expense": _record_to_dict(deleted)}), 200


# ── PATCH /api/expenses/:id ─────────────────────────────────────────────────


async def _api_expense_update(request: flask.Request, expense_id: str, user: User) -> tuple:
    from datetime import datetime as _dt

    body = request.get_json(silent=True) or {}

    description = str(body.get("description", "")).strip()
    if not description:
        return jsonify({"error": "description is required"}), 400

    raw_amount = body.get("amount_local")
    if raw_amount in (None, ""):
        return jsonify({"error": "amount_local is required"}), 400
    try:
        amount_local = float(raw_amount)
    except (TypeError, ValueError):
        return jsonify({"error": "amount_local must be a number"}), 400
    if amount_local <= 0:
        return jsonify({"error": "amount_local must be positive"}), 400

    local_currency = str(body.get("local_currency") or user.default_currency).upper()
    category = str(body.get("category", "")).strip()
    subcategory = str(body.get("subcategory", "")).strip()
    date_str = str(body.get("date", "")).strip()

    if not category:
        return jsonify({"error": "category is required"}), 400
    if not date_str:
        return jsonify({"error": "date is required"}), 400

    try:
        expense_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "date must be YYYY-MM-DD"}), 400

    base_currency = user.base_currency
    if local_currency == base_currency.upper():
        fx_rate = 1.0
        amount_base = round(amount_local, 4)
    else:
        try:
            fx_rate = await _get_currency().get_rate(local_currency, base_currency)
            amount_base = round(amount_local * fx_rate, 4)
        except Exception as exc:
            logger.warning("FX rate fetch failed for expense update (%s->%s): %s", local_currency, base_currency, exc)
            return jsonify({"error": "could not fetch exchange rate"}), 422

    updates = {
        "description": description,
        "amount_local": amount_local,
        "local_currency": local_currency,
        "amount_base": amount_base,
        "fx_rate": fx_rate,
        "category": category,
        "subcategory": subcategory,
        "timestamp": _dt.combine(expense_date, _dt.min.time()),
    }

    sheets = _get_sheets()
    updated = sheets.update_transaction(user.spreadsheet_id, expense_id, updates)
    if updated is None:
        return jsonify({"error": "expense not found"}), 404

    default_currency = user.default_currency
    if default_currency.upper() == base_currency.upper():
        base_to_default_rate: float | None = 1.0
    else:
        try:
            base_to_default_rate = round(
                await _get_currency().get_rate(base_currency, default_currency), 6
            )
        except Exception:
            base_to_default_rate = None

    return jsonify(_record_to_dict(updated, default_currency, base_to_default_rate)), 200


# ── GET /api/budgets ────────────────────────────────────────────────────────


async def _api_budgets_get(request: flask.Request, user: User) -> tuple:
    try:
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        offset = 0

    try:
        since, until = _period_dates("month", offset)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    sheets = _get_sheets()
    all_categories = sheets.get_categories(user.spreadsheet_id)
    records = sheets.get_transactions(user.spreadsheet_id, since=since, until=until)

    # Base→default rate for default-currency spending totals.
    default_currency = user.default_currency
    if default_currency.upper() == user.base_currency.upper():
        base_to_default_rate: float | None = 1.0
    else:
        try:
            base_to_default_rate = round(
                await _get_currency().get_rate(user.base_currency, default_currency), 6
            )
        except Exception as exc:
            logger.warning("Could not fetch base_to_default_rate for budgets: %s", exc)
            base_to_default_rate = None

    def _spent_default(r: ExpenseRecord) -> float:
        """Default-currency contribution of a record.

        Preserves the historical ``amount_local`` for rows already logged in the
        default currency (no conversion), otherwise converts the base amount at
        the current rate. Falls back to ``amount_base`` when no rate is available.
        """
        if r.local_currency.upper() == default_currency.upper():
            return r.amount_local
        if base_to_default_rate is not None:
            return round(r.amount_base * base_to_default_rate, 4)
        return r.amount_base

    # Aggregate spending at both category and subcategory level
    spent_by_cat: dict[str, float] = defaultdict(float)
    spent_by_subcat: dict[tuple[str, str], float] = defaultdict(float)
    spent_default_by_cat: dict[str, float] = defaultdict(float)
    spent_default_by_subcat: dict[tuple[str, str], float] = defaultdict(float)
    for r in records:
        spent_by_cat[r.category] += r.amount_base
        spent_default_by_cat[r.category] += _spent_default(r)
        if r.subcategory:
            spent_by_subcat[(r.category, r.subcategory)] += r.amount_base
            spent_default_by_subcat[(r.category, r.subcategory)] += _spent_default(r)

    def _status(pct: float) -> str:
        if pct > 100:
            return "exceeded"
        if pct >= 80:
            return "warning"
        return "normal"

    result_budgets = []
    for cat in all_categories:
        sub_entries = []
        cat_budget = 0.0
        for sub in cat.subcategories:
            sub_budget = sub.budget or 0.0
            cat_budget += sub_budget
            sub_spent = round(spent_by_subcat.get((cat.slug, sub.slug), 0.0), 4)
            sub_spent_default = round(spent_default_by_subcat.get((cat.slug, sub.slug), 0.0), 4)
            sub_remaining = round(sub_budget - sub_spent, 4)
            sub_pct = round(sub_spent / sub_budget * 100, 1) if sub_budget > 0 else 0.0
            sub_entries.append({
                "slug": sub.slug,
                "label": sub.label,
                "budget": sub_budget,
                "spent": sub_spent,
                "spent_default": sub_spent_default,
                "remaining": sub_remaining,
                "percentage": sub_pct,
                "status": _status(sub_pct),
            })

        cat_spent = round(spent_by_cat.get(cat.slug, 0.0), 4)
        cat_spent_default = round(spent_default_by_cat.get(cat.slug, 0.0), 4)
        cat_remaining = round(cat_budget - cat_spent, 4)
        cat_pct = round(cat_spent / cat_budget * 100, 1) if cat_budget > 0 else 0.0
        result_budgets.append({
            "category": cat.slug,
            "label": cat.label,
            "budget": cat_budget,
            "spent": cat_spent,
            "spent_default": cat_spent_default,
            "remaining": cat_remaining,
            "percentage": cat_pct,
            "status": _status(cat_pct),
            "subcategories": sub_entries,
        })

    total_budget = round(sum(b["budget"] for b in result_budgets), 4)
    total_spent = round(sum(r.amount_base for r in records), 4)

    return jsonify({
        "base_currency": user.base_currency,
        "month": since.strftime("%Y-%m"),
        "total_budget": total_budget,
        "total_spent": total_spent,
        "budgets": result_budgets,
    }), 200


# ── PUT /api/budgets ────────────────────────────────────────────────────────


async def _api_budgets_update(request: flask.Request, user: User) -> tuple:
    body = request.get_json(silent=True) or {}
    raw_budgets = body.get("budgets", {})
    if not isinstance(raw_budgets, dict):
        return jsonify({"error": "budgets must be an object"}), 400

    validated: dict[str, float] = {}
    for key, amount in raw_budgets.items():
        if "/" not in str(key):
            return jsonify({"error": f"budget key must be 'category/subcategory', got {key!r}"}), 400
        try:
            validated[str(key)] = float(amount)
        except (TypeError, ValueError):
            return jsonify({"error": f"invalid budget amount for {key!r}"}), 400

    sheets = _get_sheets()
    sheets.update_subcategory_budgets(user.spreadsheet_id, validated)
    return await _api_budgets_get(request, user)


# ── GET /api/settings ───────────────────────────────────────────────────────


def _api_settings_get(user: User) -> tuple:
    return jsonify({
        "telegram_id": user.telegram_id,
        "display_name": user.display_name,
        "username": user.username,
        "email": user.email,
        "base_currency": user.base_currency,
        "default_currency": user.default_currency,
        "spreadsheet_id": user.spreadsheet_id,
        "role": user.role.value,
        "created_at": user.created_at.isoformat(),
        "budget_alerts": user.budget_alerts,
        "weekly_summary": user.weekly_summary,
        "insights": user.insights,
    }), 200


# ── PUT /api/settings ───────────────────────────────────────────────────────


async def _api_settings_update(request: flask.Request, user: User) -> tuple:
    body = request.get_json(silent=True) or {}

    base: Optional[str] = None
    default: Optional[str] = None
    budget_alerts: Optional[bool] = None
    weekly_summary: Optional[bool] = None
    insights: Optional[bool] = None

    if "base_currency" in body:
        base = str(body["base_currency"]).upper()
        if not base:
            return jsonify({"error": "base_currency must not be empty"}), 400
    if "default_currency" in body:
        default = str(body["default_currency"]).upper()
        if not default:
            return jsonify({"error": "default_currency must not be empty"}), 400
    if "budget_alerts" in body:
        budget_alerts = bool(body["budget_alerts"])
    if "weekly_summary" in body:
        weekly_summary = bool(body["weekly_summary"])
    if "insights" in body:
        insights = bool(body["insights"])

    if all(v is None for v in (base, default, budget_alerts, weekly_summary, insights)):
        return jsonify({"error": "no updatable fields provided"}), 400

    registry = _get_registry()
    try:
        updated_user = await registry.update_settings(
            user.telegram_id,
            base_currency=base,
            default_currency=default,
            budget_alerts=budget_alerts,
            weekly_summary=weekly_summary,
            insights=insights,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return _api_settings_get(updated_user)


# ── DELETE /api/expenses ─────────────────────────────────────────────────────


async def _api_expenses_clear(user: User) -> tuple:
    """Delete all transactions from the user's sheet (keeps the header row)."""
    sheets = _get_sheets()
    deleted_count = sheets.clear_all_transactions(user.spreadsheet_id)
    return jsonify({"deleted": deleted_count}), 200


# ── GET /api/export ──────────────────────────────────────────────────────────


async def _api_export(request: flask.Request, user: User) -> tuple:
    """Export transactions as a CSV file.

    Query params:
        start (YYYY-MM-DD): inclusive start date; defaults to first day of current month.
        end   (YYYY-MM-DD): inclusive end date;   defaults to today.
    """
    today = date.today()
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    try:
        since = date.fromisoformat(start_str) if start_str else today.replace(day=1)
        until = date.fromisoformat(end_str) if end_str else today
    except ValueError:
        return jsonify({"error": "start and end must be ISO dates (YYYY-MM-DD)"}), 400

    sheets = _get_sheets()
    records = sheets.get_transactions(user.spreadsheet_id, since=since, until=until)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "timestamp", "amount_local", "local_currency",
        "amount_base", "base_currency", "fx_rate",
        "category", "subcategory", "description", "source",
    ])
    for r in records:
        writer.writerow([
            r.id,
            r.timestamp.isoformat(),
            r.amount_local,
            r.local_currency,
            r.amount_base,
            r.base_currency,
            r.fx_rate,
            r.category,
            r.subcategory,
            r.description,
            r.source.value,
        ])

    filename = f"expenses_{since.isoformat()}_{until.isoformat()}.csv"
    csv_bytes = buf.getvalue().encode("utf-8")
    response = flask.make_response(csv_bytes)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response, 200


# ── GET /api/categories ──────────────────────────────────────────────────────


def _api_categories_get(user: User) -> tuple:
    """Return user's categories with subcategories and labels."""
    sheets = _get_sheets()
    categories = sheets.get_categories(user.spreadsheet_id)
    return jsonify({
        "categories": [
            {
                "slug": cat.slug,
                "label": cat.label,
                "subcategories": [
                    {"slug": sub.slug, "label": sub.label}
                    for sub in cat.subcategories
                ],
            }
            for cat in categories
        ]
    }), 200


# ── POST /api/categories ─────────────────────────────────────────────────────


async def _api_categories_create(request: flask.Request, user: User) -> tuple:
    """Create a new custom category and add it to the user's Categories sheet."""
    body = request.get_json(silent=True) or {}
    label = str(body.get("label", "")).strip()
    if not label:
        return jsonify({"error": "label is required"}), 400

    slug = _slugify(label)
    if not slug:
        slug = "cat_" + hashlib.sha1(label.encode()).hexdigest()[:8]

    sheets = _get_sheets()
    try:
        sheets.add_category(user.spreadsheet_id, slug, label)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    return _api_categories_get(user)


# ── DELETE /api/categories/<slug> ───────────────────────────────────────────


async def _api_category_delete(user: User, cat_slug: str) -> tuple:
    """Delete a category and all its subcategories."""
    sheets = _get_sheets()
    deleted = sheets.delete_category(user.spreadsheet_id, cat_slug)
    if not deleted:
        return jsonify({"error": "category not found"}), 404
    return _api_categories_get(user)


# ── DELETE /api/categories/<slug>/subcategories/<sub_slug> ───────────────────


async def _api_subcategory_delete(user: User, cat_slug: str, sub_slug: str) -> tuple:
    """Delete a single subcategory."""
    sheets = _get_sheets()
    deleted = sheets.delete_subcategory(user.spreadsheet_id, cat_slug, sub_slug)
    if not deleted:
        return jsonify({"error": "subcategory not found"}), 404
    return _api_categories_get(user)


# ── POST /api/categories/<slug>/subcategories ────────────────────────────────


async def _api_subcategory_create(request: flask.Request, user: User, cat_slug: str) -> tuple:
    """Create a new subcategory under an existing category."""
    body = request.get_json(silent=True) or {}
    label = str(body.get("label", "")).strip()
    if not label:
        return jsonify({"error": "label is required"}), 400

    sub_slug = _slugify(label)
    if not sub_slug:
        sub_slug = "sub_" + hashlib.sha1(label.encode()).hexdigest()[:8]

    sheets = _get_sheets()
    try:
        sheets.add_subcategory(user.spreadsheet_id, cat_slug, sub_slug, label)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    return _api_categories_get(user)


# ── Recurring helpers ────────────────────────────────────────────────────────


def _parse_recurring_local_amount(row: dict) -> float:
    """Extract amount_local from a recurring row, falling back to the legacy
    ``amount`` column for rows written before amount_local became canonical."""
    raw = row.get("amount_local")
    if raw in (None, ""):
        raw = row.get("amount")
    try:
        return float(raw) if raw not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


async def _recurring_base_total(
    rows: list[dict],
    base_currency: str,
    default_currency: str,
    materialised_base_by_template: dict[str, float] | None = None,
) -> float:
    """Sum recurring template amounts in the user's base currency.

    Each row's ``amount_local`` is interpreted in its ``local_currency`` (or
    the user's default_currency when missing) and converted via the currency
    service. Failed conversions fall back to 1.0 to keep the endpoint working.

    When ``materialised_base_by_template`` maps a template id to the amount_base
    of an expense already materialised for it this month, that recorded value is
    used instead of a fresh conversion — preserving the FX rate at the time the
    expense actually occurred. The default-currency total is derived by the
    caller as ``total_base × current_rate``.
    """
    currency = _get_currency()
    base_cur = base_currency.upper()
    materialised = materialised_base_by_template or {}
    total = 0.0
    for row in rows:
        template_id = str(row.get("id") or "")
        if template_id in materialised:
            total += materialised[template_id]
            continue
        amount_local = _parse_recurring_local_amount(row)
        if amount_local <= 0:
            continue
        local_cur = str(row.get("local_currency") or default_currency).upper()
        if local_cur == base_cur:
            total += amount_local
            continue
        try:
            rate = await currency.get_rate(local_cur, base_cur)
        except Exception as exc:
            logger.warning(
                "FX rate fetch failed for recurring row %s (%s→%s): %s",
                row.get("id"), local_cur, base_cur, exc,
            )
            rate = 1.0
        total += amount_local * rate
    return round(total, 4)


# ── GET /api/recurring ───────────────────────────────────────────────────────


async def _api_recurring_get(user: User) -> tuple:
    """Return all recurring expense entries with amounts converted to base currency."""
    sheets = _get_sheets()
    currency = _get_currency()
    rows = sheets.get_recurring(user.spreadsheet_id)
    base_cur = user.base_currency.upper()

    items = []
    total_base = 0.0
    for row in rows:
        amount_local = _parse_recurring_local_amount(row)
        local_cur = str(row.get("local_currency") or user.default_currency).upper()
        if amount_local <= 0:
            amount_base = 0.0
        elif local_cur == base_cur:
            amount_base = amount_local
        else:
            try:
                rate = await currency.get_rate(local_cur, base_cur)
                amount_base = round(amount_local * rate, 4)
            except Exception as exc:
                logger.warning(
                    "FX rate fetch failed for recurring row %s (%s→%s): %s",
                    row.get("id"), local_cur, base_cur, exc,
                )
                amount_base = amount_local
        total_base += amount_base
        items.append({
            "id": str(row.get("id", "")),
            "category": row.get("category", ""),
            "subcategory": row.get("subcategory", ""),
            "description": row.get("description", ""),
            "amount_base": round(amount_base, 4),
            "amount_local": amount_local,
            "local_currency": local_cur,
            "day_of_month": int(row.get("day_of_month", 1) or 1),
        })

    return jsonify({
        "base_currency": user.base_currency,
        "default_currency": user.default_currency,
        "items": items,
        "total": round(total_base, 4),
    }), 200


# ── POST /api/recurring ──────────────────────────────────────────────────────


async def _api_recurring_add(request: flask.Request, user: User) -> tuple:
    """Add a new recurring expense entry.

    The client sends the amount in the currency the user typed it in
    (``amount_local`` + ``local_currency``); conversion to base currency
    happens at read time.
    """
    body = request.get_json(silent=True) or {}
    description = str(body.get("description", "")).strip()
    if not description:
        return jsonify({"error": "description is required"}), 400

    raw_amount = body.get("amount_local")
    if raw_amount in (None, ""):
        raw_amount = body.get("amount")  # client backward-compat
    if raw_amount in (None, ""):
        return jsonify({"error": "amount_local is required"}), 400
    try:
        amount_local = float(raw_amount)
    except (TypeError, ValueError):
        return jsonify({"error": "amount_local must be a number"}), 400
    if amount_local <= 0:
        return jsonify({"error": "amount_local must be positive"}), 400

    local_currency = str(body.get("local_currency") or user.default_currency).upper()

    entry = {
        "category": body.get("category", ""),
        "subcategory": body.get("subcategory", ""),
        "description": description,
        # The "amount" column is retained as a duplicate of amount_local so
        # the spreadsheet stays readable; it is no longer interpreted as base.
        "amount": amount_local,
        "amount_local": amount_local,
        "local_currency": local_currency,
        "day_of_month": int(body.get("day_of_month", 1)),
    }
    sheets = _get_sheets()
    sheets.add_recurring(user.spreadsheet_id, entry)
    return await _api_recurring_get(user)


# ── PUT /api/recurring/<entry_id> ────────────────────────────────────────────


async def _api_recurring_update(request: flask.Request, user: User, entry_id: str) -> tuple:
    """Update an existing recurring expense entry."""
    body = request.get_json(silent=True) or {}
    description = str(body.get("description", "")).strip()
    if not description:
        return jsonify({"error": "description is required"}), 400

    raw_amount = body.get("amount_local")
    if raw_amount in (None, ""):
        return jsonify({"error": "amount_local is required"}), 400
    try:
        amount_local = float(raw_amount)
    except (TypeError, ValueError):
        return jsonify({"error": "amount_local must be a number"}), 400
    if amount_local <= 0:
        return jsonify({"error": "amount_local must be positive"}), 400

    local_currency = str(body.get("local_currency") or user.default_currency).upper()

    updates = {
        "category": body.get("category", ""),
        "subcategory": body.get("subcategory", ""),
        "description": description,
        "amount": amount_local,
        "amount_local": amount_local,
        "local_currency": local_currency,
        "day_of_month": int(body.get("day_of_month", 1)),
    }
    sheets = _get_sheets()
    updated = sheets.update_recurring(user.spreadsheet_id, entry_id, updates)
    if not updated:
        return jsonify({"error": "entry not found"}), 404
    return await _api_recurring_get(user)


# ── DELETE /api/recurring/<entry_id> ────────────────────────────────────────


async def _api_recurring_delete(user: User, entry_id: str) -> tuple:
    """Delete a recurring expense entry by id."""
    sheets = _get_sheets()
    deleted = sheets.delete_recurring(user.spreadsheet_id, entry_id)
    if not deleted:
        return jsonify({"error": "entry not found"}), 404
    return await _api_recurring_get(user)


# ── POST /api/recurring/<entry_id>/log ───────────────────────────────────────


async def _api_recurring_log(user: User, entry_id: str) -> tuple:
    """Force-log a recurring expense template as a transaction right now.

    Returns 409 if the template was already logged this calendar month.
    """
    from datetime import date as _date
    from jobs.recurring_cron import _build_record

    sheets = _get_sheets()
    currency = _get_currency()

    rows = sheets.get_recurring(user.spreadsheet_id)
    item = next((r for r in rows if str(r.get("id", "")) == entry_id), None)
    if item is None:
        return jsonify({"error": "entry not found"}), 404

    today = _date.today()
    month_start = today.replace(day=1)
    existing = sheets.get_transactions(user.spreadsheet_id, since=month_start, until=today)
    already = any(
        r.recurring and r.recurring_template_id == entry_id
        for r in existing
    )
    if already:
        return jsonify({"error": "already_logged_this_month"}), 409

    record = await _build_record(currency, user, item, today)
    if record is None:
        return jsonify({"error": "could not build record"}), 422

    sheets.append_transaction(user.spreadsheet_id, record)
    return jsonify({"ok": True}), 201
