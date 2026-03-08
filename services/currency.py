"""Exchange rate service with 24-hour in-memory caching."""

import logging
import os
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Cache TTL in seconds (24 hours)
_CACHE_TTL = 86_400

# In-memory cache: (from_currency, to_currency) → (rate, fetched_at)
_rate_cache: dict[tuple[str, str], tuple[float, float]] = {}


class CurrencyServiceError(Exception):
    """Raised when the exchange rate cannot be fetched."""


class CurrencyService:
    """Fetches and caches FX rates via the ExchangeRate-API.

    Rates are cached per currency pair for 24 hours to stay within the
    free-tier limit and reduce latency on repeated requests.
    """

    BASE_URL = "https://v6.exchangerate-api.com/v6/{api_key}/pair/{from_cur}/{to_cur}"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ["EXCHANGE_RATE_API_KEY"]

    # ── Public API ──────────────────────────────────────────────────────────

    async def get_rate(self, from_currency: str, to_currency: str) -> float:
        """Return the exchange rate from_currency → to_currency.

        Uses in-memory cache; fetches from API when stale (> 24 h).

        Args:
            from_currency: ISO 4217 source currency (e.g. "THB").
            to_currency:   ISO 4217 target currency (e.g. "USD").

        Returns:
            Conversion rate as a float.

        Raises:
            CurrencyServiceError: When the API request fails.
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency == to_currency:
            return 1.0

        cached = self._get_cached(from_currency, to_currency)
        if cached is not None:
            return cached

        rate = await self._fetch_rate(from_currency, to_currency)
        self._set_cache(from_currency, to_currency, rate)
        return rate

    async def convert(self, amount: float, from_currency: str, to_currency: str) -> tuple[float, float]:
        """Convert an amount and return (converted_amount, fx_rate).

        Args:
            amount:        Amount in from_currency.
            from_currency: ISO 4217 source currency.
            to_currency:   ISO 4217 target currency.

        Returns:
            Tuple of (converted_amount, fx_rate).
        """
        rate = await self.get_rate(from_currency, to_currency)
        return round(amount * rate, 6), rate

    def invalidate_cache(self, from_currency: Optional[str] = None, to_currency: Optional[str] = None) -> None:
        """Remove cached rates.  If currencies are None, clears the whole cache."""
        if from_currency is None:
            _rate_cache.clear()
        else:
            key = (from_currency.upper(), to_currency.upper() if to_currency else "")
            _rate_cache.pop(key, None)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _get_cached(self, from_cur: str, to_cur: str) -> Optional[float]:
        """Return a cached rate if it is still fresh, otherwise None."""
        entry = _rate_cache.get((from_cur, to_cur))
        if entry is None:
            return None
        rate, fetched_at = entry
        if time.monotonic() - fetched_at > _CACHE_TTL:
            del _rate_cache[(from_cur, to_cur)]
            return None
        return rate

    def _set_cache(self, from_cur: str, to_cur: str, rate: float) -> None:
        """Store a rate in the cache with the current timestamp."""
        _rate_cache[(from_cur, to_cur)] = (rate, time.monotonic())

    async def _fetch_rate(self, from_cur: str, to_cur: str) -> float:
        """Fetch a live rate from ExchangeRate-API.

        Raises:
            CurrencyServiceError: On HTTP error or unexpected JSON shape.
        """
        url = self.BASE_URL.format(api_key=self._api_key, from_cur=from_cur, to_cur=to_cur)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        raise CurrencyServiceError(
                            f"ExchangeRate API returned HTTP {resp.status} for {from_cur}/{to_cur}"
                        )
                    data = await resp.json()
        except aiohttp.ClientError as exc:
            raise CurrencyServiceError(f"Network error fetching rate {from_cur}/{to_cur}: {exc}") from exc

        result = data.get("result")
        if result != "success":
            error_type = data.get("error-type", "unknown")
            raise CurrencyServiceError(
                f"ExchangeRate API error '{error_type}' for {from_cur}/{to_cur}"
            )

        rate = data.get("conversion_rate")
        if rate is None:
            raise CurrencyServiceError(f"No conversion_rate in response for {from_cur}/{to_cur}")

        logger.debug("Fetched rate %s→%s = %.6f", from_cur, to_cur, rate)
        return float(rate)
