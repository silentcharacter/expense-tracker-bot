"""Integration tests for FirestoreService against the local Firestore emulator.

Requires the emulator to be running:
  firebase emulators:start --only firestore --project expense-bot-489609

Run:
  pytest tests/test_firestore_integration.py -m integration -v
"""

import pytest

from datetime import date, datetime

from models.expense import ExpenseRecord, ExpenseSource
from models.category import CATEGORIES
from models.trip import Trip

TEST_USER_ID = "test_integration_999"


@pytest.fixture(autouse=True)
def cleanup(firestore_service):
    """Clear all test data before each test."""
    firestore_service.clear_all_transactions(TEST_USER_ID)
    yield
    firestore_service.clear_all_transactions(TEST_USER_ID)


# ── append_transaction ────────────────────────────────────────────────────────

@pytest.mark.integration
def test_append_transaction_writes_and_reads_back(firestore_service):
    """append_transaction should write a record that can be read back intact."""
    record = ExpenseRecord(
        amount_local=42.50,
        local_currency="THB",
        amount_base=1.25,
        base_currency="USD",
        fx_rate=0.029,
        category="food",
        subcategory="cafe",
        description="integration test coffee",
        source=ExpenseSource.text,
        raw_input="42.5 бат кофе",
    )

    firestore_service.append_transaction(TEST_USER_ID, record)
    recent = firestore_service.get_transactions(TEST_USER_ID, limit=5)
    got = next((r for r in recent if r.id == record.id), None)

    assert got is not None, f"Record {record.id} not found after append"
    assert got.amount_local == pytest.approx(record.amount_local)
    assert got.local_currency == record.local_currency
    assert got.amount_base == pytest.approx(record.amount_base)
    assert got.base_currency == record.base_currency
    assert got.fx_rate == pytest.approx(record.fx_rate)
    assert got.category == record.category
    assert got.subcategory == record.subcategory
    assert got.description == record.description
    assert got.source == record.source
    assert got.raw_input == record.raw_input


# ── update_transaction_category ──────────────────────────────────────────────

@pytest.mark.integration
def test_update_transaction_category_changes_category(firestore_service):
    """update_transaction_category should update category/subcategory in-place."""
    record = ExpenseRecord(
        amount_local=10.00,
        local_currency="USD",
        amount_base=10.00,
        base_currency="USD",
        fx_rate=1.0,
        category="food",
        subcategory="cafe",
        description="integration test category update",
        source=ExpenseSource.text,
        raw_input="10 usd coffee",
    )
    firestore_service.append_transaction(TEST_USER_ID, record)

    ok = firestore_service.update_transaction_category(TEST_USER_ID, record.id, "transport", "")
    assert ok is True

    recent = firestore_service.get_transactions(TEST_USER_ID, limit=10)
    got = next((r for r in recent if r.id == record.id), None)
    assert got is not None
    assert got.category == "transport"
    assert got.subcategory == ""


@pytest.mark.integration
def test_update_transaction_category_returns_false_for_unknown_id(firestore_service):
    """update_transaction_category should return False for a non-existent ID."""
    ok = firestore_service.update_transaction_category(
        TEST_USER_ID, "00000000-0000-0000-0000-000000000000", "food", ""
    )
    assert ok is False


# ── delete_transaction ────────────────────────────────────────────────────────

@pytest.mark.integration
def test_delete_transaction_by_id(firestore_service):
    """delete_transaction_by_id should remove the record and return it."""
    record = ExpenseRecord(
        amount_local=5.00,
        local_currency="USD",
        amount_base=5.00,
        base_currency="USD",
        fx_rate=1.0,
        category="food",
        subcategory="",
        description="to be deleted",
        source=ExpenseSource.text,
        raw_input="5 usd lunch",
    )
    firestore_service.append_transaction(TEST_USER_ID, record)

    deleted = firestore_service.delete_transaction_by_id(TEST_USER_ID, record.id)
    assert deleted is not None
    assert deleted.id == record.id

    recent = firestore_service.get_transactions(TEST_USER_ID, limit=10)
    assert not any(r.id == record.id for r in recent)


@pytest.mark.integration
def test_delete_last_transaction(firestore_service):
    """delete_last_transaction should remove the most recently added record."""
    record = ExpenseRecord(
        amount_local=7.00,
        local_currency="USD",
        amount_base=7.00,
        base_currency="USD",
        fx_rate=1.0,
        category="transport",
        subcategory="",
        description="last tx test",
        source=ExpenseSource.text,
        raw_input="7 usd taxi",
    )
    firestore_service.append_transaction(TEST_USER_ID, record)

    deleted = firestore_service.delete_last_transaction(TEST_USER_ID)
    assert deleted is not None
    assert deleted.id == record.id


# ── categories ────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_ensure_categories_seeds_defaults(firestore_service):
    """ensure_categories_sheet should seed all default categories when empty."""
    from services.firestore_service import _category_cache
    _category_cache.pop(TEST_USER_ID, None)

    firestore_service.ensure_categories_sheet(TEST_USER_ID)
    cats = firestore_service.get_categories(TEST_USER_ID)

    default_slugs = {c.slug for c in CATEGORIES}
    assert {c.slug for c in cats} == default_slugs


@pytest.mark.integration
def test_get_categories_returns_cached(firestore_service):
    """Second call within TTL should return the same list object from cache."""
    from services.firestore_service import _category_cache
    _category_cache.pop(TEST_USER_ID, None)

    firestore_service.ensure_categories_sheet(TEST_USER_ID)
    cats1 = firestore_service.get_categories(TEST_USER_ID)
    cats2 = firestore_service.get_categories(TEST_USER_ID)
    assert cats1 is cats2


# ── recurring ─────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_recurring_add_get_delete(firestore_service):
    """add_recurring / get_recurring / delete_recurring round-trip."""
    entry = {
        "id": "test-recurring-001",
        "description": "Monthly rent",
        "amount": 500.0,
        "currency": "USD",
        "category": "housing",
        "subcategory": "",
        "day_of_month": 1,
    }
    firestore_service.add_recurring(TEST_USER_ID, entry)

    entries = firestore_service.get_recurring(TEST_USER_ID)
    assert any(e["id"] == entry["id"] for e in entries)

    deleted = firestore_service.delete_recurring(TEST_USER_ID, entry["id"])
    assert deleted is True

    entries_after = firestore_service.get_recurring(TEST_USER_ID)
    assert not any(e["id"] == entry["id"] for e in entries_after)



# ── trips ─────────────────────────────────────────────────────────────────────

def _trip_record(day: int, amount: float, **kwargs) -> ExpenseRecord:
    """Expense on a fixed date, for date-range assignment tests."""
    defaults = dict(
        amount_local=amount,
        local_currency="USD",
        amount_base=amount,
        base_currency="USD",
        fx_rate=1.0,
        category="food",
        subcategory="cafe",
        description="integration trip expense",
        source=ExpenseSource.text,
        timestamp=datetime(2026, 9, day, 12, 0, 0),
    )
    defaults.update(kwargs)
    return ExpenseRecord(**defaults)


@pytest.fixture
def clean_trips(firestore_service):
    """Remove any trips left behind by a previous run."""
    for trip in firestore_service.get_trips(TEST_USER_ID):
        firestore_service.delete_trip(TEST_USER_ID, trip.id)
    yield
    for trip in firestore_service.get_trips(TEST_USER_ID):
        firestore_service.delete_trip(TEST_USER_ID, trip.id)


@pytest.mark.integration
def test_trip_add_get_update_delete(firestore_service, clean_trips):
    """Trips round-trip through Firestore, including the date-only fields."""
    trip = Trip(name="Georgia", start_date=date(2026, 9, 10), budget=1500.0)
    firestore_service.add_trip(TEST_USER_ID, trip)

    got = firestore_service.get_trip(TEST_USER_ID, trip.id)
    assert got is not None
    assert got.name == "Georgia"
    assert got.start_date == date(2026, 9, 10)
    assert got.end_date is None
    assert got.budget == pytest.approx(1500.0)

    updated = firestore_service.update_trip(
        TEST_USER_ID, trip.id, {"end_date": "2026-09-20", "name": "Georgia, autumn"}
    )
    assert updated.end_date == date(2026, 9, 20)
    assert updated.name == "Georgia, autumn"

    assert firestore_service.delete_trip(TEST_USER_ID, trip.id) is True
    assert firestore_service.get_trip(TEST_USER_ID, trip.id) is None


@pytest.mark.integration
def test_get_transactions_filters_by_trip(firestore_service, clean_trips):
    """trip_id=<id> keeps only that trip; trip_id="" keeps only home expenses."""
    trip = Trip(name="Georgia", start_date=date(2026, 9, 10))
    firestore_service.add_trip(TEST_USER_ID, trip)

    tagged = _trip_record(11, 30.0, trip_id=trip.id)
    home = _trip_record(11, 20.0)
    firestore_service.append_transaction(TEST_USER_ID, tagged)
    firestore_service.append_transaction(TEST_USER_ID, home)

    in_trip = firestore_service.get_transactions(TEST_USER_ID, trip_id=trip.id)
    assert [r.id for r in in_trip] == [tagged.id]

    at_home = firestore_service.get_transactions(TEST_USER_ID, trip_id="")
    assert [r.id for r in at_home] == [home.id]

    assert len(firestore_service.get_transactions(TEST_USER_ID)) == 2


@pytest.mark.integration
def test_assign_transactions_skips_recurring_and_detaches_on_delete(
    firestore_service, clean_trips
):
    """Back-filling a past trip picks up its window but never recurring expenses."""
    trip = Trip(name="Georgia", start_date=date(2026, 9, 10), end_date=date(2026, 9, 12))
    firestore_service.add_trip(TEST_USER_ID, trip)

    inside = _trip_record(11, 30.0)
    outside = _trip_record(20, 40.0)
    rent = _trip_record(11, 800.0, category="housing", recurring=True, recurring_template_id="t1")
    for record in (inside, outside, rent):
        firestore_service.append_transaction(TEST_USER_ID, record)

    assigned = firestore_service.assign_transactions_to_trip(
        TEST_USER_ID, trip.id, trip.start_date, trip.end_date
    )
    assert assigned == 1

    in_trip = firestore_service.get_transactions(TEST_USER_ID, trip_id=trip.id)
    assert [r.id for r in in_trip] == [inside.id]

    # Deleting the trip keeps the expense and only clears its tag.
    firestore_service.delete_trip(TEST_USER_ID, trip.id)
    still_there = firestore_service.get_transactions(TEST_USER_ID)
    assert inside.id in {r.id for r in still_there}
    assert all(r.trip_id == "" for r in still_there)
