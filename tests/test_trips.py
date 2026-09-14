"""Tests for trip tracking: the Trip model, trip_service, and the /api/trips routes.

Storage is an in-memory fake rather than a MagicMock so the trip filtering the
API relies on is exercised for real (the same semantics FirestoreService
implements: ``trip_id=None`` no filter, ``""`` home only, otherwise that trip).
"""

from datetime import date, datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.category import UserCategory, UserSubcategory
from models.expense import ExpenseRecord, ExpenseSource, User, UserRole, UserStatus
from models.trip import Trip
from services.trip_service import resolve_active_trip, trip_totals
from tests.test_api import _call

TG_ID = 42
TODAY = date(2026, 9, 14)


# ── Fakes ────────────────────────────────────────────────────────────────────


class FakeStorage:
    """Minimal in-memory storage implementing the surface the API touches."""

    def __init__(
        self,
        records: Optional[list[ExpenseRecord]] = None,
        trips: Optional[list[Trip]] = None,
        categories: Optional[list[UserCategory]] = None,
    ) -> None:
        self.records: dict[str, ExpenseRecord] = {r.id: r for r in (records or [])}
        self.trips: dict[str, Trip] = {t.id: t for t in (trips or [])}
        self.categories = categories or []
        self.active_trip: dict[int, str] = {}
        self.recurring: list[dict] = []

    # transactions
    def get_transactions(self, user_id, since=None, until=None, limit=None, trip_id=None):
        out = list(self.records.values())
        if trip_id is not None:
            out = [r for r in out if r.trip_id == trip_id]
        if since or until:
            out = [
                r for r in out
                if not (since and r.timestamp.date() < since)
                and not (until and r.timestamp.date() > until)
            ]
        out.sort(key=lambda r: r.timestamp, reverse=True)
        return out[:limit] if limit else out

    def update_transaction(self, user_id, expense_id, updates):
        record = self.records.get(expense_id)
        if record is None:
            return None
        updated = record.model_copy(update=updates)
        self.records[expense_id] = updated
        return updated

    def set_transaction_trip(self, user_id, record_id, trip_id):
        record = self.records.get(record_id)
        if record is None:
            return False
        self.records[record_id] = record.model_copy(update={"trip_id": trip_id})
        return True

    # trips
    def get_trips(self, user_id):
        return sorted(self.trips.values(), key=lambda t: t.start_date, reverse=True)

    def get_trip(self, user_id, trip_id):
        return self.trips.get(trip_id) if trip_id else None

    def add_trip(self, user_id, trip):
        self.trips[trip.id] = trip
        return trip

    def update_trip(self, user_id, trip_id, updates):
        trip = self.trips.get(trip_id)
        if trip is None:
            return None
        patch = dict(updates)
        for key in ("start_date", "end_date"):
            if key in patch:
                patch[key] = date.fromisoformat(patch[key]) if patch[key] else None
        self.trips[trip_id] = trip.model_copy(update=patch)
        return self.trips[trip_id]

    def delete_trip(self, user_id, trip_id):
        if trip_id not in self.trips:
            return False
        self.unassign_trip(user_id, trip_id)
        del self.trips[trip_id]
        return True

    def assign_transactions_to_trip(self, user_id, trip_id, since, until=None, overwrite=False):
        count = 0
        for rid, r in list(self.records.items()):
            if r.recurring or r.trip_id == trip_id:
                continue
            if r.trip_id and not overwrite:
                continue
            day = r.timestamp.date()
            if day < since or (until and day > until):
                continue
            self.records[rid] = r.model_copy(update={"trip_id": trip_id})
            count += 1
        return count

    def unassign_trip(self, user_id, trip_id):
        count = 0
        for rid, r in list(self.records.items()):
            if r.trip_id == trip_id:
                self.records[rid] = r.model_copy(update={"trip_id": ""})
                count += 1
        return count

    def set_active_trip(self, telegram_id, trip_id):
        self.active_trip[telegram_id] = trip_id
        return True

    # categories / recurring (used by budgets and the pace block)
    def get_categories(self, user_id):
        return self.categories

    def get_budgets(self, user_id):
        return {
            c.slug: sum(s.budget or 0.0 for s in c.subcategories)
            for c in self.categories
        }

    def get_recurring(self, user_id):
        return self.recurring


def _user(**kwargs) -> User:
    defaults = dict(
        telegram_id=TG_ID,
        display_name="Alice",
        spreadsheet_id=str(TG_ID),
        base_currency="USD",
        default_currency="USD",
        role=UserRole.user,
        status=UserStatus.active,
        created_at=datetime(2026, 1, 1),
    )
    defaults.update(kwargs)
    return User(**defaults)


def _record(day: int, amount: float = 10.0, trip_id: str = "", **kwargs) -> ExpenseRecord:
    defaults = dict(
        amount_local=amount,
        local_currency="USD",
        amount_base=amount,
        base_currency="USD",
        fx_rate=1.0,
        category="food",
        subcategory="restaurant",
        description="lunch",
        source=ExpenseSource.text,
        timestamp=datetime(2026, 9, day, 12, 0, 0),
        trip_id=trip_id,
    )
    defaults.update(kwargs)
    return ExpenseRecord(**defaults)


def _trip(**kwargs) -> Trip:
    defaults = dict(id="tripabcd", name="Georgia", start_date=date(2026, 9, 10))
    defaults.update(kwargs)
    return Trip(**defaults)


def _registry_for(user: User) -> AsyncMock:
    m = AsyncMock()
    m.get_user.return_value = user
    return m


# ── Model ────────────────────────────────────────────────────────────────────


def test_trip_rejects_inverted_range() -> None:
    with pytest.raises(ValueError):
        Trip(name="x", start_date=date(2026, 9, 10), end_date=date(2026, 9, 1))


def test_trip_rejects_empty_name() -> None:
    with pytest.raises(ValueError):
        Trip(name="   ", start_date=date(2026, 9, 10))


def test_trip_covers_and_day_count() -> None:
    trip = _trip(end_date=date(2026, 9, 20))
    assert trip.covers(date(2026, 9, 10))
    assert trip.covers(date(2026, 9, 20))
    assert not trip.covers(date(2026, 9, 9))
    assert not trip.covers(date(2026, 9, 21))
    assert trip.total_days() == 11
    assert not trip.is_open


def test_open_trip_counts_days_up_to_today() -> None:
    trip = _trip()
    assert trip.is_open
    assert trip.total_days() is None
    assert trip.day_count(TODAY) == 5


def test_trip_firestore_round_trip() -> None:
    trip = _trip(end_date=date(2026, 9, 20), budget=1500.0, trip_currency="gel")
    restored = Trip.from_firestore_dict(trip.to_firestore_dict())
    assert restored.model_dump() == trip.model_dump()
    assert restored.trip_currency == "GEL"


def test_open_trip_round_trips_with_empty_end_date() -> None:
    """An open trip stores end_date as "" and must come back as None, not a crash."""
    restored = Trip.from_firestore_dict(_trip().to_firestore_dict())
    assert restored.end_date is None


def test_expense_record_defaults_to_no_trip() -> None:
    """Records written before trips existed still parse."""
    record = ExpenseRecord.from_firestore_dict({
        "amount_local": 1.0, "local_currency": "USD", "amount_base": 1.0,
        "base_currency": "USD", "fx_rate": 1.0, "category": "food",
        "description": "x", "source": "text",
    })
    assert record.trip_id == ""


# ── trip_service ─────────────────────────────────────────────────────────────


def test_resolve_active_trip_returns_running_trip() -> None:
    trip = _trip()
    storage = FakeStorage(trips=[trip])
    user = _user(active_trip_id=trip.id)
    assert resolve_active_trip(storage, user, TODAY) is trip


def test_resolve_active_trip_clears_finished_pointer() -> None:
    """A trip whose end date has passed stops swallowing new expenses."""
    trip = _trip(end_date=date(2026, 9, 12))
    storage = FakeStorage(trips=[trip])
    user = _user(active_trip_id=trip.id)

    assert resolve_active_trip(storage, user, TODAY) is None
    assert user.active_trip_id == ""
    assert storage.active_trip[TG_ID] == ""


def test_resolve_active_trip_clears_deleted_pointer() -> None:
    storage = FakeStorage()
    user = _user(active_trip_id="gone1234")
    assert resolve_active_trip(storage, user, TODAY) is None
    assert user.active_trip_id == ""


def test_trip_totals_budget_progress() -> None:
    trip = _trip(budget=100.0)
    stats = trip_totals(trip, [_record(10, 30.0), _record(11, 20.0)], TODAY)
    assert stats["total_base"] == 50.0
    assert stats["transaction_count"] == 2
    assert stats["days"] == 5
    assert stats["daily_average"] == 10.0
    assert stats["budget_remaining"] == 50.0
    assert stats["budget_percentage"] == 50.0


# ── GET /api/trips ───────────────────────────────────────────────────────────


async def test_trips_list_includes_totals_and_active_flag() -> None:
    trip = _trip()
    user = _user(active_trip_id=trip.id)
    storage = FakeStorage(
        records=[_record(10, 30.0, trip_id=trip.id), _record(11, 12.0), _record(12, 8.0, trip_id=trip.id)],
        trips=[trip],
    )
    body, status = await _call("GET", "/api/trips", storage, _registry_for(user))

    assert status == 200
    assert body["active_trip_id"] == trip.id
    assert len(body["trips"]) == 1
    entry = body["trips"][0]
    assert entry["name"] == "Georgia"
    assert entry["total_base"] == pytest.approx(38.0)  # home expense excluded
    assert entry["transaction_count"] == 2
    assert entry["is_active"] is True


async def test_trips_list_is_501_on_sheets_backend() -> None:
    storage = MagicMock()
    storage.get_trips.side_effect = NotImplementedError
    body, status = await _call("GET", "/api/trips", storage, _registry_for(_user()))
    assert status == 501


# ── POST /api/trips ──────────────────────────────────────────────────────────


async def test_create_trip_activates_and_backfills() -> None:
    user = _user()
    in_window = _record(11, 25.0)
    before_trip = _record(1, 99.0)
    storage = FakeStorage(records=[in_window, before_trip])
    body, status = await _call(
        "POST", "/api/trips", storage, _registry_for(user),
        json_body={
            "name": "Georgia",
            "start_date": "2026-09-10",
            "budget": 500,
            "activate": True,
            "assign_existing": True,
        },
    )

    assert status == 201
    trip_id = body["trip"]["id"]
    assert body["assigned"] == 1                      # only the 11 Sep expense
    assert body["trip"]["total_base"] == pytest.approx(25.0)
    assert storage.active_trip[TG_ID] == trip_id
    assert storage.records[in_window.id].trip_id == trip_id
    assert storage.records[before_trip.id].trip_id == ""


async def test_create_trip_does_not_backfill_recurring_expenses() -> None:
    """Rent keeps being paid at home while you travel — it is not trip spending."""
    user = _user()
    rent = _record(11, 800.0, category="housing", recurring=True, recurring_template_id="t1")
    storage = FakeStorage(records=[rent, _record(11, 25.0)])
    body, status = await _call(
        "POST", "/api/trips", storage, _registry_for(user),
        json_body={"name": "Georgia", "start_date": "2026-09-10", "assign_existing": True},
    )

    assert status == 201
    assert body["assigned"] == 1
    assert storage.records[rent.id].trip_id == ""


async def test_create_trip_requires_a_name() -> None:
    body, status = await _call(
        "POST", "/api/trips", FakeStorage(), _registry_for(_user()), json_body={"name": "  "}
    )
    assert status == 400


async def test_create_trip_rejects_bad_date() -> None:
    body, status = await _call(
        "POST", "/api/trips", FakeStorage(), _registry_for(_user()),
        json_body={"name": "Georgia", "start_date": "10.09.2026"},
    )
    assert status == 400


# ── PUT /api/trips/:id ───────────────────────────────────────────────────────


async def test_update_trip_finishes_it_and_clears_active_pointer() -> None:
    trip = _trip()
    user = _user(active_trip_id=trip.id)
    storage = FakeStorage(trips=[trip])

    body, status = await _call(
        "PUT", f"/api/trips/{trip.id}", storage, _registry_for(user),
        json_body={"end_date": "2026-09-13", "active": False},
    )

    assert status == 200
    assert body["end_date"] == "2026-09-13"
    assert body["is_active"] is False
    assert storage.active_trip[TG_ID] == ""


async def test_update_trip_rejects_end_before_start() -> None:
    trip = _trip()
    storage = FakeStorage(trips=[trip])
    body, status = await _call(
        "PUT", f"/api/trips/{trip.id}", storage, _registry_for(_user()),
        json_body={"end_date": "2026-09-01"},
    )
    assert status == 400
    assert storage.trips[trip.id].end_date is None


async def test_update_missing_trip_returns_404() -> None:
    body, status = await _call(
        "PUT", "/api/trips/nope", FakeStorage(), _registry_for(_user()), json_body={"name": "x"}
    )
    assert status == 404


# ── DELETE /api/trips/:id ────────────────────────────────────────────────────


async def test_delete_trip_keeps_expenses_but_detaches_them() -> None:
    trip = _trip()
    user = _user(active_trip_id=trip.id)
    tagged = _record(11, 25.0, trip_id=trip.id)
    storage = FakeStorage(records=[tagged], trips=[trip])

    body, status = await _call("DELETE", f"/api/trips/{trip.id}", storage, _registry_for(user))

    assert status == 200
    assert body["detached_expenses"] == 1
    assert trip.id not in storage.trips
    assert storage.records[tagged.id].trip_id == ""
    assert storage.active_trip[TG_ID] == ""


# ── POST /api/trips/:id/assign ───────────────────────────────────────────────


async def test_assign_backfills_past_trip_from_its_dates() -> None:
    trip = _trip(start_date=date(2026, 9, 5), end_date=date(2026, 9, 8))
    storage = FakeStorage(
        records=[_record(4, 10.0), _record(6, 20.0), _record(7, 30.0), _record(9, 40.0)],
        trips=[trip],
    )
    body, status = await _call(
        "POST", f"/api/trips/{trip.id}/assign", storage, _registry_for(_user()), json_body={}
    )

    assert status == 200
    assert body["assigned"] == 2
    assert body["trip"]["total_base"] == pytest.approx(50.0)


async def test_assign_skips_expenses_already_in_another_trip() -> None:
    trip = _trip(start_date=date(2026, 9, 5), end_date=date(2026, 9, 8))
    storage = FakeStorage(records=[_record(6, 20.0, trip_id="other123")], trips=[trip])

    body, status = await _call(
        "POST", f"/api/trips/{trip.id}/assign", storage, _registry_for(_user()), json_body={}
    )
    assert body["assigned"] == 0

    body, status = await _call(
        "POST", f"/api/trips/{trip.id}/assign", storage, _registry_for(_user()),
        json_body={"overwrite": True},
    )
    assert body["assigned"] == 1


# ── Reports filtered by trip ─────────────────────────────────────────────────


async def test_summary_scoped_to_trip_uses_trip_date_range() -> None:
    trip = _trip(start_date=date(2026, 9, 10), end_date=date(2026, 9, 12), budget=100.0)
    storage = FakeStorage(
        records=[
            _record(10, 30.0, trip_id=trip.id),
            _record(11, 20.0, trip_id=trip.id, category="transport"),
            _record(11, 70.0),          # home expense in the same window
            _record(20, 15.0),          # outside the trip
        ],
        trips=[trip],
    )
    body, status = await _call(
        "GET", f"/api/trips/{trip.id}/summary", storage, _registry_for(_user())
    )

    assert status == 200
    assert body["period"] == "trip"
    assert body["date_range"] == {"start": "2026-09-10", "end": "2026-09-12"}
    assert body["total_base"] == pytest.approx(50.0)
    assert {c["category"] for c in body["by_category"]} == {"food", "transport"}
    assert body["trip"]["name"] == "Georgia"
    assert body["trip"]["budget_percentage"] == 50.0


async def test_summary_for_missing_trip_returns_404() -> None:
    body, status = await _call(
        "GET", "/api/trips/nope/summary", FakeStorage(), _registry_for(_user())
    )
    assert status == 404


async def test_summary_counts_trip_and_home_expenses_together() -> None:
    trip = _trip()
    storage = FakeStorage(
        records=[_record(10, 30.0, trip_id=trip.id), _record(11, 20.0)],
        trips=[trip],
    )
    body, status = await _call(
        "GET", "/api/summary", storage, _registry_for(_user()), args={"period": "year"}
    )

    assert status == 200
    assert body["total_base"] == pytest.approx(50.0)
    assert body["transaction_count"] == 2


async def test_expenses_can_be_filtered_by_trip_or_home() -> None:
    trip = _trip()
    storage = FakeStorage(
        records=[_record(10, 30.0, trip_id=trip.id), _record(11, 20.0)],
        trips=[trip],
    )
    registry = _registry_for(_user())

    body, _ = await _call("GET", "/api/expenses", storage, registry, args={"trip_id": trip.id})
    assert [e["amount_base"] for e in body["expenses"]] == [30.0]
    assert body["expenses"][0]["trip_id"] == trip.id

    body, _ = await _call("GET", "/api/expenses", storage, registry, args={"trip_id": "none"})
    assert [e["amount_base"] for e in body["expenses"]] == [20.0]

    body, _ = await _call("GET", "/api/expenses", storage, registry)
    assert body["total"] == 2


async def test_budgets_count_trip_spending_and_report_its_share() -> None:
    """Budgets cover every expense; the trip part is reported separately."""
    trip = _trip()
    categories = [
        UserCategory(
            slug="food",
            label="Food & Drinks",
            budget=100.0,
            subcategories=[UserSubcategory(slug="restaurant", label="Restaurant", budget=100.0)],
        )
    ]
    storage = FakeStorage(
        records=[_record(10, 90.0, trip_id=trip.id), _record(11, 20.0)],
        trips=[trip],
        categories=categories,
    )
    body, status = await _call("GET", "/api/budgets", storage, _registry_for(_user()))

    assert status == 200
    food = next(b for b in body["budgets"] if b["category"] == "food")
    assert food["spent"] == pytest.approx(110.0)
    assert food["status"] == "exceeded"
    assert body["total_spent"] == pytest.approx(110.0)
    assert body["total_spent_trip"] == pytest.approx(90.0)


async def test_patch_expense_can_move_it_into_a_trip() -> None:
    trip = _trip()
    record = _record(11, 20.0)
    storage = FakeStorage(records=[record], trips=[trip])

    body, status = await _call(
        "PATCH", f"/api/expenses/{record.id}", storage, _registry_for(_user()),
        json_body={
            "description": "lunch",
            "amount_local": 20.0,
            "local_currency": "USD",
            "category": "food",
            "subcategory": "restaurant",
            "date": "2026-09-11",
            "trip_id": trip.id,
        },
    )

    assert status == 200
    assert body["trip_id"] == trip.id
    assert storage.records[record.id].trip_id == trip.id


async def test_export_has_a_trip_column() -> None:
    trip = _trip()
    storage = FakeStorage(records=[_record(11, 20.0, trip_id=trip.id)], trips=[trip])
    body, status = await _call(
        "GET", "/api/export", storage, _registry_for(_user()),
        args={"start": "2026-09-01", "end": "2026-09-30"},
    )

    assert status == 200
    text = body.decode("utf-8")
    assert text.splitlines()[0].endswith(",trip")
    assert "Georgia" in text


# ── Bot: /trip ───────────────────────────────────────────────────────────────


def test_start_trip_creates_and_activates() -> None:
    from handlers.trips import _start_trip

    user = _user()
    storage = FakeStorage()
    text, _ = _start_trip(storage, user, "Georgia")

    assert len(storage.trips) == 1
    trip = next(iter(storage.trips.values()))
    assert trip.name == "Georgia"
    assert trip.start_date == date.today()
    assert trip.is_open
    assert storage.active_trip[TG_ID] == trip.id
    assert user.active_trip_id == trip.id
    assert "Georgia" in text


def test_starting_a_second_trip_finishes_the_first() -> None:
    """Two trips can't both collect expenses, so the previous one is closed."""
    from handlers.trips import _start_trip

    user = _user()
    storage = FakeStorage()
    _start_trip(storage, user, "Georgia")
    first_id = user.active_trip_id

    text, _ = _start_trip(storage, user, "Armenia")

    assert storage.trips[first_id].end_date == date.today()
    assert user.active_trip_id != first_id
    assert "Finished" in text


def test_end_trip_reports_totals_and_stops_tagging() -> None:
    from handlers.trips import _end_active_trip

    trip = _trip()
    user = _user(active_trip_id=trip.id)
    storage = FakeStorage(records=[_record(10, 30.0, trip_id=trip.id)], trips=[trip])

    text, _ = _end_active_trip(storage, user)

    assert storage.trips[trip.id].end_date == date.today()
    assert user.active_trip_id == ""
    assert "30.00 USD" in text


def test_end_trip_without_an_active_one_is_harmless() -> None:
    from handlers.trips import _end_active_trip

    text, _ = _end_active_trip(FakeStorage(), _user())
    assert "no active trip" in text.lower()


def test_trip_status_without_a_trip_invites_to_start_one() -> None:
    from handlers.trips import _trip_status

    text, _ = _trip_status(FakeStorage(), _user())
    assert "/trip" in text


def test_trip_status_shows_spend_for_the_active_trip() -> None:
    from handlers.trips import _trip_status

    trip = _trip(budget=100.0)
    user = _user(active_trip_id=trip.id)
    storage = FakeStorage(
        records=[_record(10, 30.0, trip_id=trip.id), _record(11, 20.0)],
        trips=[trip],
    )
    text, _ = _trip_status(storage, user)

    assert "Georgia" in text
    assert "30.00 USD" in text       # the home expense is not counted
    assert "30% used" in text


def test_trip_callback_data_fits_telegram_limit() -> None:
    """Telegram caps callback_data at 64 bytes: expense uuid + trip id must fit."""
    from handlers.trips import trip_picker_keyboard
    from handlers.callbacks import saved_keyboard

    record_id = "0123456789abcdef0123456789abcdef0123"  # uuid4 length
    trips = [_trip(id=f"trip{i:04d}", name=f"Trip {i}") for i in range(6)]

    keyboards = [
        saved_keyboard(record_id, in_trip=True),
        trip_picker_keyboard(record_id, trips, trips[0].id),
    ]
    for markup in keyboards:
        for row in markup.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode("utf-8")) <= 64, button.callback_data
