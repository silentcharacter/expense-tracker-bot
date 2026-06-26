"""Unit tests for GeminiService retry behavior."""

from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from services import gemini as gemini_module
from services.gemini import GeminiService


class _FakeModels:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def generate_content(self, **kwargs: Any) -> SimpleNamespace:
        self.calls += 1
        if self.calls <= self.failures:
            raise errors.ServerError(
                503,
                {"error": {"message": "This model is currently experiencing high demand."}},
                None,
            )
        return SimpleNamespace(
            text='{"amount": 350, "currency": "THB", "category": "transport", "subcategory": "", "description": "taxi"}'
        )


@pytest.mark.asyncio
async def test_generate_retries_transient_gemini_server_errors(monkeypatch) -> None:
    """Transient Gemini 503s should be retried before surfacing to handlers."""
    service = GeminiService.__new__(GeminiService)
    fake_models = _FakeModels(failures=2)
    service._client = SimpleNamespace(models=fake_models)

    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(gemini_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(gemini_module.random, "uniform", lambda _low, _high: 0)

    expense = await service._generate("system", [])

    assert fake_models.calls == 3
    assert sleep_calls == [0.5, 1.0]
    assert expense.amount == 350
    assert expense.currency == "THB"


@pytest.mark.asyncio
async def test_generate_does_not_retry_non_transient_gemini_errors(monkeypatch) -> None:
    """Permanent Gemini errors should fail immediately."""
    service = GeminiService.__new__(GeminiService)
    fake_models = _FakeModels(failures=0)

    def raise_client_error(**kwargs: Any) -> SimpleNamespace:
        raise errors.ClientError(400, {"error": {"message": "bad request"}}, None)

    fake_models.generate_content = raise_client_error
    service._client = SimpleNamespace(models=fake_models)

    async def fail_sleep(delay: float) -> None:
        raise AssertionError("non-transient errors must not sleep/retry")

    monkeypatch.setattr(gemini_module.asyncio, "sleep", fail_sleep)

    with pytest.raises(gemini_module.GeminiServiceError):
        await service._generate("system", [])
