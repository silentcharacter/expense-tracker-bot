"""Per-user timezone: resolution, storage format and the "just after midnight" scenario.

Frozen clock used throughout: 2026-11-15 17:30 UTC (a Sunday). That is
already 00:30 on Monday 2026-11-16 in Asia/Bangkok (UTC+7), while the server
(UTC), Europe/Kyiv (19:30) and America/New_York (12:30) are still on the 15th.
"""

import logging
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.expense import ExpenseRecord, ExpenseSource, User, UserRole, UserStatus
from utils import timeutil

# Fixtures (user, mock_sheets, mock_registry, mock_currency) are reused from test_api.
from tests.test_api import (  # noqa: F401
    _call,
    _make_record,
    mock_currency,
    mock_registry,
    mock_sheets,
    user,
)

JUST_AFTER_BANGKOK_MIDNIGHT = datetime(2026, 11, 15, 17, 30, tzinfo=timezone.utc)


def _user(tz: str = "", **kwargs) -> User:
    defaults = dict(
        telegram_id=42,
        display_name="Ilya",
        spreadsheet_id="42",
        base_currency="USD",
        default_currency="USD",
        role=UserRole.user,
        status=UserStatus.active,
        timezone=tz,
    )
    defaults.update(kwargs)
    return User(**defaults)


def _freeze(monkeypatch: pytest.MonkeyPatch, at: datetime) -> None:
    monkeypatch.setattr(timeutil, "_utc_now", lambda: at)


@pytest.fixture
def after_midnight(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Server/UTC on Nov 15, Asia/Bangkok already on Nov 16 (00:30)."""
    monkeypatch.setenv("TIMEZONE", "Asia/Bangkok")
    _freeze(monkeypatch, JUST_AFTER_BANGKOK_MIDNIGHT)
    return JUST_AFTER_BANGKOK_MIDNIGHT


# ── Resolution: bot setting → TIMEZONE → Asia/Bangkok ───────────────────────


def test_default_comes_from_timezone_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    assert timeutil.default_timezone_name() == "Europe/Kyiv"
    assert str(timeutil.get_user_timezone(_user())) == "Europe/Kyiv"


def test_default_is_bangkok_when_timezone_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIMEZONE", raising=False)
    assert str(timeutil.default_tz()) == "Asia/Bangkok"
    assert timeutil.user_timezone_name(_user()) == "Asia/Bangkok"


def test_invalid_timezone_env_falls_back_to_utc_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("TIMEZONE", "Mars/Olympus_Mons")
    with caplog.at_level(logging.WARNING, logger="utils.timeutil"):
        tz = timeutil.default_tz()
    assert tz is timezone.utc
    assert "Mars/Olympus_Mons" in caplog.text


def test_user_setting_wins_over_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMEZONE", "Asia/Bangkok")
    assert str(timeutil.get_user_timezone(_user("Europe/Kyiv"))) == "Europe/Kyiv"


def test_invalid_user_setting_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMEZONE", "Asia/Bangkok")
    assert str(timeutil.get_user_timezone(_user("Not/AZone"))) == "Asia/Bangkok"
    assert str(timeutil.get_user_timezone(None)) == "Asia/Bangkok"


def test_is_valid_timezone() -> None:
    assert timeutil.is_valid_timezone("America/New_York")
    assert not timeutil.is_valid_timezone("")
    assert not timeutil.is_valid_timezone("Nowhere/Land")
    assert not timeutil.is_valid_timezone(" Europe/Kyiv")


def test_user_model_round_trips_timezone_setting() -> None:
    u = _user("Europe/Kyiv")
    assert u.to_firestore_dict()["timezone"] == "Europe/Kyiv"
    assert User.from_firestore_dict(u.to_firestore_dict()).timezone == "Europe/Kyiv"
    assert "timezone" in User.registry_headers()
    assert u.to_registry_row()[User.registry_headers().index("timezone")] == "Europe/Kyiv"
    legacy = {k: v for k, v in u.to_firestore_dict().items() if k != "timezone"}
    assert User.from_firestore_dict(legacy).timezone == ""
    assert User(**{**legacy, "timezone": None}).timezone == ""


# ── Storage format ──────────────────────────────────────────────────────────


def _expense(**kwargs) -> ExpenseRecord:
    defaults = dict(
        amount_local=1.0, local_currency="USD", amount_base=1.0, base_currency="USD",
        fx_rate=1.0, category="food", description="x", source=ExpenseSource.text,
    )
    defaults.update(kwargs)
    return ExpenseRecord(**defaults)


def test_new_expense_timestamp_is_aware_utc(after_midnight) -> None:
    r = _expense()
    assert r.timestamp == after_midnight
    assert r.timestamp.utcoffset().total_seconds() == 0
    assert r.local_date(_user("Asia/Bangkok")) == date(2026, 11, 16)
    assert r.local_date(_user("Europe/Kyiv")) == date(2026, 11, 15)


def test_legacy_naive_timestamps_are_read_as_utc() -> None:
    r = _expense(timestamp=datetime(2026, 11, 15, 17, 30))
    assert r.timestamp == JUST_AFTER_BANGKOK_MIDNIGHT
    assert r.local_date("Asia/Bangkok") == date(2026, 11, 16)


def test_firestore_round_trip_keeps_tzinfo() -> None:
    r = _expense(timestamp=JUST_AFTER_BANGKOK_MIDNIGHT)
    back = ExpenseRecord.from_firestore_dict(r.to_firestore_dict())
    assert back.timestamp.tzinfo is not None
    assert back.timestamp == JUST_AFTER_BANGKOK_MIDNIGHT


def test_start_of_day_is_local_midnight_as_utc() -> None:
    ts = timeutil.start_of_day(date(2026, 11, 16), "Asia/Bangkok")
    assert ts == datetime(2026, 11, 15, 17, 0, tzinfo=timezone.utc)
    assert timeutil.local_date(ts, "Asia/Bangkok") == date(2026, 11, 16)


# ── Just after local midnight ───────────────────────────────────────────────


def test_today_is_the_users_new_day_while_server_is_still_on_yesterday(after_midnight) -> None:
    assert after_midnight.date() == date(2026, 11, 15)  # server / UTC
    assert timeutil.user_today(_user("Asia/Bangkok")) == date(2026, 11, 16)
    assert timeutil.user_today(_user()) == date(2026, 11, 16)  # default TIMEZONE
    assert timeutil.user_today(_user("Europe/Kyiv")) == date(2026, 11, 15)
    assert timeutil.user_today(_user("America/New_York")) == date(2026, 11, 15)
    assert timeutil.user_now(_user("Asia/Bangkok")).time() == time(0, 30)


def test_period_and_yesterday_follow_user_day(after_midnight) -> None:
    from api.routes import _period_dates, _previous_period_dates

    bkk = _user("Asia/Bangkok")
    assert _period_dates("today", 0, bkk) == (date(2026, 11, 16), date(2026, 11, 16))
    assert _period_dates("week", 0, bkk) == (date(2026, 11, 16), date(2026, 11, 16))
    assert _period_dates("month", 0, bkk) == (date(2026, 11, 1), date(2026, 11, 16))
    # "Yesterday" for the Bangkok user is the 15th, not the 14th.
    assert _previous_period_dates("today", date(2026, 11, 16), date(2026, 11, 16)) == (
        date(2026, 11, 15), date(2026, 11, 15)
    )
    assert _period_dates("today", -1, bkk) == (date(2026, 11, 15), date(2026, 11, 15))

    kyiv = _user("Europe/Kyiv")  # still Sunday the 15th
    assert _period_dates("today", 0, kyiv) == (date(2026, 11, 15), date(2026, 11, 15))
    assert _period_dates("week", 0, kyiv) == (date(2026, 11, 9), date(2026, 11, 15))


def test_month_rolls_over_at_users_midnight(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.routes import _period_dates

    # 17:30 UTC on Nov 30 = 00:30 on Dec 1 in Bangkok, 19:30 on Nov 30 in Kyiv.
    _freeze(monkeypatch, datetime(2026, 11, 30, 17, 30, tzinfo=timezone.utc))
    assert _period_dates("month", 0, _user("Asia/Bangkok")) == (date(2026, 12, 1), date(2026, 12, 1))
    assert _period_dates("month", -1, _user("Asia/Bangkok")) == (date(2026, 11, 1), date(2026, 11, 30))
    assert _period_dates("month", 0, _user("Europe/Kyiv")) == (date(2026, 11, 1), date(2026, 11, 30))


def _registry_for(u: User) -> AsyncMock:
    m = AsyncMock()
    m.get_user.return_value = u
    return m


def _pace_records() -> list[ExpenseRecord]:
    return [
        # 23:00 Nov 15 in Bangkok — "yesterday" for a Bangkok user.
        _make_record(id="late", amount_base=200.0, category="food",
                     timestamp=datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc)),
        # 00:10 Nov 16 in Bangkok — "today" for a Bangkok user.
        _make_record(id="early", amount_base=100.0, category="food",
                     timestamp=datetime(2026, 11, 15, 17, 10, tzinfo=timezone.utc)),
    ]


async def test_summary_and_pace_after_midnight_bangkok(
    after_midnight, mock_sheets, mock_currency  # noqa: F811
) -> None:
    bkk = _user("Asia/Bangkok")
    mock_sheets.get_transactions.return_value = _pace_records()
    mock_sheets.get_recurring.return_value = []
    mock_sheets.get_budgets.return_value = {"food": 1000.0}

    body, status = await _call(
        "GET", "/api/summary", mock_sheets, _registry_for(bkk),
        args={"period": "month"}, mock_currency=mock_currency,
    )

    assert status == 200
    kwargs = mock_sheets.get_transactions.call_args.kwargs
    assert (kwargs["since"], kwargs["until"]) == (date(2026, 11, 1), date(2026, 11, 16))
    assert kwargs["tz"] is bkk
    assert {d["date"]: d["amount_base"] for d in body["daily_totals"]} == {
        "2026-11-15": 200.0, "2026-11-16": 100.0,
    }
    pace = body["spending_pace"]
    assert pace["days_elapsed"] == 15
    assert pace["today_discretionary_spent"] == pytest.approx(100.0)
    assert pace["projected_discretionary"] == pytest.approx(200.0 / 15 * 30)


async def test_summary_and_pace_same_moment_for_kyiv_user(
    after_midnight, mock_sheets, mock_currency  # noqa: F811
) -> None:
    kyiv = _user("Europe/Kyiv")
    mock_sheets.get_transactions.return_value = _pace_records()
    mock_sheets.get_recurring.return_value = []
    mock_sheets.get_budgets.return_value = {"food": 1000.0}

    body, status = await _call(
        "GET", "/api/summary", mock_sheets, _registry_for(kyiv),
        args={"period": "month"}, mock_currency=mock_currency,
    )

    assert status == 200
    kwargs = mock_sheets.get_transactions.call_args.kwargs
    assert kwargs["until"] == date(2026, 11, 15)
    assert [d["date"] for d in body["daily_totals"]] == ["2026-11-15"]
    pace = body["spending_pace"]
    assert pace["days_elapsed"] == 14
    assert pace["today_discretionary_spent"] == pytest.approx(300.0)


async def test_expense_timestamps_are_serialised_in_user_zone(
    after_midnight, mock_sheets, mock_currency  # noqa: F811
) -> None:
    mock_sheets.get_transactions.return_value = _pace_records()
    body, status = await _call(
        "GET", "/api/expenses", mock_sheets, _registry_for(_user("Asia/Bangkok")),
        mock_currency=mock_currency,
    )
    assert status == 200
    stamps = {e["id"]: e["timestamp"] for e in body["expenses"]}
    assert stamps["early"].startswith("2026-11-16T00:10")
    assert stamps["early"].endswith("+07:00")
    assert stamps["late"].startswith("2026-11-15T23:00")


def test_firestore_date_filter_uses_user_zone() -> None:
    from services.firestore_service import FirestoreService

    svc = FirestoreService.__new__(FirestoreService)  # no Firestore client needed
    svc._get_all_transactions = lambda user_id: _pace_records()
    got = svc.get_transactions("42", since=date(2026, 11, 16), until=date(2026, 11, 16),
                               tz=_user("Asia/Bangkok"))
    assert [r.id for r in got] == ["early"]
    got = svc.get_transactions("42", since=date(2026, 11, 15), until=date(2026, 11, 15),
                               tz=_user("Europe/Kyiv"))
    assert sorted(r.id for r in got) == ["early", "late"]


# ── Settings ────────────────────────────────────────────────────────────────


async def test_settings_get_reports_effective_timezone(
    after_midnight, mock_sheets  # noqa: F811
) -> None:
    body, status = await _call("GET", "/api/settings", mock_sheets, _registry_for(_user()))
    assert status == 200
    assert body["timezone"] == "Asia/Bangkok"
    assert body["timezone_is_default"] is True
    assert body["today"] == "2026-11-16"


async def test_settings_put_passes_timezone_to_registry(mock_sheets) -> None:  # noqa: F811
    registry = _registry_for(_user())
    registry.update_settings.return_value = _user("Europe/Kyiv")
    body, status = await _call(
        "PUT", "/api/settings", mock_sheets, registry, json_body={"timezone": "Europe/Kyiv"}
    )
    assert status == 200
    assert registry.update_settings.call_args.kwargs["timezone"] == "Europe/Kyiv"
    assert body["timezone"] == "Europe/Kyiv"
    assert body["timezone_is_default"] is False


async def test_registry_rejects_unknown_timezone_and_stores_valid_one() -> None:
    from services.user_registry import UserRegistry

    storage = MagicMock()
    storage.find_user.return_value = _user()
    registry = UserRegistry(sheets_service=storage)

    with pytest.raises(ValueError):
        await registry.update_settings(42, timezone="Mars/Base")
    storage.update_user_settings.assert_not_called()

    updated = await registry.update_settings(42, timezone="Europe/Kyiv")
    assert updated.timezone == "Europe/Kyiv"
    assert storage.update_user_settings.call_args.kwargs["timezone"] == "Europe/Kyiv"


# ── Crons: each user on their own calendar ──────────────────────────────────


async def test_recurring_cron_uses_each_users_day(after_midnight) -> None:
    from jobs.recurring_cron import run_recurring_cron

    bkk = _user("Asia/Bangkok", telegram_id=1, spreadsheet_id="1")
    kyiv = _user("Europe/Kyiv", telegram_id=2, spreadsheet_id="2")
    sheets = MagicMock()
    sheets.get_all_active_users.return_value = [bkk, kyiv]
    sheets.get_recurring.return_value = [{
        "id": "rent", "day_of_month": 16, "amount_local": 500.0, "local_currency": "USD",
        "category": "housing", "subcategory": "", "description": "Rent",
    }]
    sheets.get_transactions.return_value = []
    currency = AsyncMock()
    currency.convert = AsyncMock(return_value=(500.0, 1.0))

    summary = await run_recurring_cron(sheets=sheets, currency=currency)

    # Due on the 16th: only the Bangkok user is already there.
    assert summary["inserted"] == 1
    spreadsheet_id, record = sheets.append_transaction.call_args.args
    assert spreadsheet_id == "1"
    assert record.local_date(bkk) == date(2026, 11, 16)


async def test_weekly_summary_uses_each_users_week(after_midnight) -> None:
    from jobs.weekly_summary_cron import run_weekly_summary

    bkk = _user("Asia/Bangkok", telegram_id=1, spreadsheet_id="1")
    ny = _user("America/New_York", telegram_id=2, spreadsheet_id="2")
    sheets = MagicMock()
    sheets.get_all_active_users.return_value = [bkk, ny]
    sheets.get_transactions.return_value = []  # nothing spent → skipped after first read
    bot = MagicMock()
    bot.__aenter__ = AsyncMock(return_value=bot)
    bot.__aexit__ = AsyncMock(return_value=False)

    await run_weekly_summary(sheets=sheets, bot=bot)

    calls = {c.args[0]: c.kwargs for c in sheets.get_transactions.call_args_list}
    # Monday 00:30 in Bangkok → last week is Nov 9–15.
    assert (calls["1"]["since"], calls["1"]["until"]) == (date(2026, 11, 9), date(2026, 11, 15))
    # Still Sunday in New York → the last complete week is Nov 2–8.
    assert (calls["2"]["since"], calls["2"]["until"]) == (date(2026, 11, 2), date(2026, 11, 8))


async def test_budget_alert_month_starts_at_users_midnight(monkeypatch: pytest.MonkeyPatch) -> None:
    from handlers.budget_alerts import check_and_send_budget_alert

    # 00:30 Dec 1 in Bangkok, still Nov 30 on the server.
    _freeze(monkeypatch, datetime(2026, 11, 30, 17, 30, tzinfo=timezone.utc))
    bkk = _user("Asia/Bangkok")
    sheets = MagicMock()
    sheets.get_transactions.return_value = []
    sheets.get_categories.return_value = []
    await check_and_send_budget_alert(MagicMock(), bkk, _expense(), sheets)
    kwargs = sheets.get_transactions.call_args.kwargs
    assert (kwargs["since"], kwargs["until"]) == (date(2026, 12, 1), date(2026, 12, 1))
