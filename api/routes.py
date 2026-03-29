"""REST API for Telegram Mini App, served alongside the existing webhook."""

import logging
import os
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

import flask
from flask import jsonify

from models.expense import ExpenseRecord, User
from services.auth import validate_init_data
from services.sheets import SheetsService
from services.user_registry import UserRegistry

logger = logging.getLogger(__name__)

# ── Lazy service singletons ─────────────────────────────────────────────────
# Re-using the same instances across Cloud Function warm invocations.

_sheets_singleton: Optional[SheetsService] = None
_registry_singleton: Optional[UserRegistry] = None


def _get_sheets() -> SheetsService:
    global _sheets_singleton
    if _sheets_singleton is None:
        _sheets_singleton = SheetsService()
    return _sheets_singleton


def _get_registry() -> UserRegistry:
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = UserRegistry(sheets_service=_get_sheets())
    return _registry_singleton


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
        "Access-Control-Allow-Methods": "GET, PUT, DELETE, OPTIONS",
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
    elif path == "/budgets" and method == "GET":
        return await _api_budgets_get(user)
    elif path == "/budgets" and method == "PUT":
        return await _api_budgets_update(request, user)
    elif path == "/settings" and method == "GET":
        return _api_settings_get(user)
    elif path == "/settings" and method == "PUT":
        return await _api_settings_update(request, user)
    else:
        return jsonify({"error": "not found"}), 404


# ── Period helpers ──────────────────────────────────────────────────────────


def _period_dates(period: str) -> tuple[date, date]:
    """Return inclusive (since, until) dates for the named period."""
    today = date.today()
    if period == "today":
        return today, today
    elif period == "week":
        return today - timedelta(days=6), today
    elif period == "month":
        return today.replace(day=1), today
    elif period == "year":
        return today.replace(month=1, day=1), today
    else:
        raise ValueError(f"Unknown period {period!r}; must be today|week|month|year")


def _previous_period_dates(since: date, until: date) -> tuple[date, date]:
    """Return an equal-length period ending the day before since."""
    length = (until - since).days + 1
    prev_until = since - timedelta(days=1)
    prev_since = prev_until - timedelta(days=length - 1)
    return prev_since, prev_until


# ── Serialisation ───────────────────────────────────────────────────────────


def _record_to_dict(r: ExpenseRecord) -> dict:
    return {
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
    }


# ── GET /api/summary ────────────────────────────────────────────────────────


async def _api_summary(request: flask.Request, user: User) -> tuple:
    period = request.args.get("period", "week")
    compare = request.args.get("compare", "false").lower() == "true"

    try:
        since, until = _period_dates(period)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    sheets = _get_sheets()
    records = sheets.get_transactions(user.spreadsheet_id, since=since, until=until)

    total_base = sum(r.amount_base for r in records)
    days = max((until - since).days + 1, 1)

    # By category
    cat_totals: dict[str, dict] = defaultdict(lambda: {"amount_base": 0.0, "count": 0})
    for r in records:
        cat_totals[r.category]["amount_base"] += r.amount_base
        cat_totals[r.category]["count"] += 1

    by_category = sorted(
        [
            {
                "category": slug,
                "amount_base": round(vals["amount_base"], 4),
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
    daily: dict[str, float] = defaultdict(float)
    for r in records:
        daily[r.timestamp.date().isoformat()] += r.amount_base

    daily_totals = [
        {"date": d, "amount_base": round(amt, 4)} for d, amt in sorted(daily.items())
    ]

    result: dict = {
        "period": period,
        "date_range": {"start": since.isoformat(), "end": until.isoformat()},
        "total_base": round(total_base, 4),
        "base_currency": user.base_currency,
        "transaction_count": len(records),
        "daily_average": round(total_base / days, 4),
        "by_category": by_category,
        "by_currency": by_currency,
        "daily_totals": daily_totals,
    }

    if compare:
        prev_since, prev_until = _previous_period_dates(since, until)
        prev_records = sheets.get_transactions(
            user.spreadsheet_id, since=prev_since, until=prev_until
        )
        prev_total = sum(r.amount_base for r in prev_records)
        change_pct = (
            round((total_base - prev_total) / prev_total * 100, 1) if prev_total else 0.0
        )
        result["comparison"] = {
            "previous_total": round(prev_total, 4),
            "change_percent": change_pct,
            "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
        }

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

    total = len(records)
    page = records[offset: offset + limit]

    return jsonify({
        "expenses": [_record_to_dict(r) for r in page],
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


# ── GET /api/budgets ────────────────────────────────────────────────────────


async def _api_budgets_get(user: User) -> tuple:
    today = date.today()
    since = today.replace(day=1)

    sheets = _get_sheets()
    budgets_config = sheets.get_budgets(user.spreadsheet_id)
    records = sheets.get_transactions(user.spreadsheet_id, since=since, until=today)

    spent_by_cat: dict[str, float] = defaultdict(float)
    for r in records:
        spent_by_cat[r.category] += r.amount_base

    result_budgets = []
    for slug, budget_amount in budgets_config.items():
        spent = round(spent_by_cat.get(slug, 0.0), 4)
        remaining = round(budget_amount - spent, 4)
        pct = round(spent / budget_amount * 100, 1) if budget_amount > 0 else 0.0
        if pct < 80:
            status = "normal"
        elif pct <= 100:
            status = "warning"
        else:
            status = "exceeded"
        result_budgets.append({
            "category": slug,
            "budget": budget_amount,
            "spent": spent,
            "remaining": remaining,
            "percentage": pct,
            "status": status,
        })

    return jsonify({
        "base_currency": user.base_currency,
        "month": today.strftime("%Y-%m"),
        "budgets": result_budgets,
    }), 200


# ── PUT /api/budgets ────────────────────────────────────────────────────────


async def _api_budgets_update(request: flask.Request, user: User) -> tuple:
    body = request.get_json(silent=True) or {}
    raw_budgets = body.get("budgets", {})
    if not isinstance(raw_budgets, dict):
        return jsonify({"error": "budgets must be an object"}), 400

    validated: dict[str, float] = {}
    for slug, amount in raw_budgets.items():
        try:
            validated[str(slug)] = float(amount)
        except (TypeError, ValueError):
            return jsonify({"error": f"invalid budget amount for {slug!r}"}), 400

    sheets = _get_sheets()
    sheets.update_category_budgets(user.spreadsheet_id, validated)
    return await _api_budgets_get(user)


# ── GET /api/settings ───────────────────────────────────────────────────────


def _api_settings_get(user: User) -> tuple:
    return jsonify({
        "telegram_id": user.telegram_id,
        "display_name": user.display_name,
        "email": user.email,
        "base_currency": user.base_currency,
        "default_currency": user.default_currency,
        "spreadsheet_id": user.spreadsheet_id,
        "role": user.role.value,
        "created_at": user.created_at.isoformat(),
    }), 200


# ── PUT /api/settings ───────────────────────────────────────────────────────


async def _api_settings_update(request: flask.Request, user: User) -> tuple:
    body = request.get_json(silent=True) or {}
    base = str(body.get("base_currency", "")).upper()
    default = str(body.get("default_currency", "")).upper()

    if not base or not default:
        return jsonify({"error": "base_currency and default_currency are required"}), 400

    registry = _get_registry()
    try:
        updated_user = await registry.update_settings(user.telegram_id, base, default)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return _api_settings_get(updated_user)
