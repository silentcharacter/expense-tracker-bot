"""Integration tests for CurrencyService.

These tests call the real ExchangeRate-API and require:
  - .env.yaml with EXCHANGE_RATE_API_KEY

Run:
  pytest tests/test_currency_integration.py -m integration -v
"""

import pytest

from services.currency import CurrencyService, CurrencyServiceError


@pytest.mark.integration
async def test_convert_thb_to_usd(currency_service: CurrencyService):
    """THB → USD should return a realistic rate (~0.027–0.035)."""
    converted, rate = await currency_service.convert(1000, "THB", "USD")

    assert rate > 0.02
    assert rate < 0.05
    assert converted == pytest.approx(1000 * rate, rel=1e-4)


@pytest.mark.integration
async def test_convert_usd_to_thb(currency_service: CurrencyService):
    """USD → THB should return a realistic rate (~28–40)."""
    converted, rate = await currency_service.convert(100, "USD", "THB")

    assert rate > 25
    assert rate < 45
    assert converted == pytest.approx(100 * rate, rel=1e-4)


@pytest.mark.integration
async def test_convert_same_currency(currency_service: CurrencyService):
    """Same currency should return rate 1.0 without calling the API."""
    converted, rate = await currency_service.convert(500, "USD", "USD")

    assert rate == 1.0
    assert converted == 500.0


@pytest.mark.integration
async def test_convert_eur_to_usd(currency_service: CurrencyService):
    """EUR → USD should return a realistic rate (~0.9–1.5)."""
    converted, rate = await currency_service.convert(100, "EUR", "USD")

    assert rate > 0.9
    assert rate < 1.5
    assert converted == pytest.approx(100 * rate, rel=1e-4)


@pytest.mark.integration
async def test_get_rate_is_cached(currency_service: CurrencyService):
    """Second call for the same pair should return a cached rate."""
    rate1 = await currency_service.get_rate("USD", "THB")
    rate2 = await currency_service.get_rate("USD", "THB")

    assert rate1 == rate2


@pytest.mark.integration
async def test_convert_case_insensitive(currency_service: CurrencyService):
    """Currency codes should be case-insensitive."""
    _, rate_upper = await currency_service.convert(100, "USD", "THB")
    _, rate_lower = await currency_service.convert(100, "usd", "thb")

    assert rate_upper == rate_lower


@pytest.mark.integration
async def test_invalid_currency_raises(currency_service: CurrencyService):
    """An invalid currency code should raise CurrencyServiceError."""
    with pytest.raises(CurrencyServiceError):
        await currency_service.convert(100, "USD", "ZZZZZ")
