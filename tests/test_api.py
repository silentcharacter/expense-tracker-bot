"""Unit tests for api/routes.py — all endpoints + auth edge cases.

No external services are used. Services are replaced with MagicMock /
AsyncMock fixtures so tests run offline and instantaneously.
"""

import json
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch

import flask
import pytest

from models.expense import ExpenseRecord, ExpenseSource, User, UserRole, UserStatus
from models.category import UserCategory, UserSubcategory

# A minimal Flask app whose context makes flask.jsonify() usable in tests.
_flask_app = flask.Flask(__name__)

TG_ID = 42


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def user() -> User:
    return User(
        telegram_id=TG_ID,
        display_name="Alice",
        spreadsheet_id="sheet123",
        base_currency="USD",
        default_currency="THB",
        role=UserRole.user,
        status=UserStatus.active,
        created_at=datetime(2026, 3, 1, 12, 0, 0),
    )


@pytest.fixture
def mock_sheets() -> MagicMock:
    m = MagicMock()
    m.get_transactions.return_value = []
    m.get_budgets.return_value = {}
    m.delete_transaction_by_id.return_value = None
    return m


@pytest.fixture
def mock_registry(user: User) -> AsyncMock:
    m = AsyncMock()
    m.get_user.return_value = user
    return m


@pytest.fixture
def mock_currency() -> MagicMock:
    """Stub CurrencyService that returns a fixed FX rate without HTTP calls."""
    m = MagicMock()
    m.get_rate = AsyncMock(return_value=33.5)
    return m


def _make_record(**kwargs) -> ExpenseRecord:
    """Build an ExpenseRecord with sensible defaults, overridable via kwargs."""
    defaults: dict = dict(
        amount_local=100.0,
        local_currency="THB",
        amount_base=3.0,
        base_currency="USD",
        fx_rate=0.03,
        category="food",
        subcategory="restaurant",
        description="lunch",
        source=ExpenseSource.text,
        timestamp=datetime(2026, 3, 15, 12, 0, 0),
    )
    defaults.update(kwargs)
    return ExpenseRecord(**defaults)


# ── Test helper ───────────────────────────────────────────────────────────────


async def _call(
    method: str,
    path: str,
    mock_sheets: MagicMock,
    mock_registry: AsyncMock,
    headers: dict | None = None,
    json_body: dict | None = None,
    args: dict | None = None,
    valid_auth: bool = True,
    mock_currency: MagicMock | None = None,
) -> tuple[dict | bytes, int]:
    """Call handle_api_request inside a Flask test context and return (body, status).

    body is a dict for JSON responses, or raw bytes for non-JSON (e.g. CSV export).
    """
    from api.routes import handle_api_request

    auth_return = {"id": TG_ID} if valid_auth else None
    all_headers = {"Authorization": "tma test", **(headers or {})}

    if mock_currency is None:
        mock_currency = MagicMock()
        mock_currency.get_rate = AsyncMock(return_value=1.0)

    with (
        patch("api.routes._get_sheets", return_value=mock_sheets),
        patch("api.routes._get_registry", return_value=mock_registry),
        patch("api.routes._get_currency", return_value=mock_currency),
        patch("api.routes.validate_init_data", return_value=auth_return),
        _flask_app.test_request_context(
            path,
            method=method,
            headers=all_headers,
            json=json_body,
            query_string=args or {},
        ),
    ):
        result = await handle_api_request(flask.request)

    if isinstance(result, tuple) and len(result) == 3:
        # CORS preflight: ("", status, headers_dict)
        return {}, result[1]

    response, status = result[0], result[1]
    content_type = response.content_type if hasattr(response, "content_type") else ""
    if "text/csv" in content_type:
        return response.get_data(), status
    body: dict = json.loads(response.get_data(as_text=True))
    return body, status


# ── Auth ──────────────────────────────────────────────────────────────────────


async def test_unauthenticated_returns_401(mock_sheets, mock_registry) -> None:
    """Requests with invalid initData are rejected with 401."""
    body, status = await _call(
        "GET", "/api/summary", mock_sheets, mock_registry, valid_auth=False
    )
    assert status == 401
    assert "unauthorized" in body["error"]


async def test_user_not_in_registry_returns_401(mock_sheets, mock_registry) -> None:
    """Valid initData but user not registered → 401."""
    mock_registry.get_user.return_value = None
    body, status = await _call("GET", "/api/settings", mock_sheets, mock_registry)
    assert status == 401


# ── GET /api/summary ──────────────────────────────────────────────────────────


async def test_summary_aggregations(mock_sheets, mock_registry) -> None:
    """Summary computes total, category breakdown, currency breakdown, and daily totals."""
    mock_sheets.get_transactions.return_value = [
        _make_record(amount_base=10.0, category="food", local_currency="THB", amount_local=350.0),
        _make_record(
            amount_base=5.0,
            category="transport",
            local_currency="USD",
            amount_local=5.0,
            timestamp=datetime(2026, 3, 16, 9, 0, 0),
        ),
    ]
    body, status = await _call(
        "GET", "/api/summary", mock_sheets, mock_registry, args={"period": "week"}
    )
    assert status == 200
    assert body["period"] == "week"
    assert body["total_base"] == pytest.approx(15.0)
    assert body["transaction_count"] == 2
    assert body["base_currency"] == "USD"
    # Category breakdown — food first (higher amount)
    cats = {c["category"]: c for c in body["by_category"]}
    assert "food" in cats
    assert cats["food"]["amount_base"] == pytest.approx(10.0)
    assert cats["food"]["percentage"] == pytest.approx(66.7, abs=0.1)
    # Currency breakdown
    currencies = {c["currency"]: c for c in body["by_currency"]}
    assert "THB" in currencies
    assert currencies["THB"]["amount_local"] == pytest.approx(350.0)
    # Daily totals — two different dates
    assert len(body["daily_totals"]) == 2


async def test_summary_compare(mock_sheets, mock_registry) -> None:
    """compare=true adds a comparison block with direction."""
    current = [_make_record(amount_base=100.0)]
    previous = [_make_record(amount_base=200.0)]
    mock_sheets.get_transactions.side_effect = [current, previous]

    body, status = await _call(
        "GET",
        "/api/summary",
        mock_sheets,
        mock_registry,
        args={"period": "week", "compare": "true"},
    )
    assert status == 200
    assert "comparison" in body
    cmp = body["comparison"]
    assert cmp["previous_total"] == pytest.approx(200.0)
    assert cmp["change_percent"] == pytest.approx(-50.0)
    assert cmp["direction"] == "down"


async def test_summary_includes_default_currency_rate(mock_sheets, mock_registry, mock_currency) -> None:
    """Summary always includes default_currency and default_currency_rate fields."""
    mock_sheets.get_transactions.return_value = []
    body, status = await _call(
        "GET", "/api/summary", mock_sheets, mock_registry,
        args={"period": "week"}, mock_currency=mock_currency,
    )
    assert status == 200
    assert body["default_currency"] == "THB"
    assert body["default_currency_rate"] == pytest.approx(33.5)


async def test_summary_month_includes_spending_pace(mock_sheets, mock_registry, mock_currency) -> None:
    """Monthly summary at offset=0 includes a spending_pace block (spec §1.2)."""
    mock_sheets.get_transactions.return_value = [
        _make_record(amount_base=200.0, category="food"),
        _make_record(amount_base=500.0, category="housing", recurring=True, recurring_template_id="t1"),
    ]
    mock_sheets.get_recurring.return_value = [
        {
            "id": "t1",
            "amount_local": 500.0,
            "local_currency": "USD",  # same as base → no FX conversion
            "day_of_month": 1,
        },
    ]
    mock_sheets.get_budgets.return_value = {"food": 600.0, "housing": 500.0}

    body, status = await _call(
        "GET", "/api/summary", mock_sheets, mock_registry,
        args={"period": "month"}, mock_currency=mock_currency,
    )
    assert status == 200
    assert "spending_pace" in body
    pace = body["spending_pace"]
    assert pace["recurring_spent"] == pytest.approx(500.0)
    assert pace["discretionary_spent"] == pytest.approx(200.0)
    assert pace["recurring_total"] == pytest.approx(500.0)
    assert pace["budget_total"] == pytest.approx(1100.0)
    assert pace["discretionary_budget"] == pytest.approx(600.0)
    assert pace["status"] in ("on_track", "over_pace")
    assert pace["days_in_month"] >= 28
    assert pace["days_elapsed"] >= 1


async def test_summary_week_omits_spending_pace(mock_sheets, mock_registry, mock_currency) -> None:
    """Spending pace only attached for current month — not for week/today."""
    mock_sheets.get_transactions.return_value = []
    body, status = await _call(
        "GET", "/api/summary", mock_sheets, mock_registry,
        args={"period": "week"}, mock_currency=mock_currency,
    )
    assert status == 200
    assert "spending_pace" not in body


async def test_summary_invalid_period(mock_sheets, mock_registry) -> None:
    body, status = await _call(
        "GET", "/api/summary", mock_sheets, mock_registry, args={"period": "forever"}
    )
    assert status == 400
    assert "error" in body


async def test_summary_empty_period(mock_sheets, mock_registry) -> None:
    """Empty transaction list returns zeros without crashing."""
    mock_sheets.get_transactions.return_value = []
    body, status = await _call(
        "GET", "/api/summary", mock_sheets, mock_registry, args={"period": "today"}
    )
    assert status == 200
    assert body["total_base"] == 0.0
    assert body["by_category"] == []


# ── GET /api/expenses ─────────────────────────────────────────────────────────


async def test_expenses_list_pagination(mock_sheets, mock_registry) -> None:
    """offset and limit slice the result; total reflects unsliced count."""
    mock_sheets.get_transactions.return_value = [_make_record() for _ in range(10)]
    body, status = await _call(
        "GET",
        "/api/expenses",
        mock_sheets,
        mock_registry,
        args={"limit": "3", "offset": "2"},
    )
    assert status == 200
    assert body["total"] == 10
    assert body["limit"] == 3
    assert body["offset"] == 2
    assert len(body["expenses"]) == 3


async def test_expenses_list_category_filter(mock_sheets, mock_registry) -> None:
    """category param filters server-side before pagination."""
    mock_sheets.get_transactions.return_value = [
        _make_record(category="food"),
        _make_record(category="transport"),
        _make_record(category="food"),
    ]
    body, status = await _call(
        "GET",
        "/api/expenses",
        mock_sheets,
        mock_registry,
        args={"category": "food"},
    )
    assert status == 200
    assert body["total"] == 2
    assert all(e["category"] == "food" for e in body["expenses"])


async def test_expenses_list_date_params_passed_to_sheets(mock_sheets, mock_registry) -> None:
    """since/until are forwarded to sheets.get_transactions."""
    body, status = await _call(
        "GET",
        "/api/expenses",
        mock_sheets,
        mock_registry,
        args={"since": "2026-03-01", "until": "2026-03-15"},
    )
    assert status == 200
    call_kwargs = mock_sheets.get_transactions.call_args
    assert call_kwargs.kwargs["since"] == date(2026, 3, 1)
    assert call_kwargs.kwargs["until"] == date(2026, 3, 15)


async def test_expenses_list_invalid_date(mock_sheets, mock_registry) -> None:
    body, status = await _call(
        "GET",
        "/api/expenses",
        mock_sheets,
        mock_registry,
        args={"since": "not-a-date"},
    )
    assert status == 400


async def test_expenses_limit_capped_at_200(mock_sheets, mock_registry) -> None:
    mock_sheets.get_transactions.return_value = []
    body, status = await _call(
        "GET",
        "/api/expenses",
        mock_sheets,
        mock_registry,
        args={"limit": "9999"},
    )
    assert status == 200
    assert body["limit"] == 200


async def test_expenses_record_fields(mock_sheets, mock_registry) -> None:
    """Response includes all expected fields per the spec."""
    r = _make_record()
    mock_sheets.get_transactions.return_value = [r]
    body, status = await _call("GET", "/api/expenses", mock_sheets, mock_registry)
    assert status == 200
    exp = body["expenses"][0]
    assert exp["id"] == r.id
    assert exp["category"] == "food"
    assert exp["source"] == "text"
    assert "timestamp" in exp
    # is_recurring defaults to False for plain records
    assert exp["is_recurring"] is False


async def test_expenses_is_recurring_flag(mock_sheets, mock_registry) -> None:
    """Records materialised by the recurring cron expose is_recurring=True."""
    r = _make_record(recurring=True, recurring_template_id="tpl-1")
    mock_sheets.get_transactions.return_value = [r]
    body, status = await _call("GET", "/api/expenses", mock_sheets, mock_registry)
    assert status == 200
    assert body["expenses"][0]["is_recurring"] is True


# ── DELETE /api/expenses/:id ──────────────────────────────────────────────────


async def test_expense_delete_success(mock_sheets, mock_registry) -> None:
    r = _make_record(id="abc-123")
    mock_sheets.delete_transaction_by_id.return_value = r
    body, status = await _call(
        "DELETE", "/api/expenses/abc-123", mock_sheets, mock_registry
    )
    assert status == 200
    assert body["deleted"] is True
    assert body["expense"]["id"] == "abc-123"
    mock_sheets.delete_transaction_by_id.assert_called_once_with("sheet123", "abc-123")


async def test_expense_delete_not_found(mock_sheets, mock_registry) -> None:
    mock_sheets.delete_transaction_by_id.return_value = None
    body, status = await _call(
        "DELETE", "/api/expenses/missing-id", mock_sheets, mock_registry
    )
    assert status == 404
    assert "not found" in body["error"]


# ── GET /api/budgets ──────────────────────────────────────────────────────────


async def test_budgets_get_status_calculation(mock_sheets, mock_registry) -> None:
    """Budget statuses: normal (<80%), warning (80-100%), exceeded (>100%)."""
    mock_sheets.get_categories.return_value = [
        UserCategory(slug="food", label="Food & Drinks", subcategories=[
            UserSubcategory(slug="restaurant", label="Restaurant", budget=100.0),
        ]),
        UserCategory(slug="transport", label="Transport", subcategories=[
            UserSubcategory(slug="taxi", label="Taxi", budget=100.0),
        ]),
        UserCategory(slug="housing", label="Housing", subcategories=[
            UserSubcategory(slug="rent", label="Rent", budget=100.0),
        ]),
    ]
    mock_sheets.get_transactions.return_value = [
        _make_record(category="food", amount_base=40.0),
        _make_record(category="transport", amount_base=90.0),
        _make_record(category="housing", amount_base=120.0),
    ]
    body, status = await _call("GET", "/api/budgets", mock_sheets, mock_registry)
    assert status == 200
    assert body["base_currency"] == "USD"
    by_cat = {b["category"]: b for b in body["budgets"]}
    assert by_cat["food"]["status"] == "normal"
    assert by_cat["transport"]["status"] == "warning"
    assert by_cat["housing"]["status"] == "exceeded"
    assert by_cat["food"]["spent"] == pytest.approx(40.0)
    assert by_cat["housing"]["remaining"] == pytest.approx(-20.0)
    # Each category entry includes subcategories list
    assert isinstance(by_cat["food"]["subcategories"], list)


async def test_budgets_get_unspent_category(mock_sheets, mock_registry) -> None:
    """Categories with a budget but zero spending appear with spent=0."""
    mock_sheets.get_categories.return_value = [
        UserCategory(slug="food", label="Food & Drinks", subcategories=[
            UserSubcategory(slug="restaurant", label="Restaurant", budget=200.0),
        ]),
    ]
    mock_sheets.get_transactions.return_value = []
    body, status = await _call("GET", "/api/budgets", mock_sheets, mock_registry)
    assert status == 200
    assert body["budgets"][0]["spent"] == 0.0
    assert body["budgets"][0]["status"] == "normal"
    assert body["budgets"][0]["budget"] == 200.0


async def test_budgets_get_includes_unbudgeted_categories(mock_sheets, mock_registry) -> None:
    """GET /api/budgets returns all categories, including those with no subcategory budgets."""
    mock_sheets.get_categories.return_value = [
        UserCategory(slug="food", label="Food & Drinks", subcategories=[
            UserSubcategory(slug="restaurant", label="Restaurant", budget=200.0),
        ]),
        UserCategory(slug="other", label="Other", subcategories=[]),
    ]
    mock_sheets.get_transactions.return_value = []
    body, status = await _call("GET", "/api/budgets", mock_sheets, mock_registry)
    assert status == 200
    slugs = [b["category"] for b in body["budgets"]]
    assert "food" in slugs
    assert "other" in slugs
    by_cat = {b["category"]: b for b in body["budgets"]}
    assert by_cat["other"]["budget"] == 0.0


# ── PUT /api/budgets ──────────────────────────────────────────────────────────


async def test_budgets_update_calls_sheets(mock_sheets, mock_registry) -> None:
    """PUT /api/budgets calls update_subcategory_budgets and returns updated budgets."""
    mock_sheets.get_categories.return_value = [
        UserCategory(slug="food", label="Food & Drinks", subcategories=[
            UserSubcategory(slug="restaurant", label="Restaurant", budget=450.0),
        ]),
    ]
    mock_sheets.get_transactions.return_value = []

    body, status = await _call(
        "PUT",
        "/api/budgets",
        mock_sheets,
        mock_registry,
        json_body={"budgets": {"food/restaurant": 450.0, "transport/taxi": 200.0}},
    )
    assert status == 200
    mock_sheets.update_subcategory_budgets.assert_called_once_with(
        "sheet123", {"food/restaurant": 450.0, "transport/taxi": 200.0}
    )
    # Response is the updated budgets view
    assert "budgets" in body


async def test_budgets_update_invalid_amount(mock_sheets, mock_registry) -> None:
    body, status = await _call(
        "PUT",
        "/api/budgets",
        mock_sheets,
        mock_registry,
        json_body={"budgets": {"food": "not-a-number"}},
    )
    assert status == 400
    assert "error" in body


async def test_budgets_update_non_dict(mock_sheets, mock_registry) -> None:
    body, status = await _call(
        "PUT",
        "/api/budgets",
        mock_sheets,
        mock_registry,
        json_body={"budgets": [1, 2, 3]},
    )
    assert status == 400


# ── GET /api/settings ─────────────────────────────────────────────────────────


async def test_settings_get_fields(mock_sheets, mock_registry, user: User) -> None:
    """Settings response contains all spec-required fields including notification flags."""
    body, status = await _call("GET", "/api/settings", mock_sheets, mock_registry)
    assert status == 200
    assert body["telegram_id"] == TG_ID
    assert body["display_name"] == "Alice"
    assert body["base_currency"] == "USD"
    assert body["default_currency"] == "THB"
    assert body["spreadsheet_id"] == "sheet123"
    assert body["role"] == "user"
    assert "created_at" in body
    # Notification flags (defaults)
    assert body["budget_alerts"] is True
    assert body["weekly_summary"] is True
    assert body["insights"] is True


# ── PUT /api/settings ─────────────────────────────────────────────────────────


async def test_settings_update_currencies(mock_sheets, mock_registry, user: User) -> None:
    """Providing only base_currency updates that field; no 400 is raised."""
    updated = user.model_copy(update={"base_currency": "EUR"})
    mock_registry.update_settings.return_value = updated

    body, status = await _call(
        "PUT",
        "/api/settings",
        mock_sheets,
        mock_registry,
        json_body={"base_currency": "EUR"},
    )
    assert status == 200
    mock_registry.update_settings.assert_called_once_with(
        TG_ID,
        base_currency="EUR",
        default_currency=None,
        budget_alerts=None,
        weekly_summary=None,
        insights=None,
    )
    assert body["base_currency"] == "EUR"


async def test_settings_update_both_currencies(mock_sheets, mock_registry, user: User) -> None:
    updated = user.model_copy(update={"base_currency": "EUR", "default_currency": "THB"})
    mock_registry.update_settings.return_value = updated

    body, status = await _call(
        "PUT",
        "/api/settings",
        mock_sheets,
        mock_registry,
        json_body={"base_currency": "EUR", "default_currency": "THB"},
    )
    assert status == 200
    assert body["base_currency"] == "EUR"


async def test_settings_update_notifications(mock_sheets, mock_registry, user: User) -> None:
    """Toggling a notification flag persists via registry.update_settings."""
    updated = user.model_copy(update={"budget_alerts": False})
    mock_registry.update_settings.return_value = updated

    body, status = await _call(
        "PUT",
        "/api/settings",
        mock_sheets,
        mock_registry,
        json_body={"budget_alerts": False},
    )
    assert status == 200
    mock_registry.update_settings.assert_called_once_with(
        TG_ID,
        base_currency=None,
        default_currency=None,
        budget_alerts=False,
        weekly_summary=None,
        insights=None,
    )
    assert body["budget_alerts"] is False


async def test_settings_update_invalid_currency(mock_sheets, mock_registry) -> None:
    """Invalid ISO 4217 code from registry.update_settings → 400."""
    mock_registry.update_settings.side_effect = ValueError("invalid currency")

    body, status = await _call(
        "PUT",
        "/api/settings",
        mock_sheets,
        mock_registry,
        json_body={"base_currency": "FAKE"},
    )
    assert status == 400
    assert "error" in body


async def test_settings_update_empty_body(mock_sheets, mock_registry) -> None:
    """Empty body (no updatable fields) returns 400."""
    body, status = await _call(
        "PUT",
        "/api/settings",
        mock_sheets,
        mock_registry,
        json_body={},
    )
    assert status == 400
    assert "error" in body


# ── DELETE /api/expenses ──────────────────────────────────────────────────────


async def test_expenses_clear_all(mock_sheets, mock_registry) -> None:
    """DELETE /api/expenses clears all transactions and returns deleted count."""
    mock_sheets.clear_all_transactions.return_value = 17

    body, status = await _call(
        "DELETE",
        "/api/expenses",
        mock_sheets,
        mock_registry,
    )
    assert status == 200
    assert body["deleted"] == 17
    mock_sheets.clear_all_transactions.assert_called_once_with("sheet123")


async def test_expenses_clear_all_empty(mock_sheets, mock_registry) -> None:
    """Clearing an already-empty sheet returns 0."""
    mock_sheets.clear_all_transactions.return_value = 0

    body, status = await _call("DELETE", "/api/expenses", mock_sheets, mock_registry)
    assert status == 200
    assert body["deleted"] == 0


# ── GET /api/export ───────────────────────────────────────────────────────────


async def test_export_returns_csv(mock_sheets, mock_registry) -> None:
    """GET /api/export returns CSV bytes with correct content."""
    mock_sheets.get_transactions.return_value = [
        _make_record(category="food", description="lunch"),
    ]

    raw, status = await _call(
        "GET",
        "/api/export",
        mock_sheets,
        mock_registry,
        args={"start": "2026-03-01", "end": "2026-03-31"},
    )
    assert status == 200
    assert isinstance(raw, bytes)
    text = raw.decode("utf-8")
    assert "id,timestamp" in text
    assert "food" in text
    assert "lunch" in text


async def test_export_invalid_date(mock_sheets, mock_registry) -> None:
    body, status = await _call(
        "GET",
        "/api/export",
        mock_sheets,
        mock_registry,
        args={"start": "not-a-date"},
    )
    assert status == 400
    assert "error" in body


async def test_export_default_date_range(mock_sheets, mock_registry) -> None:
    """Without start/end params the export defaults to the current month."""
    mock_sheets.get_transactions.return_value = []

    raw, status = await _call("GET", "/api/export", mock_sheets, mock_registry)
    assert status == 200
    assert isinstance(raw, bytes)
    # Header row always present
    assert b"id,timestamp" in raw


# ── GET /api/categories ───────────────────────────────────────────────────────


async def test_categories_get_returns_list(mock_sheets, mock_registry) -> None:
    """GET /api/categories returns all user categories with subcategories."""
    mock_sheets.get_categories.return_value = [
        UserCategory(slug="food", label="Food & Drinks", subcategories=[
            UserSubcategory(slug="restaurant", label="Restaurant", budget=100.0),
            UserSubcategory(slug="groceries", label="Groceries", budget=None),
        ]),
        UserCategory(slug="transport", label="Transport", subcategories=[]),
    ]
    body, status = await _call("GET", "/api/categories", mock_sheets, mock_registry)
    assert status == 200
    assert "categories" in body
    slugs = [c["slug"] for c in body["categories"]]
    assert "food" in slugs
    assert "transport" in slugs
    food = next(c for c in body["categories"] if c["slug"] == "food")
    assert food["label"] == "Food & Drinks"
    assert len(food["subcategories"]) == 2
    sub_slugs = [s["slug"] for s in food["subcategories"]]
    assert "restaurant" in sub_slugs
    assert "groceries" in sub_slugs


# ── POST /api/categories ──────────────────────────────────────────────────────


async def test_categories_create_success(mock_sheets, mock_registry) -> None:
    """POST /api/categories creates a new category and returns updated list."""
    mock_sheets.get_categories.return_value = [
        UserCategory(slug="custom", label="My Custom", subcategories=[]),
    ]
    body, status = await _call(
        "POST",
        "/api/categories",
        mock_sheets,
        mock_registry,
        json_body={"label": "My Custom"},
    )
    assert status == 200
    mock_sheets.add_category.assert_called_once_with("sheet123", "my_custom", "My Custom")
    slugs = [c["slug"] for c in body["categories"]]
    assert "custom" in slugs


async def test_categories_create_no_extra_fields(mock_sheets, mock_registry) -> None:
    """POST /api/categories ignores unknown fields, creates category without budget."""
    mock_sheets.get_categories.return_value = []
    body, status = await _call(
        "POST",
        "/api/categories",
        mock_sheets,
        mock_registry,
        json_body={"label": "Entertainment"},
    )
    assert status == 200
    mock_sheets.add_category.assert_called_once_with("sheet123", "entertainment", "Entertainment")


async def test_categories_create_missing_label(mock_sheets, mock_registry) -> None:
    """POST /api/categories without label returns 400."""
    body, status = await _call(
        "POST",
        "/api/categories",
        mock_sheets,
        mock_registry,
        json_body={},
    )
    assert status == 400
    assert "error" in body


async def test_categories_create_duplicate_slug(mock_sheets, mock_registry) -> None:
    """POST /api/categories with duplicate slug returns 409."""
    mock_sheets.add_category.side_effect = ValueError("Category 'food' already exists")
    body, status = await _call(
        "POST",
        "/api/categories",
        mock_sheets,
        mock_registry,
        json_body={"label": "Food"},
    )
    assert status == 409
    assert "error" in body


# ── Unknown routes ────────────────────────────────────────────────────────────


async def test_unknown_route_returns_404(mock_sheets, mock_registry) -> None:
    body, status = await _call("GET", "/api/nonexistent", mock_sheets, mock_registry)
    assert status == 404
    assert "error" in body
