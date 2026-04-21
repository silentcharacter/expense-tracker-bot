"""Unit tests for jobs/recurring_cron.py.

All external services (SheetsService, CurrencyService) are replaced with
MagicMock / AsyncMock so tests run offline and instantaneously.
"""

import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs.recurring_cron import _build_record, _process_user, run_recurring_cron
from models.expense import ExpenseRecord, ExpenseSource, User, UserRole, UserStatus

# ── Helpers ───────────────────────────────────────────────────────────────────

TODAY = date(2026, 4, 21)


def _make_user(**kwargs) -> User:
    defaults = dict(
        telegram_id=1,
        display_name="Alice",
        spreadsheet_id="sheet1",
        base_currency="USD",
        default_currency="USD",
        role=UserRole.user,
        status=UserStatus.active,
        created_at=datetime(2026, 1, 1),
    )
    defaults.update(kwargs)
    return User(**defaults)


def _make_template(**kwargs) -> dict:
    defaults = dict(
        id="tpl-1",
        day_of_month=TODAY.day,
        amount_local=100.0,
        local_currency="USD",
        category="food",
        subcategory="",
        description="Lunch",
    )
    defaults.update(kwargs)
    return defaults


def _make_sheets(templates: list[dict], existing: list[ExpenseRecord]) -> MagicMock:
    m = MagicMock()
    m.get_recurring.return_value = templates
    m.get_transactions.return_value = existing
    m.append_transaction.return_value = None
    return m


def _make_currency(amount_base: float = 100.0, fx_rate: float = 1.0) -> AsyncMock:
    m = AsyncMock()
    m.convert = AsyncMock(return_value=(amount_base, fx_rate))
    return m


# ── _build_record ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_record_same_currency():
    """No FX call when local == base currency."""
    user = _make_user(base_currency="USD", default_currency="USD")
    currency = _make_currency()
    item = _make_template(local_currency="USD", amount_local=50.0)

    record = await _build_record(currency, user, item, TODAY)

    assert record is not None
    assert record.amount_local == 50.0
    assert record.amount_base == 50.0
    assert record.fx_rate == 1.0
    assert record.recurring is True
    assert record.recurring_template_id == "tpl-1"
    currency.convert.assert_not_called()


@pytest.mark.asyncio
async def test_build_record_cross_currency():
    """FX conversion called when currencies differ."""
    user = _make_user(base_currency="USD", default_currency="THB")
    currency = _make_currency(amount_base=2.94, fx_rate=0.02940)
    item = _make_template(local_currency="THB", amount_local=100.0)

    record = await _build_record(currency, user, item, TODAY)

    assert record is not None
    assert record.amount_local == 100.0
    assert record.local_currency == "THB"
    assert record.amount_base == pytest.approx(2.94)
    assert record.fx_rate == pytest.approx(0.02940)
    currency.convert.assert_awaited_once_with(100.0, "THB", "USD")


@pytest.mark.asyncio
async def test_build_record_fx_failure_fallback():
    """When FX fails, falls back to local == base currency."""
    user = _make_user(base_currency="USD")
    currency = AsyncMock()
    currency.convert = AsyncMock(side_effect=RuntimeError("network error"))
    item = _make_template(local_currency="EUR", amount_local=80.0)

    record = await _build_record(currency, user, item, TODAY)

    assert record is not None
    assert record.local_currency == record.base_currency == "USD"
    assert record.amount_base == 80.0
    assert record.fx_rate == 1.0


@pytest.mark.asyncio
async def test_build_record_zero_amount_returns_none():
    user = _make_user()
    item = _make_template(amount_local=0.0)
    record = await _build_record(_make_currency(), user, item, TODAY)
    assert record is None


@pytest.mark.asyncio
async def test_build_record_negative_amount_returns_none():
    user = _make_user()
    item = _make_template(amount_local=-5.0)
    record = await _build_record(_make_currency(), user, item, TODAY)
    assert record is None


@pytest.mark.asyncio
async def test_build_record_invalid_amount_returns_none():
    user = _make_user()
    item = _make_template(amount_local="not-a-number")
    record = await _build_record(_make_currency(), user, item, TODAY)
    assert record is None


@pytest.mark.asyncio
async def test_build_record_uses_user_default_currency_when_template_has_none():
    """Template without local_currency falls back to user's default_currency."""
    user = _make_user(base_currency="USD", default_currency="EUR")
    currency = _make_currency(amount_base=55.0, fx_rate=0.55)
    item = _make_template(local_currency="", amount_local=100.0)

    record = await _build_record(currency, user, item, TODAY)

    assert record is not None
    currency.convert.assert_awaited_once_with(100.0, "EUR", "USD")


@pytest.mark.asyncio
async def test_build_record_sets_correct_timestamp():
    user = _make_user()
    item = _make_template()
    record = await _build_record(_make_currency(), user, item, TODAY)
    assert record is not None
    assert record.timestamp == datetime(TODAY.year, TODAY.month, TODAY.day, 0, 0, 0)


# ── _process_user ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_user_no_due_templates():
    """No templates due today → returns (0, 0) and never touches Sheets write."""
    user = _make_user()
    # day_of_month = 5, TODAY.day = 21 → not due
    templates = [_make_template(day_of_month=5)]
    sheets = _make_sheets(templates, [])
    currency = _make_currency()

    inserted, skipped, errors = await _process_user(sheets, currency, user, TODAY)

    assert (inserted, skipped) == (0, 0)
    sheets.append_transaction.assert_not_called()


@pytest.mark.asyncio
async def test_process_user_inserts_new_template():
    """Due template not yet in Transactions → inserted = 1."""
    user = _make_user()
    sheets = _make_sheets([_make_template()], [])
    currency = _make_currency()

    inserted, skipped, errors = await _process_user(sheets, currency, user, TODAY)

    assert inserted == 1
    assert skipped == 0
    sheets.append_transaction.assert_called_once()


@pytest.mark.asyncio
async def test_process_user_skips_already_inserted():
    """Template already materialised this month → skipped = 1."""
    user = _make_user()
    existing_record = ExpenseRecord(
        amount_local=100.0,
        local_currency="USD",
        amount_base=100.0,
        base_currency="USD",
        fx_rate=1.0,
        category="food",
        description="Lunch",
        source=ExpenseSource.text,
        recurring=True,
        recurring_template_id="tpl-1",
    )
    sheets = _make_sheets([_make_template()], [existing_record])
    currency = _make_currency()

    inserted, skipped, errors = await _process_user(sheets, currency, user, TODAY)

    assert inserted == 0
    assert skipped == 1
    sheets.append_transaction.assert_not_called()


@pytest.mark.asyncio
async def test_process_user_skips_template_without_id():
    """Template missing id is skipped without crash."""
    user = _make_user()
    item = _make_template()
    item["id"] = ""
    sheets = _make_sheets([item], [])
    currency = _make_currency()

    inserted, skipped, errors = await _process_user(sheets, currency, user, TODAY)

    assert inserted == 0
    assert skipped == 0
    sheets.append_transaction.assert_not_called()


@pytest.mark.asyncio
async def test_process_user_multiple_templates_partial_skip():
    """Two templates due: one already inserted, one new."""
    user = _make_user()
    tpl1 = _make_template(id="tpl-1")
    tpl2 = _make_template(id="tpl-2")

    existing_record = ExpenseRecord(
        amount_local=50.0,
        local_currency="USD",
        amount_base=50.0,
        base_currency="USD",
        fx_rate=1.0,
        category="food",
        description="Coffee",
        source=ExpenseSource.text,
        recurring=True,
        recurring_template_id="tpl-1",
    )
    sheets = _make_sheets([tpl1, tpl2], [existing_record])
    currency = _make_currency()

    inserted, skipped, errors = await _process_user(sheets, currency, user, TODAY)

    assert inserted == 1
    assert skipped == 1
    sheets.append_transaction.assert_called_once()


# ── run_recurring_cron ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_recurring_cron_counts_summary():
    """Happy path: two users, one insert each → summary correct."""
    user1 = _make_user(telegram_id=1, spreadsheet_id="s1")
    user2 = _make_user(telegram_id=2, spreadsheet_id="s2")

    sheets = MagicMock()
    sheets.get_all_active_users.return_value = [user1, user2]
    sheets.get_recurring.return_value = [_make_template()]
    sheets.get_transactions.return_value = []
    sheets.append_transaction.return_value = None

    currency = _make_currency()

    summary = await run_recurring_cron(sheets=sheets, currency=currency, today=TODAY)

    assert summary["users"] == 2
    assert summary["inserted"] == 2
    assert summary["skipped"] == 0
    assert summary["errors"] == 0


@pytest.mark.asyncio
async def test_run_recurring_cron_get_users_fails():
    """If get_all_active_users raises, errors=1 and no crash."""
    sheets = MagicMock()
    sheets.get_all_active_users.side_effect = RuntimeError("Sheets down")

    summary = await run_recurring_cron(sheets=sheets, currency=_make_currency(), today=TODAY)

    assert summary["errors"] == 1
    assert summary["users"] == 0


@pytest.mark.asyncio
async def test_run_recurring_cron_one_user_fails_others_continue():
    """Exception for one user is counted as error; other users still processed."""
    user1 = _make_user(telegram_id=1, spreadsheet_id="s1")
    user2 = _make_user(telegram_id=2, spreadsheet_id="s2")

    sheets = MagicMock()
    sheets.get_all_active_users.return_value = [user1, user2]

    # user1 will fail during get_recurring, user2 succeeds
    def get_recurring(spreadsheet_id: str) -> list:
        if spreadsheet_id == "s1":
            raise RuntimeError("permission denied")
        return [_make_template()]

    sheets.get_recurring.side_effect = get_recurring
    sheets.get_transactions.return_value = []
    sheets.append_transaction.return_value = None

    summary = await run_recurring_cron(sheets=sheets, currency=_make_currency(), today=TODAY)

    assert summary["users"] == 2
    assert summary["errors"] == 1
    assert summary["inserted"] == 1


@pytest.mark.asyncio
async def test_run_recurring_cron_no_users():
    """Empty user list → all counts are zero."""
    sheets = MagicMock()
    sheets.get_all_active_users.return_value = []

    summary = await run_recurring_cron(sheets=sheets, currency=_make_currency(), today=TODAY)

    assert summary == {"users": 0, "inserted": 0, "skipped": 0, "errors": 0}
