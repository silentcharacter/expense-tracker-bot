"""Integration tests for SheetsService.

These tests call the real Google Sheets API and require:
  - .env.yaml with REGISTRY_SHEET_ID and valid credentials
  - At least one registered user in the Master Registry

Run:
  pytest tests/test_sheets_integration.py -m integration -v
"""

import pytest

from models.expense import ExpenseRecord, ExpenseSource


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
