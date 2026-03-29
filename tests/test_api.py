"""Unit tests for api/routes.py — all 7 endpoints + auth edge cases.

No external services are used. Services are replaced with MagicMock /
AsyncMock fixtures so tests run offline and instantaneously.
"""

import json
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch

import flask
import pytest

from models.expense import ExpenseRecord, ExpenseSource, User, UserRole, UserStatus

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
) -> tuple[dict, int]:
    """Call handle_api_request inside a Flask test context and return (body, status)."""
    from api.routes import handle_api_request

    auth_return = {"id": TG_ID} if valid_auth else None
    all_headers = {"Authorization": "tma test", **(headers or {})}

    with (
        patch("api.routes._get_sheets", return_value=mock_sheets),
        patch("api.routes._get_registry", return_value=mock_registry),
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
    mock_sheets.get_budgets.return_value = {
        "food": 100.0,       # 40% spent → normal
        "transport": 100.0,  # 90% spent → warning
        "housing": 100.0,    # 120% spent → exceeded
    }
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


async def test_budgets_get_unspent_category(mock_sheets, mock_registry) -> None:
    """Categories with a budget but zero spending appear with spent=0."""
    mock_sheets.get_budgets.return_value = {"food": 200.0}
    mock_sheets.get_transactions.return_value = []
    body, status = await _call("GET", "/api/budgets", mock_sheets, mock_registry)
    assert status == 200
    assert body["budgets"][0]["spent"] == 0.0
    assert body["budgets"][0]["status"] == "normal"


# ── PUT /api/budgets ──────────────────────────────────────────────────────────


async def test_budgets_update_calls_sheets(mock_sheets, mock_registry) -> None:
    """PUT /api/budgets calls update_category_budgets and returns updated budgets."""
    mock_sheets.get_budgets.return_value = {"food": 450.0}
    mock_sheets.get_transactions.return_value = []

    body, status = await _call(
        "PUT",
        "/api/budgets",
        mock_sheets,
        mock_registry,
        json_body={"budgets": {"food": 450.0, "transport": 200.0}},
    )
    assert status == 200
    mock_sheets.update_category_budgets.assert_called_once_with(
        "sheet123", {"food": 450.0, "transport": 200.0}
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
    """Settings response contains all spec-required fields."""
    body, status = await _call("GET", "/api/settings", mock_sheets, mock_registry)
    assert status == 200
    assert body["telegram_id"] == TG_ID
    assert body["display_name"] == "Alice"
    assert body["base_currency"] == "USD"
    assert body["default_currency"] == "THB"
    assert body["spreadsheet_id"] == "sheet123"
    assert body["role"] == "user"
    assert "created_at" in body


# ── PUT /api/settings ─────────────────────────────────────────────────────────


async def test_settings_update_success(mock_sheets, mock_registry, user: User) -> None:
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
    mock_registry.update_settings.assert_called_once_with(TG_ID, "EUR", "THB")
    assert body["base_currency"] == "EUR"


async def test_settings_update_invalid_currency(mock_sheets, mock_registry) -> None:
    """Invalid ISO 4217 code from registry.update_settings → 400."""
    mock_registry.update_settings.side_effect = ValueError("invalid currency")

    body, status = await _call(
        "PUT",
        "/api/settings",
        mock_sheets,
        mock_registry,
        json_body={"base_currency": "FAKE", "default_currency": "THB"},
    )
    assert status == 400
    assert "error" in body


async def test_settings_update_missing_fields(mock_sheets, mock_registry) -> None:
    body, status = await _call(
        "PUT",
        "/api/settings",
        mock_sheets,
        mock_registry,
        json_body={"base_currency": "USD"},  # default_currency missing
    )
    assert status == 400


# ── Unknown routes ────────────────────────────────────────────────────────────


async def test_unknown_route_returns_404(mock_sheets, mock_registry) -> None:
    body, status = await _call("GET", "/api/nonexistent", mock_sheets, mock_registry)
    assert status == 404
    assert "error" in body
