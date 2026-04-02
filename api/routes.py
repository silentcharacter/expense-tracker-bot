"""REST API for Telegram Mini App, served alongside the existing webhook."""

import csv
import io
import logging
import os
import re as _re
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
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
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
    elif path == "/expenses" and method == "DELETE":
        return await _api_expenses_clear(user)
    elif path == "/export" and method == "GET":
        return await _api_export(request, user)
    elif path == "/categories" and method == "GET":
        return _api_categories_get(user)
    elif path == "/categories" and method == "POST":
        return await _api_categories_create(request, user)
    else:
        return jsonify({"error": "not found"}), 404


# ── Period helpers ──────────────────────────────────────────────────────────


def _period_dates(period: str) -> tuple[date, date]:
    """Return inclusive (since, until) dates for the named period."""
    today = date.today()
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

    days_remaining = max((until - date.today()).days, 0)

    result: dict = {
        "period": period,
        "date_range": {"start": since.isoformat(), "end": until.isoformat()},
        "total_base": round(total_base, 4),
        "base_currency": user.base_currency,
        "transaction_count": len(records),
        "daily_average": round(total_base / days, 4),
        "days_remaining": days_remaining,
        "by_category": by_category,
        "by_currency": by_currency,
        "daily_totals": daily_totals,
    }

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
    all_categories = sheets.get_categories(user.spreadsheet_id)
    records = sheets.get_transactions(user.spreadsheet_id, since=since, until=today)

    # Aggregate spending at both category and subcategory level
    spent_by_cat: dict[str, float] = defaultdict(float)
    spent_by_subcat: dict[tuple[str, str], float] = defaultdict(float)
    for r in records:
        spent_by_cat[r.category] += r.amount_base
        if r.subcategory:
            spent_by_subcat[(r.category, r.subcategory)] += r.amount_base

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
            sub_remaining = round(sub_budget - sub_spent, 4)
            sub_pct = round(sub_spent / sub_budget * 100, 1) if sub_budget > 0 else 0.0
            sub_entries.append({
                "slug": sub.slug,
                "label": sub.label,
                "budget": sub_budget,
                "spent": sub_spent,
                "remaining": sub_remaining,
                "percentage": sub_pct,
                "status": _status(sub_pct),
            })

        cat_spent = round(spent_by_cat.get(cat.slug, 0.0), 4)
        cat_remaining = round(cat_budget - cat_spent, 4)
        cat_pct = round(cat_spent / cat_budget * 100, 1) if cat_budget > 0 else 0.0
        result_budgets.append({
            "category": cat.slug,
            "label": cat.label,
            "budget": cat_budget,
            "spent": cat_spent,
            "remaining": cat_remaining,
            "percentage": cat_pct,
            "status": _status(cat_pct),
            "subcategories": sub_entries,
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
    for key, amount in raw_budgets.items():
        if "/" not in str(key):
            return jsonify({"error": f"budget key must be 'category/subcategory', got {key!r}"}), 400
        try:
            validated[str(key)] = float(amount)
        except (TypeError, ValueError):
            return jsonify({"error": f"invalid budget amount for {key!r}"}), 400

    sheets = _get_sheets()
    sheets.update_subcategory_budgets(user.spreadsheet_id, validated)
    return await _api_budgets_get(user)


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

    slug = _re.sub(r"[^a-z0-9_]", "", label.lower().replace(" ", "_"))
    if not slug:
        return jsonify({"error": "label must contain at least one alphanumeric character"}), 400

    sheets = _get_sheets()
    try:
        sheets.add_category(user.spreadsheet_id, slug, label)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    return _api_categories_get(user)
