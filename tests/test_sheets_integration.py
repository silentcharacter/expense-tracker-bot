"""Integration tests for SheetsService.

These tests call the real Google Sheets API and require:
  - .env.yaml with REGISTRY_SHEET_ID and valid credentials
  - At least one registered user in the Master Registry

Run:
  pytest tests/test_sheets_integration.py -m integration -v
"""

import pytest

from models.expense import ExpenseRecord, ExpenseSource
from models.category import CATEGORIES


def _find_test_spreadsheet(sheets_service) -> str:
    """Return the spreadsheet_id of the first registered user."""
    from models.expense import User

    sheet = sheets_service._get_sheet(sheets_service._registry_id, "Registry")
    rows = sheet.get_all_records(expected_headers=User.registry_headers())
    if not rows:
        pytest.skip("No registered users in the Master Registry — cannot run Sheets tests")
    return rows[0]["spreadsheet_id"]


@pytest.fixture(scope="module")
def test_spreadsheet_id(sheets_service):
    """Spreadsheet ID of a real user for integration tests."""
    return _find_test_spreadsheet(sheets_service)


# ── append_transaction ────────────────────────────────────────────────────────

@pytest.mark.integration
def test_append_transaction_writes_and_reads_back(sheets_service, test_spreadsheet_id):
    """append_transaction should write a row that can be read back intact."""
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

    sheets_service.append_transaction(test_spreadsheet_id, record)

    try:
        recent = sheets_service.get_transactions(test_spreadsheet_id, limit=5)
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
    finally:
        sheets_service.delete_last_transaction(test_spreadsheet_id)


# ── update_transaction_category ──────────────────────────────────────────────

@pytest.mark.integration
def test_update_transaction_category_changes_category(sheets_service, test_spreadsheet_id):
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
    sheets_service.append_transaction(test_spreadsheet_id, record)

    try:
        ok = sheets_service.update_transaction_category(
            test_spreadsheet_id, record.id, "transport", ""
        )
        assert ok is True

        recent = sheets_service.get_transactions(test_spreadsheet_id, limit=10)
        got = next((r for r in recent if r.id == record.id), None)
        assert got is not None, f"Record {record.id} not found after update"
        assert got.category == "transport"
        assert got.subcategory == ""
    finally:
        sheets_service.delete_transaction_by_id(test_spreadsheet_id, record.id)


@pytest.mark.integration
def test_update_transaction_category_returns_false_for_unknown_id(sheets_service, test_spreadsheet_id):
    """update_transaction_category should return False when the record ID doesn't exist."""
    ok = sheets_service.update_transaction_category(
        test_spreadsheet_id, "00000000-0000-0000-0000-000000000000", "food", ""
    )
    assert ok is False


# ── get_categories / ensure_categories_sheet ─────────────────────────────────

@pytest.mark.integration
def test_ensure_categories_sheet_seeds_defaults(sheets_service, test_spreadsheet_id):
    """ensure_categories_sheet should write header + default category rows if empty."""
    from services.sheets import _category_cache, SHEET_CATEGORIES

    sheet = sheets_service._get_sheet(test_spreadsheet_id, SHEET_CATEGORIES)
    backup = sheet.get_all_values()

    try:
        sheet.clear()
        _category_cache.pop(test_spreadsheet_id, None)

        sheets_service.ensure_categories_sheet(test_spreadsheet_id)
        cats = sheets_service.get_categories(test_spreadsheet_id)

        default_slugs = {c.slug for c in CATEGORIES}
        assert {c.slug for c in cats} == default_slugs
    finally:
        sheet.clear()
        if backup:
            sheet.update(backup, raw=False)
        _category_cache.pop(test_spreadsheet_id, None)


@pytest.mark.integration
def test_get_categories_returns_cached(sheets_service, test_spreadsheet_id):
    """Second call within TTL should return the same list object from cache."""
    from services.sheets import _category_cache
    _category_cache.pop(test_spreadsheet_id, None)

    cats1 = sheets_service.get_categories(test_spreadsheet_id)
    cats2 = sheets_service.get_categories(test_spreadsheet_id)
    assert cats1 is cats2
